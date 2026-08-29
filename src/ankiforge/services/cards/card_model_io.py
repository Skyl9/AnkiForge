"""
Service d'Exportation et d'Importation de Modèles de Cartes AnkiForge.
Supporte le format de paquet bundle communautaire .afmodel (archive zip) et le format .json.
"""

from __future__ import annotations

import json
import logging
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ankiforge.database.models import NoteTypeModel

logger = logging.getLogger(__name__)

SCHEMA_VERSION = "1.0"
BUNDLE_EXTENSION = ".afmodel"


class CardModelIO:
    """Gestionnaire d'import / export pour les modèles de cartes (NoteTypeModel) et paquets .afmodel."""

    @classmethod
    def export_to_dict(
        cls,
        model: NoteTypeModel,
        author: str = "AnkiForge User",
        version: str = "1.0.0",
        description: str = "",
        tags: list[str] | None = None,
        demo_cards: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        """Convertit un NoteTypeModel en dictionnaire standardisé AnkiForge."""
        try:
            fields = json.loads(str(model.fields_schema)) if model.fields_schema else ["Front", "Back"]
        except Exception:
            fields = ["Front", "Back"]

        try:
            templates = json.loads(str(model.templates)) if model.templates else []
        except Exception:
            templates = []

        if not demo_cards:
            # Génère des cartes témoins par défaut basées sur le schéma
            demo_cards = [{f: f"Exemple de contenu pour {f}" for f in fields}]

        return {
            "ankiforge_schema_version": SCHEMA_VERSION,
            "metadata": {
                "name": model.name,
                "author": author or "AnkiForge User",
                "version": version or "1.0.0",
                "description": description or "",
                "exported_at": datetime.now(UTC).isoformat(),
                "tags": tags or ["ankiforge", "card-model"],
            },
            "fields_schema": fields,
            "templates": templates,
            "css_style": model.css_style or "",
            "demo_cards": demo_cards,
        }

    @classmethod
    def export_to_json(
        cls,
        model: NoteTypeModel,
        author: str = "AnkiForge User",
        version: str = "1.0.0",
        description: str = "",
        tags: list[str] | None = None,
        demo_cards: list[dict[str, str]] | None = None,
    ) -> str:
        """Sérialise un modèle de carte en JSON formaté."""
        data = cls.export_to_dict(
            model=model,
            author=author,
            version=version,
            description=description,
            tags=tags,
            demo_cards=demo_cards,
        )
        return json.dumps(data, indent=2, ensure_ascii=False)

    @classmethod
    def export_to_bundle(
        cls,
        model: NoteTypeModel,
        output_path: Path | str,
        author: str = "AnkiForge User",
        version: str = "1.0.0",
        description: str = "",
        tags: list[str] | None = None,
        demo_cards: list[dict[str, str]] | None = None,
        assets: dict[str, bytes] | None = None,
    ) -> Path:
        """
        Exporte un modèle au format bundle .afmodel (archive ZIP contenant templates, CSS, manifeste et démos).
        """
        out = Path(output_path)
        if out.suffix.lower() != BUNDLE_EXTENSION:
            out = out.with_suffix(BUNDLE_EXTENSION)

        model_dict = cls.export_to_dict(
            model=model,
            author=author,
            version=version,
            description=description,
            tags=tags,
            demo_cards=demo_cards,
        )

        manifest = {
            "ankiforge_schema_version": SCHEMA_VERSION,
            "metadata": model_dict["metadata"],
            "fields_schema": model_dict["fields_schema"],
            "templates_count": len(model_dict["templates"]),
        }

        with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            # 1. Manifeste
            zf.writestr("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))

            # 2. Templates
            templates = model_dict["templates"]
            if templates:
                first_tmpl = templates[0]
                zf.writestr("front.html", first_tmpl.get("qfmt", "{{Front}}"))
                zf.writestr("back.html", first_tmpl.get("afmt", "{{FrontSide}}<hr id='answer'>{{Back}}"))
            zf.writestr("templates.json", json.dumps(templates, indent=2, ensure_ascii=False))

            # 3. Styles CSS
            zf.writestr("style.css", model_dict.get("css_style", ""))

            # 4. Cartes démos
            zf.writestr("demo_cards.json", json.dumps(model_dict.get("demo_cards", []), indent=2, ensure_ascii=False))

            # 5. Assets optionnels
            if assets:
                for asset_name, asset_bytes in assets.items():
                    zf.writestr(f"assets/{asset_name}", asset_bytes)

        logger.info("Paquet modèle .afmodel créé avec succès dans : %s", out)
        return out

    @classmethod
    def validate_and_parse_json(cls, json_str: str) -> tuple[bool, dict[str, Any] | None, str]:
        """
        Valide et normalise la structure d'un modèle JSON AnkiForge.
        """
        try:
            data = json.loads(json_str)
        except Exception as e:
            return False, None, f"JSON invalide : {str(e)}"

        if not isinstance(data, dict):
            return False, None, "Le contenu doit être un objet JSON valide."

        # Vérification du nom
        name = ""
        if "metadata" in data and isinstance(data["metadata"], dict) and "name" in data["metadata"]:
            name = str(data["metadata"]["name"]).strip()
        elif "name" in data:
            name = str(data["name"]).strip()

        if not name:
            return False, None, "Nom du modèle manquant dans le fichier JSON."

        # Vérification des champs
        fields = data.get("fields_schema", [])
        if not isinstance(fields, list) or not fields:
            fields = ["Front", "Back"]

        # Vérification des templates
        templates = data.get("templates", [])
        if not isinstance(templates, list) or not templates:
            templates = [{"name": "Carte 1", "qfmt": "{{Front}}", "afmt": "{{FrontSide}}<hr id='answer'>{{Back}}"}]

        css_style = data.get("css_style", "")
        demo_cards = data.get("demo_cards", [])

        normalized_data = {
            "name": name,
            "fields_schema": fields,
            "templates": templates,
            "css_style": css_style,
            "metadata": data.get("metadata", {}),
            "demo_cards": demo_cards,
        }

        return True, normalized_data, ""

    @classmethod
    def read_bundle_file(cls, bundle_path: Path | str) -> tuple[bool, dict[str, Any] | None, str]:
        """
        Lit et extrait les métadonnées et gabarits d'une archive .afmodel.
        """
        path = Path(bundle_path)
        if not path.exists():
            return False, None, f"Le fichier '{path}' est introuvable."

        try:
            with zipfile.ZipFile(path, "r") as zf:
                file_list = zf.namelist()

                if "manifest.json" not in file_list:
                    return False, None, "Archive .afmodel invalide : 'manifest.json' manquant."

                manifest_raw = zf.read("manifest.json").decode("utf-8")
                manifest = json.loads(manifest_raw)

                # Lecture du CSS
                css_style = ""
                if "style.css" in file_list:
                    css_style = zf.read("style.css").decode("utf-8")

                # Lecture des templates
                templates = []
                if "templates.json" in file_list:
                    templates_raw = zf.read("templates.json").decode("utf-8")
                    templates = json.loads(templates_raw)
                elif "front.html" in file_list and "back.html" in file_list:
                    front = zf.read("front.html").decode("utf-8")
                    back = zf.read("back.html").decode("utf-8")
                    templates = [{"name": "Carte 1", "qfmt": front, "afmt": back}]

                # Lecture des cartes démos
                demo_cards = []
                if "demo_cards.json" in file_list:
                    demos_raw = zf.read("demo_cards.json").decode("utf-8")
                    demo_cards = json.loads(demos_raw)

                name = manifest.get("metadata", {}).get("name", path.stem)
                fields = manifest.get("fields_schema", ["Front", "Back"])

                model_data = {
                    "name": name,
                    "fields_schema": fields,
                    "templates": templates,
                    "css_style": css_style,
                    "metadata": manifest.get("metadata", {}),
                    "demo_cards": demo_cards,
                }
                return True, model_data, ""
        except Exception as e:
            return False, None, f"Erreur lors de la lecture du paquet .afmodel : {str(e)}"

    @classmethod
    def read_model_file(cls, file_path: Path | str) -> tuple[bool, dict[str, Any] | None, str]:
        """
        Détecte automatiquement l'extension et charge le modèle depuis un fichier .afmodel ou .json.
        """
        p = Path(file_path)
        if p.suffix.lower() == BUNDLE_EXTENSION or zipfile.is_zipfile(p):
            return cls.read_bundle_file(p)
        else:
            try:
                content = p.read_text(encoding="utf-8")
                return cls.validate_and_parse_json(content)
            except Exception as e:
                return False, None, f"Impossible de lire le fichier JSON : {str(e)}"

    @classmethod
    def save_model_to_db(
        cls,
        model_data: dict[str, Any],
        overwrite_existing: bool = False,
        new_name: str | None = None,
    ) -> tuple[NoteTypeModel, bool]:
        """
        Enregistre les données du modèle en base SQLite Peewee.
        """
        name = (new_name or model_data["name"]).strip()
        fields_json = json.dumps(model_data["fields_schema"], ensure_ascii=False)
        templates_json = json.dumps(model_data["templates"], ensure_ascii=False)
        css_style = model_data.get("css_style", "")

        existing = NoteTypeModel.get_or_none(NoteTypeModel.name == name)

        if existing:
            if overwrite_existing:
                existing.fields_schema = fields_json
                existing.templates = templates_json
                existing.css_style = css_style
                existing.save()
                return existing, False
            else:
                idx = 2
                while NoteTypeModel.get_or_none(NoteTypeModel.name == f"{name} ({idx})"):
                    idx += 1
                name = f"{name} ({idx})"

        created = NoteTypeModel.create(
            name=name,
            fields_schema=fields_json,
            templates=templates_json,
            css_style=css_style,
        )
        logger.info("Modèle de carte '%s' enregistré en base de données avec succès.", name)
        return created, True

    @classmethod
    def get_starter_pack_models(cls) -> list[dict[str, Any]]:
        """
        Retourne la collection des 4 modèles communautaires préconfigurés (Starter Pack).
        """
        return [
            {
                "id": "medical_qcm",
                "name": "Médical & QCM Interactif",
                "category": "Médecine & Concours",
                "author": "AnkiForge Santé",
                "version": "1.2.0",
                "description": "Gabarit pour questions médicales à choix multiples (QCM) avec explications physiopathologiques et badges de sévérité.",
                "fields_schema": ["Question", "Options", "Reponse_Correcte", "Explication", "Pathologie", "Source"],
                "templates": [
                    {
                        "name": "QCM Médical",
                        "qfmt": """
<div class="card-med">
  <div class="header-badge">{{Pathologie}}</div>
  <div class="q-title">{{Question}}</div>
  <div class="options-box">{{Options}}</div>
</div>
                        """.strip(),
                        "afmt": """
{{FrontSide}}
<hr id="answer">
<div class="ans-med">
  <div class="correct-badge">✓ Réponse : {{Reponse_Correcte}}</div>
  <div class="explanation-box">
    <strong>Justification Clinique :</strong><br>
    {{Explication}}
  </div>
  <div class="source-ref">Ref : {{Source}}</div>
</div>
                        """.strip(),
                    }
                ],
                "css_style": """
.card-med { font-family: -apple-system, system-ui, sans-serif; padding: 16px; background: var(--bg-panel, #1e1e2e); color: var(--text-primary, #cdd6f4); border-radius: 10px; }
.header-badge {
  display: inline-block;
  background: rgba(239, 68, 68, 0.2);
  color: #f87171;
  border: 1px solid rgba(239, 68, 68, 0.4);
  padding: 3px 10px;
  border-radius: 9999px;
  font-size: 11px;
  font-weight: bold;
  margin-bottom: 12px;
}
.q-title { font-size: 15px; font-weight: 600; line-height: 1.5; margin-bottom: 14px; }
.options-box { background: rgba(255, 255, 255, 0.04); border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 6px; padding: 10px; line-height: 1.6; }
.correct-badge { color: #10b981; font-weight: bold; font-size: 14px; margin-bottom: 8px; }
.explanation-box { background: rgba(16, 185, 129, 0.08); border-left: 3px solid #10b981; padding: 10px; border-radius: 4px; font-size: 13px; }
.source-ref { margin-top: 10px; font-size: 10px; color: #888; text-align: right; }
                """.strip(),
                "demo_cards": [
                    {
                        "Question": "Quel traitement de première intention est recommandé pour une fibrillation auriculaire aiguë instable ?",
                        "Options": "A. Bêta-bloquants per os<br>B. Cardioversion électrique synchronisée<br>C. Amiodarone IV lente<br>D. Digoxine",
                        "Reponse_Correcte": "B. Cardioversion électrique synchronisée",
                        "Explication": "L'instabilité hémodynamique impose une cardioversion électrique en urgence selon les recommandations ESC.",
                        "Pathologie": "Cardiologie / Rythmologie",
                        "Source": "Guide ESC 2024",
                    }
                ],
            },
            {
                "id": "dev_jetbrains",
                "name": "Dev & Code JetBrains",
                "category": "Informatique & Dev",
                "author": "AnkiForge Dev",
                "version": "1.1.0",
                "description": "Style sombre avec police JetBrains Mono, coloration syntaxique et encadré de solution pas à pas.",
                "fields_schema": ["Concept", "Code_Snippet", "Solution", "Complexite", "Documentation"],
                "templates": [
                    {
                        "name": "Snippet Code",
                        "qfmt": """
<div class="dev-card">
  <div class="dev-header">
    <span class="lang-tag">Python 3.12</span>
    <span class="concept-title">{{Concept}}</span>
  </div>
  <pre class="code-block"><code>{{Code_Snippet}}</code></pre>
</div>
                        """.strip(),
                        "afmt": """
{{FrontSide}}
<hr id="answer">
<div class="solution-card">
  <div class="sol-title">⚡ Explication & Solution :</div>
  <div class="sol-content">{{Solution}}</div>
  <div class="complexity-badge">⏱️ Complexité : {{Complexite}}</div>
</div>
                        """.strip(),
                    }
                ],
                "css_style": """
.dev-card { font-family: 'JetBrains Mono', monospace; background: #1e1f22; color: #bcbec4; padding: 14px; border-radius: 8px; border: 1px solid #393b40; }
.dev-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
.lang-tag { background: #3574f0; color: white; padding: 2px 8px; border-radius: 4px; font-size: 10px; font-weight: bold; }
.concept-title { font-size: 13px; font-weight: bold; color: #dfe1e5; }
.code-block { background: #2b2d30; padding: 12px; border-radius: 6px; font-size: 12px; line-height: 1.5; overflow-x: auto; }
.solution-card { margin-top: 12px; background: #26282b; border: 1px solid #43454a; border-radius: 6px; padding: 12px; font-size: 12px; }
.sol-title { color: #56a8f5; font-weight: bold; margin-bottom: 6px; }
.complexity-badge { margin-top: 8px; font-size: 11px; color: #e5c07b; font-style: italic; }
                """.strip(),
                "demo_cards": [
                    {
                        "Concept": "Inversion de liste in-place",
                        "Code_Snippet": "def reverse_list(arr: list[int]) -> None:\n    # Comment inverser sans tableau temporaire ?\n    pass",
                        "Solution": "Utiliser deux pointeurs gauche/droite et échanger : `arr[l], arr[r] = arr[r], arr[l]`",
                        "Complexite": "O(N) temps, O(1) espace",
                        "Documentation": "https://docs.python.org",
                    }
                ],
            },
            {
                "id": "math_katex",
                "name": "Maths & KaTeX Minimal",
                "category": "Mathématiques & Sciences",
                "author": "AnkiForge Sciences",
                "version": "1.0.0",
                "description": "Rendu KaTeX épuré avec théorèmes encadrés, hypothèses et démonstrations pliables.",
                "fields_schema": ["Theoreme", "Enonce_Formule", "Hypotheses", "Demonstration"],
                "templates": [
                    {
                        "name": "Théorème Math",
                        "qfmt": """
<div class="math-card">
  <div class="math-badge">THÉORÈME</div>
  <div class="thm-name">{{Theoreme}}</div>
  <div class="hypo-box"><em>Hypothèses :</em> {{Hypotheses}}</div>
</div>
                        """.strip(),
                        "afmt": """
{{FrontSide}}
<hr id="answer">
<div class="math-body">
  <div class="formula-box">$${{Enonce_Formule}}$$</div>
  <details class="demo-box">
    <summary>Démonstration / Preuve</summary>
    <div>{{Demonstration}}</div>
  </details>
</div>
                        """.strip(),
                    }
                ],
                "css_style": """
.math-card { font-family: 'STIX Two Text', 'Latin Modern Math', serif; background: #fafafa; color: #1f2937; padding: 18px; border-radius: 8px; border: 1px solid #e5e7eb; }
.math-badge { display: inline-block; background: #4f46e5; color: white; padding: 2px 8px; border-radius: 4px; font-size: 10px; font-weight: bold; letter-spacing: 0.5px; }
.thm-name { font-size: 16px; font-weight: bold; margin-top: 8px; margin-bottom: 6px; }
.hypo-box { font-size: 13px; color: #4b5563; line-height: 1.5; }
.formula-box { background: #f3f4f6; border-radius: 6px; padding: 14px; text-align: center; font-size: 16px; margin: 12px 0; }
.demo-box { margin-top: 10px; font-size: 12px; color: #6b7280; }
                """.strip(),
                "demo_cards": [
                    {
                        "Theoreme": "Théorème Fondamental de l'Analyse",
                        "Enonce_Formule": "\\int_a^b f(t)\\,dt = F(b) - F(a)",
                        "Hypotheses": "Soit $f: [a, b] \\to \\mathbb{R}$ une fonction continue et $F$ une primitive de $f$.",
                        "Demonstration": "Par le théorème de la valeur moyenne et la continuité uniforme.",
                    }
                ],
            },
            {
                "id": "vocab_languages",
                "name": "Vocabulaire & Langues Étrangères",
                "category": "Langues & Vocabulaire",
                "author": "AnkiForge Polyglot",
                "version": "1.0.0",
                "description": "Cartes de langues avec transcription phonétique IPA, classe grammaticale, phrase d'exemple et note culturelle.",
                "fields_schema": ["Mot_Etranger", "Phonetique", "Traduction", "Classe_Grammaticale", "Exemple_Phrase", "Traduction_Exemple"],
                "templates": [
                    {
                        "name": "Vocabulaire",
                        "qfmt": """
<div class="lang-card">
  <div class="word-main">{{Mot_Etranger}}</div>
  <div class="ipa">{{Phonetique}}</div>
  <div class="pos-tag">{{Classe_Grammaticale}}</div>
</div>
                        """.strip(),
                        "afmt": """
{{FrontSide}}
<hr id="answer">
<div class="lang-ans">
  <div class="trans-main">{{Traduction}}</div>
  <div class="example-box">
    <p class="ex-foreign">« {{Exemple_Phrase}} »</p>
    <p class="ex-native">« {{Traduction_Exemple}} »</p>
  </div>
</div>
                        """.strip(),
                    }
                ],
                "css_style": """
.lang-card { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; text-align: center; padding: 20px; background: #ffffff; color: #111827; border-radius: 12px; }
.word-main { font-size: 24px; font-weight: 700; color: #1e3a8a; }
.ipa { font-size: 14px; color: #6b7280; font-family: monospace; margin-top: 4px; }
.pos-tag { display: inline-block; background: #e0e7ff; color: #3730a3; padding: 2px 10px; border-radius: 9999px; font-size: 11px; font-weight: 600; margin-top: 8px; }
.trans-main { font-size: 18px; font-weight: 600; color: #047857; margin-bottom: 12px; }
.example-box { background: #f9fafb; border-left: 3px solid #6366f1; padding: 10px 14px; border-radius: 6px; text-align: left; font-size: 13px; }
.ex-foreign { font-style: italic; color: #374151; margin: 0 0 4px 0; }
.ex-native { color: #6b7280; margin: 0; }
                """.strip(),
                "demo_cards": [
                    {
                        "Mot_Etranger": "Serendipity",
                        "Phonetique": "/ˌser.ənˈdɪp.ə.t̬i/",
                        "Traduction": "Sérendipité (découverte heureuse et imprévue)",
                        "Classe_Grammaticale": "Nom féminin",
                        "Exemple_Phrase": "Finding this rare book was pure serendipity.",
                        "Traduction_Exemple": "Trouver ce livre rare était un pur coup de chance.",
                    }
                ],
            },
        ]

    @classmethod
    def install_starter_pack(cls, pack_id: str, overwrite: bool = False) -> NoteTypeModel | None:
        """Installe un modèle du starter pack par son identifiant unique."""
        packs = {p["id"]: p for p in cls.get_starter_pack_models()}
        pack = packs.get(pack_id)
        if not pack:
            return None

        model, _ = cls.save_model_to_db(pack, overwrite_existing=overwrite)
        return model
