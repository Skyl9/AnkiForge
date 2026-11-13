"""Tests complets pour l'outil MCP ingest_authority_source.

Couvre :
- Importation inline_markdown avec certificat JSON valide
- Garde-fou volumétrique pour inline_markdown (> 32k caractères)
- Importation file_staging avec fichier texte/markdown et PDF factice
- Sécurité Path Traversal (chemin absolu, ../, symlink)
- Sécurité SSRF (blocage 127.0.0.1, 0.0.0.0, 192.168.1.1, schémas file://)
- Idempotence (already_exists puis force_update=True)
- Robustesse du décodage JSON (présence de clôtures ```json ```)
"""

from __future__ import annotations

import hashlib
import json
from unittest.mock import MagicMock, patch

import pytest

from ankidraft.database.models import (
    DocumentModel,
    NoteModel,
    NoteTypeModel,
    NoteVersionModel,
)
from ankidraft.services.ai.mcp_tool_registry import MCPToolRegistry
from ankidraft.services.profile_manager import ProfileManager
from ankidraft.services.reindex_service import REINDEX_ERROR

pytestmark = pytest.mark.integration


def _create_test_note(mock_db):
    """Crée un type de note et une note de base pour les tests."""
    note_type = NoteTypeModel.create(name="Basic Test", fields_schema='["Front", "Back"]', templates="[]", css_style="")
    note = NoteModel.create(guid="test-guid-1", note_type=note_type, tags="")
    NoteVersionModel.create(note=note, version_number=1, is_active=True, content='{"Front": "Q", "Back": "R"}')
    return note_type, note


def _setup_staging_dir():
    """Configure le dossier de staging pour le profil de test."""
    pm = ProfileManager()
    # Forcer le profil actif pour le test
    from ankidraft.utils.paths import set_active_profile

    set_active_profile("test")
    # Créer un gestionnaire de profil avec le bon dossier
    staging_dir = pm.get_staging_dir("test")
    return staging_dir


class TestIngestAuthoritySourceInlineMarkdown:
    """Tests pour le mode inline_markdown."""

    def test_inline_markdown_basic_with_valid_authority_certificate(self, mock_db):
        """Importation inline_markdown avec certificat JSON valide."""
        _create_test_note(mock_db)

        content = "# Titre du document\n\nContenu de la source d'autorité."
        authority_meta = json.dumps({"authority_score": 95.0, "authority_type": "RFC", "issuer": "IETF"})

        result = json.loads(
            MCPToolRegistry.ingest_authority_source(
                transport_mode="inline_markdown",
                inline_content=content,
                authority_metadata_json=authority_meta,
            )
        )

        assert result["status"] == "created"
        assert result["document_id"] > 0
        assert result["title"] == "Titre du document"
        assert result["authority_score"] == 95.0
        assert result["authority_type"] == "RFC"
        assert "source_sha256" in result
        assert len(result["source_sha256"]) == 64
        assert result["index_status"] in ("indexed", "imported_unindexed")

        # Vérifier en base
        doc = DocumentModel.get_by_id(result["document_id"])
        assert doc.title == "Titre du document"
        assert doc.content == content
        assert doc.authority_score == 95.0
        assert doc.authority_type == "RFC"
        assert doc.authority_certificate == authority_meta
        assert doc.source_sha256 == result["source_sha256"]
        assert doc.file_type == "md"

    def test_inline_markdown_title_fallback_to_h1(self, mock_db):
        """Titre déduit du premier H1 si non fourni."""
        _create_test_note(mock_db)

        content = "# Mon Titre H1\n\nContenu sans titre explicite."
        result = json.loads(
            MCPToolRegistry.ingest_authority_source(
                transport_mode="inline_markdown",
                inline_content=content,
                authority_metadata_json="{}",
            )
        )

        assert result["status"] == "created"
        assert result["title"] == "Mon Titre H1"

    def test_inline_markdown_title_fallback_default(self, mock_db):
        """Repli sur 'Source d'Autorité Markdown' si pas de H1."""
        _create_test_note(mock_db)

        content = "Contenu sans titre H1."
        result = json.loads(
            MCPToolRegistry.ingest_authority_source(
                transport_mode="inline_markdown",
                inline_content=content,
                authority_metadata_json="{}",
            )
        )

        assert result["status"] == "created"
        assert result["title"] == "Source d'Autorité Markdown"

    def test_inline_markdown_payload_too_large(self, mock_db):
        """Garde-fou volumétrique : > 32 000 caractères refusé."""
        _create_test_note(mock_db)

        large_content = "x" * 32001
        result = json.loads(
            MCPToolRegistry.ingest_authority_source(
                transport_mode="inline_markdown",
                inline_content=large_content,
                authority_metadata_json="{}",
            )
        )

        assert result["status"] == "payload_too_large"
        assert "trop volumineux" in result["message"].lower()
        assert "32 000" in result["message"]

    def test_inline_markdown_exact_limit_allowed(self, mock_db):
        """Exactement 32 000 caractères autorisé."""
        _create_test_note(mock_db)

        content = "x" * 32000
        result = json.loads(
            MCPToolRegistry.ingest_authority_source(
                transport_mode="inline_markdown",
                inline_content=content,
                authority_metadata_json="{}",
            )
        )

        assert result["status"] == "created"

    def test_inline_markdown_robust_json_with_markdown_fences(self, mock_db):
        """Décodage robuste tolérant les blocs ```json ```."""
        _create_test_note(mock_db)

        content = "Contenu test."
        authority_with_fences = '```json\n{"authority_score": 88.5, "authority_type": "ACADEMIC"}\n```'

        result = json.loads(
            MCPToolRegistry.ingest_authority_source(
                transport_mode="inline_markdown",
                inline_content=content,
                authority_metadata_json=authority_with_fences,
            )
        )

        assert result["status"] == "created"
        assert result["authority_score"] == 88.5
        assert result["authority_type"] == "ACADEMIC"

    def test_inline_markdown_authority_score_out_of_bounds_rejected(self, mock_db):
        """Score d'autorité hors bornes [0, 100] refusé."""
        _create_test_note(mock_db)

        authority_meta = json.dumps({"authority_score": 150.0, "authority_type": "TEST"})
        result = json.loads(
            MCPToolRegistry.ingest_authority_source(
                transport_mode="inline_markdown",
                inline_content="Contenu.",
                authority_metadata_json=authority_meta,
            )
        )

        assert result["status"] == "error"
        assert "0.0 et 100.0" in result["message"]


class TestIngestAuthoritySourceFileStaging:
    """Tests pour le mode file_staging."""

    def test_file_staging_text_file(self, mock_db):
        """Importation file_staging avec fichier texte/markdown."""
        _create_test_note(mock_db)

        staging_dir = _setup_staging_dir()
        test_file = staging_dir / "test_doc.md"
        test_content = "# Document Staging\n\nContenu extrait depuis un fichier."
        test_file.write_text(test_content, encoding="utf-8")

        result = json.loads(
            MCPToolRegistry.ingest_authority_source(
                transport_mode="file_staging",
                locator="test_doc.md",
                authority_metadata_json=json.dumps({"authority_score": 90.0, "authority_type": "COURSE"}),
            )
        )

        assert result["status"] == "created"
        # Pour file_staging, le titre est déduit du nom de fichier (sans extension)
        assert result["title"] == "test_doc"
        assert result["authority_score"] == 90.0
        assert result["authority_type"] == "COURSE"
        assert result["index_status"] in ("indexed", "imported_unindexed")

        # Fichier nettoyé après ingestion
        assert not test_file.exists()

    def test_file_staging_pdf_archives_media(self, mock_db):
        """Importation file_staging PDF : archive le média original."""
        _create_test_note(mock_db)

        staging_dir = _setup_staging_dir()
        pdf_file = staging_dir / "test.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 dummy content")

        # Mocker DocumentParser pour éviter les problèmes de parsing PDF
        with patch("ankidraft.services.parsing.document_parser.DocumentParser") as mock_parser_class:
            mock_parser = MagicMock()
            mock_parser_class.return_value = mock_parser
            mock_parser.parse_document.return_value = "# Test PDF\n\nContenu extrait du PDF."

            result = json.loads(
                MCPToolRegistry.ingest_authority_source(
                    transport_mode="file_staging",
                    locator="test.pdf",
                    authority_metadata_json=json.dumps({"authority_score": 85.0, "authority_type": "TECHNICAL_SPEC"}),
                )
            )

        assert result["status"] == "created"
        assert result["title"] == "test"
        assert result["authority_score"] == 85.0
        assert result["authority_type"] == "TECHNICAL_SPEC"

        # Vérifier que le média a été archivé
        doc = DocumentModel.get_by_id(result["document_id"])
        assert doc.original_media is not None
        assert doc.original_media.filename.endswith(".pdf")

        # Fichier nettoyé
        assert not pdf_file.exists()

    def test_file_staging_path_traversal_absolute_rejected(self, mock_db):
        """Rejet des chemins absolus (/etc/passwd)."""
        _create_test_note(mock_db)

        result = json.loads(
            MCPToolRegistry.ingest_authority_source(
                transport_mode="file_staging",
                locator="/etc/passwd",
                authority_metadata_json="{}",
            )
        )

        assert result["status"] == "error"
        assert "chemin absolu" in result["message"].lower()

    def test_file_staging_path_traversal_parent_rejected(self, mock_db):
        """Rejet des traversées ../."""
        _create_test_note(mock_db)

        result = json.loads(
            MCPToolRegistry.ingest_authority_source(
                transport_mode="file_staging",
                locator="../secrets.txt",
                authority_metadata_json="{}",
            )
        )

        assert result["status"] == "error"
        assert "traversée" in result["message"].lower() or "path traversal" in result["message"].lower()

    def test_file_staging_symlink_rejected(self, mock_db):
        """Rejet des liens symboliques."""
        _create_test_note(mock_db)

        staging_dir = _setup_staging_dir()

        # Créer un vrai fichier
        real_file = staging_dir / "real.txt"
        real_file.write_text("Real content")

        # Créer un symlink vers ce fichier
        symlink_file = staging_dir / "link.txt"
        try:
            symlink_file.symlink_to(real_file)
        except OSError:
            # Sur certains systèmes, les symlinks ne sont pas supportés en test
            pytest.skip("Symlinks non supportés sur ce système")

        result = json.loads(
            MCPToolRegistry.ingest_authority_source(
                transport_mode="file_staging",
                locator="link.txt",
                authority_metadata_json="{}",
            )
        )

        assert result["status"] == "error"
        assert "symbolique" in result["message"].lower() or "symlink" in result["message"].lower()

    def test_file_staging_nonexistent_file(self, mock_db):
        """Fichier inexistant dans staging refusé."""
        _create_test_note(mock_db)

        result = json.loads(
            MCPToolRegistry.ingest_authority_source(
                transport_mode="file_staging",
                locator="nonexistent.md",
                authority_metadata_json="{}",
            )
        )

        assert result["status"] == "error"
        assert "introuvable" in result["message"].lower()


class TestIngestAuthoritySourceUrl:
    """Tests pour le mode URL (avec mocks WebImporter)."""

    @patch("ankidraft.services.parsing.web_importer.WebImporter")
    def test_url_mode_success(self, mock_importer_class, mock_db):
        """Importation URL réussie avec WebImporter mocké."""
        _create_test_note(mock_db)

        mock_importer = MagicMock()
        mock_importer_class.return_value = mock_importer

        mock_result = MagicMock()
        mock_result.content = "# Page Web\n\nContenu de la page web."
        mock_result.title = "Titre Page Web"
        mock_importer.analyze_url.return_value = mock_result

        result = json.loads(
            MCPToolRegistry.ingest_authority_source(
                transport_mode="url",
                locator="https://example.com/rfc1234",
                authority_metadata_json=json.dumps({"authority_score": 100.0, "authority_type": "RFC"}),
            )
        )

        assert result["status"] == "created"
        assert result["title"] == "Titre Page Web"
        assert result["authority_score"] == 100.0
        assert result["authority_type"] == "RFC"
        assert result["source_sha256"] is not None

        # Vérifier que WebImporter a été appelé
        mock_importer.analyze_url.assert_called_once()

    @patch("ankidraft.services.parsing.web_importer.WebImporter")
    def test_url_mode_ssrf_blocked_localhost(self, mock_importer_class, mock_db):
        """Blocage SSRF pour 127.0.0.1."""
        _create_test_note(mock_db)

        mock_importer = MagicMock()
        mock_importer_class.return_value = mock_importer
        from ankidraft.services.parsing.web_importer import WebImportError

        mock_importer.analyze_url.side_effect = WebImportError("Adresse réseau privé (environnement interne) refusée pour l'import web.", category="network")

        result = json.loads(
            MCPToolRegistry.ingest_authority_source(
                transport_mode="url",
                locator="http://127.0.0.1/admin",
                authority_metadata_json="{}",
            )
        )

        assert result["status"] == "error"
        assert result["category"] == "network"

    @patch("ankidraft.services.parsing.web_importer.WebImporter")
    def test_url_mode_ssrf_blocked_unspecified(self, mock_importer_class, mock_db):
        """Blocage SSRF pour 0.0.0.0 (is_unspecified)."""
        _create_test_note(mock_db)

        mock_importer = MagicMock()
        mock_importer_class.return_value = mock_importer
        from ankidraft.services.parsing.web_importer import WebImportError

        mock_importer.analyze_url.side_effect = WebImportError("Adresse réseau privé (environnement interne) refusée pour l'import web.", category="network")

        result = json.loads(
            MCPToolRegistry.ingest_authority_source(
                transport_mode="url",
                locator="http://0.0.0.0/",
                authority_metadata_json="{}",
            )
        )

        assert result["status"] == "error"
        assert result["category"] == "network"

    @patch("ankidraft.services.parsing.web_importer.WebImporter")
    def test_url_mode_ssrf_blocked_private_ip(self, mock_importer_class, mock_db):
        """Blocage SSRF pour IP privée 192.168.1.1."""
        _create_test_note(mock_db)

        mock_importer = MagicMock()
        mock_importer_class.return_value = mock_importer
        from ankidraft.services.parsing.web_importer import WebImportError

        mock_importer.analyze_url.side_effect = WebImportError("Adresse réseau privé (environnement interne) refusée pour l'import web.", category="network")

        result = json.loads(
            MCPToolRegistry.ingest_authority_source(
                transport_mode="url",
                locator="http://192.168.1.1/admin",
                authority_metadata_json="{}",
            )
        )

        assert result["status"] == "error"
        assert result["category"] == "network"

    @patch("ankidraft.services.parsing.web_importer.WebImporter")
    def test_url_mode_file_scheme_rejected(self, mock_importer_class, mock_db):
        """Blocage schéma file://."""
        _create_test_note(mock_db)

        mock_importer = MagicMock()
        mock_importer_class.return_value = mock_importer
        from ankidraft.services.parsing.web_importer import WebImportError

        mock_importer.analyze_url.side_effect = WebImportError("Protocole 'file' non supporté : utilisez http:// ou https://.", category="invalid_url")

        result = json.loads(
            MCPToolRegistry.ingest_authority_source(
                transport_mode="url",
                locator="file:///etc/passwd",
                authority_metadata_json="{}",
            )
        )

        assert result["status"] == "error"
        assert result["category"] in ("invalid_url", "network")


class TestIngestAuthoritySourceIdempotence:
    """Tests d'idempotence (détection doublons et force_update)."""

    def test_idempotence_same_source_url_returns_already_exists(self, mock_db):
        """Même source_url -> already_exists sans force_update."""
        _create_test_note(mock_db)

        content = "Contenu de test pour idempotence."
        authority_meta = json.dumps({"authority_score": 90.0, "authority_type": "RFC"})

        # Première ingestion
        result1 = json.loads(
            MCPToolRegistry.ingest_authority_source(
                transport_mode="inline_markdown",
                inline_content=content,
                title="Doc RFC Test",
                authority_metadata_json=authority_meta,
            )
        )
        assert result1["status"] == "created"
        doc_id = result1["document_id"]

        # Deuxième ingestion avec même contenu (même source_sha256)
        result2 = json.loads(
            MCPToolRegistry.ingest_authority_source(
                transport_mode="inline_markdown",
                inline_content=content,
                title="Doc RFC Test 2",
                authority_metadata_json=authority_meta,
            )
        )

        assert result2["status"] == "already_exists"
        assert result2["document_id"] == doc_id

    def test_idempotence_force_update_true_updates_document(self, mock_db):
        """force_update=True met à jour le document existant (même contenu, métadonnées différentes)."""
        _create_test_note(mock_db)

        content = "Contenu identique pour test force_update."
        authority_meta_v1 = json.dumps({"authority_score": 90.0, "authority_type": "RFC"})
        authority_meta_v2 = json.dumps({"authority_score": 95.0, "authority_type": "RFC", "updated": True})

        # Première ingestion
        result1 = json.loads(
            MCPToolRegistry.ingest_authority_source(
                transport_mode="inline_markdown",
                inline_content=content,
                authority_metadata_json=authority_meta_v1,
            )
        )
        assert result1["status"] == "created"
        doc_id = result1["document_id"]

        # Deuxième ingestion avec force_update et métadonnées différentes
        result2 = json.loads(
            MCPToolRegistry.ingest_authority_source(
                transport_mode="inline_markdown",
                inline_content=content,
                authority_metadata_json=authority_meta_v2,
                force_update=True,
            )
        )

        assert result2["status"] == "updated"
        assert result2["document_id"] == doc_id

        # Vérifier que les métadonnées d'autorité ont été mises à jour
        doc = DocumentModel.get_by_id(doc_id)
        assert doc.authority_score == 95.0
        assert doc.authority_certificate == authority_meta_v2


class TestIngestAuthoritySourceEdgeCases:
    """Cas limites et gestion d'erreurs."""

    def test_invalid_transport_mode(self, mock_db):
        """Mode de transport invalide refusé."""
        _create_test_note(mock_db)

        result = json.loads(
            MCPToolRegistry.ingest_authority_source(
                transport_mode="invalid_mode",
                authority_metadata_json="{}",
            )
        )

        assert result["status"] == "error"
        assert "invalide" in result["message"].lower()

    def test_url_mode_missing_locator(self, mock_db):
        """Mode url sans locator refusé."""
        _create_test_note(mock_db)

        result = json.loads(
            MCPToolRegistry.ingest_authority_source(
                transport_mode="url",
                authority_metadata_json="{}",
            )
        )

        assert result["status"] == "error"
        assert "requis" in result["message"].lower()

    def test_file_staging_missing_locator(self, mock_db):
        """Mode file_staging sans locator refusé."""
        _create_test_note(mock_db)

        result = json.loads(
            MCPToolRegistry.ingest_authority_source(
                transport_mode="file_staging",
                authority_metadata_json="{}",
            )
        )

        assert result["status"] == "error"
        assert "requis" in result["message"].lower()

    def test_inline_markdown_missing_content(self, mock_db):
        """Mode inline_markdown sans inline_content refusé."""
        _create_test_note(mock_db)

        result = json.loads(
            MCPToolRegistry.ingest_authority_source(
                transport_mode="inline_markdown",
                authority_metadata_json="{}",
            )
        )

        assert result["status"] == "error"
        assert "requis" in result["message"].lower()

    def test_authority_type_not_string_rejected(self, mock_db):
        """authority_type non-string refusé."""
        _create_test_note(mock_db)

        authority_meta = json.dumps({"authority_score": 50.0, "authority_type": 123})
        result = json.loads(
            MCPToolRegistry.ingest_authority_source(
                transport_mode="inline_markdown",
                inline_content="Test.",
                authority_metadata_json=authority_meta,
            )
        )

        assert result["status"] == "error"
        assert "chaîne" in result["message"].lower()

    def test_title_uniqueness_enforced(self, mock_db):
        """Unicité du titre garantie via _unique_title."""
        _create_test_note(mock_db)

        content = "Contenu identique."
        authority_meta = json.dumps({"authority_score": 50.0, "authority_type": "TEST"})

        # Première ingestion
        r1 = json.loads(
            MCPToolRegistry.ingest_authority_source(
                transport_mode="inline_markdown",
                inline_content=content,
                title="Titre Unique",
                authority_metadata_json=authority_meta,
            )
        )
        assert r1["status"] == "created"

        # Deuxième ingestion avec même titre -> suffixe (2)
        r2 = json.loads(
            MCPToolRegistry.ingest_authority_source(
                transport_mode="inline_markdown",
                inline_content=content + " v2",
                title="Titre Unique",
                authority_metadata_json=authority_meta,
            )
        )
        assert r2["status"] == "created"
        assert r2["title"] == "Titre Unique (2)"


class TestIngestAuthoritySourceSHA256:
    """Tests de l'empreinte SHA-256."""

    def test_source_sha256_consistent(self, mock_db):
        """Même contenu normalisé -> même SHA-256."""
        _create_test_note(mock_db)

        content = "  Contenu avec espaces  \n\n  "
        authority_meta = "{}"

        r1 = json.loads(
            MCPToolRegistry.ingest_authority_source(
                transport_mode="inline_markdown",
                inline_content=content,
                authority_metadata_json=authority_meta,
            )
        )
        r2 = json.loads(
            MCPToolRegistry.ingest_authority_source(
                transport_mode="inline_markdown",
                inline_content=content + " extra",
                authority_metadata_json=authority_meta,
                force_update=True,
            )
        )

        # Le SHA-256 doit être recalculé sur le nouveau contenu
        assert r2["source_sha256"] != r1["source_sha256"]

        # Mais pour le même contenu exact (après strip), même SHA
        r3 = json.loads(
            MCPToolRegistry.ingest_authority_source(
                transport_mode="inline_markdown",
                inline_content="  Contenu avec espaces  \n\n  ",
                authority_metadata_json=authority_meta,
                force_update=True,
            )
        )
        assert r3["source_sha256"] == r1["source_sha256"]

    def test_source_sha256_matches_hashlib(self, mock_db):
        """SHA-256 correspond à hashlib.sha256(normalized_content)."""
        _create_test_note(mock_db)

        content = "Contenu exact pour test SHA-256."
        expected_sha256 = hashlib.sha256(content.strip().encode("utf-8")).hexdigest()

        result = json.loads(
            MCPToolRegistry.ingest_authority_source(
                transport_mode="inline_markdown",
                inline_content=content,
                authority_metadata_json="{}",
            )
        )

        assert result["source_sha256"] == expected_sha256


class TestIngestAuthoritySourceIntegration:
    """Tests d'intégration plus complets."""

    @patch("ankidraft.services.reindex_service.reindex_document")
    def test_graceful_degradation_when_indexing_fails(self, mock_reindex, mock_db):
        """Dégradation gracieuse si indexation RAG échoue."""
        _create_test_note(mock_db)

        mock_reindex.return_value = REINDEX_ERROR

        result = json.loads(
            MCPToolRegistry.ingest_authority_source(
                transport_mode="inline_markdown",
                inline_content="Contenu test.",
                authority_metadata_json="{}",
            )
        )

        assert result["status"] == "created"
        assert result["index_status"] == "imported_unindexed"

    @patch("ankidraft.services.reindex_service.reindex_document")
    def test_graceful_degradation_when_indexing_exception(self, mock_reindex, mock_db):
        """Dégradation gracieuse si exception lors de l'indexation."""
        _create_test_note(mock_db)

        mock_reindex.side_effect = Exception("Embeddings model not available")

        result = json.loads(
            MCPToolRegistry.ingest_authority_source(
                transport_mode="inline_markdown",
                inline_content="Contenu test.",
                authority_metadata_json="{}",
            )
        )

        assert result["status"] == "created"
        assert result["index_status"] == "imported_unindexed"

    def test_notification_emitted(self, mock_db):
        """Vérifier que la notification MCP est émise."""
        _create_test_note(mock_db)

        from ankidraft.utils.event_bus import MCPDataMutatedEvent, event_bus

        received_events = []

        def capture_event(event):
            if isinstance(event, MCPDataMutatedEvent):
                received_events.append(event)

        event_bus.subscribe(MCPDataMutatedEvent, capture_event)

        try:
            result = json.loads(
                MCPToolRegistry.ingest_authority_source(
                    transport_mode="inline_markdown",
                    inline_content="Contenu avec notification.",
                    authority_metadata_json="{}",
                )
            )

            assert result["status"] == "created"

            # Vérifier qu'un événement a été émis
            doc_events = [e for e in received_events if e.mutation_type == "document_create"]
            assert len(doc_events) == 1
            assert doc_events[0].domain == "docs"
            assert doc_events[0].target_id == result["document_id"]
            assert doc_events[0].target_name == result["title"]
        finally:
            event_bus.unsubscribe(MCPDataMutatedEvent, capture_event)

    def test_file_type_detection(self, mock_db):
        """Détection correcte du file_type selon extension."""
        _create_test_note(mock_db)

        staging_dir = _setup_staging_dir()

        # Test .md
        md_file = staging_dir / "test.md"
        md_file.write_text("# Test\n\nContent")
        r1 = json.loads(
            MCPToolRegistry.ingest_authority_source(
                transport_mode="file_staging",
                locator="test.md",
                authority_metadata_json="{}",
            )
        )
        doc1 = DocumentModel.get_by_id(r1["document_id"])
        assert doc1.file_type == "md"

        # Test .txt
        txt_file = staging_dir / "test.txt"
        txt_file.write_text("Plain text content")
        r2 = json.loads(
            MCPToolRegistry.ingest_authority_source(
                transport_mode="file_staging",
                locator="test.txt",
                authority_metadata_json="{}",
            )
        )
        doc2 = DocumentModel.get_by_id(r2["document_id"])
        assert doc2.file_type == "txt"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
