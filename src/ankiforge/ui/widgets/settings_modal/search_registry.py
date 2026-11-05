"""Registre déclaratif des options de paramètres pour la recherche instantanée.

Le catalogue est statique et découplé des widgets réels : il indexe les libellés,
mots-clés, descriptions et chemin d'accès (Onglet > Section > Option) de chaque
réglage, permettant une recherche instantanée sans instancier les onglets
(chargement différé préservé).

Aucune couleur en dur : les teintes sémantiques sont consommées exclusivement via
``DesignTokens`` (voir ``src/ankiforge/ui/theme.py``).
"""

from __future__ import annotations

import logging
import unicodedata
from dataclasses import dataclass
from typing import ClassVar

logger = logging.getLogger(__name__)

# Poids de pertinence par champ lors du scoring de recherche.
_WEIGHT_LABEL = 3.0
_WEIGHT_KEYWORD = 2.0
_WEIGHT_DESCRIPTION = 1.0


@dataclass(frozen=True)
class SettingDescriptor:
    """Métadonnées d'un réglage indexable par le moteur de recherche.

    Attributes:
        key: Identifiant stable du réglage (ex: ``ui/language``).
        label: Libellé affiché à l'utilisateur.
        description: Description courte du réglage.
        keywords: Mots-clés associés pour élargir la correspondance.
        tab: Nom de l'onglet hôte (ex: ``Général``).
        section: Section de l'onglet (ex: ``Apparence & Interface``).
        widget: Nom du widget cible (ex: ``Langue de l'interface``).
        tab_index: Index de l'onglet dans le ``QStackedWidget`` du modal.
    """

    key: str
    label: str
    description: str
    keywords: tuple[str, ...]
    tab: str
    section: str
    widget: str
    tab_index: int


@dataclass(frozen=True)
class SettingSearchResult:
    """Résultat de recherche avec score de pertinence et champs appariés.

    Attributes:
        descriptor: Descripteur du réglage trouvé.
        score: Score de pertinence (plus élevé = plus pertinent).
        matched_fields: Noms des champs ayant contribué au match
            (``label``, ``description``, ``keywords``).
    """

    descriptor: SettingDescriptor
    score: float
    matched_fields: tuple[str, ...]


def _normalize(text: str) -> str:
    """Supprime les diacritiques et passe en minuscules (insensible à la casse/accents)."""
    decomposed = unicodedata.normalize("NFD", text)
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return stripped.casefold()


class SettingsRegistry:
    """Catalogue statique des options de paramètres indexables par recherche.

    L'instanciation est inutile : tous les membres sont des méthodes de classe
    opérant sur le tuple statique ``_DESCRIPTORS``.
    """

    _DESCRIPTORS: ClassVar[tuple[SettingDescriptor, ...]] = (
        # ── Onglet : Général (index 0) ────────────────────────────────────────
        SettingDescriptor(
            key="ui/layout",
            label="Disposition de l'interface",
            description="Choisit la coquille d'interface (IDE, Dashboard, Glassmorphism, macOS).",
            keywords=("layout", "disposition", "coquille", "ide", "dashboard", "macos", "glassmorphism"),
            tab="Général",
            section="Apparence & Interface",
            widget="Disposition de l'interface",
            tab_index=0,
        ),
        SettingDescriptor(
            key="ui/mode_source",
            label="Mode d'apparence",
            description="Définit si l'interface est sombre, claire ou suit le système.",
            keywords=("mode", "apparence", "sombre", "clair", "système", "dark", "light"),
            tab="Général",
            section="Apparence & Interface",
            widget="Mode d'apparence",
            tab_index=0,
        ),
        SettingDescriptor(
            key="ui/theme_family",
            label="Famille de thème",
            description="Sélectionne l'identité graphique parmi les 12 familles bivalentes.",
            keywords=("thème", "famille", "jetbrains", "nord", "dracula", "tokyo", "solarized", "catppuccin"),
            tab="Général",
            section="Apparence & Interface",
            widget="Famille de thème",
            tab_index=0,
        ),
        SettingDescriptor(
            key="ui/language",
            label="Langue de l'interface",
            description="Définit la langue utilisée par l'application (français ou anglais).",
            keywords=("langue", "language", "français", "anglais", "traduction", "i18n"),
            tab="Général",
            section="Éditeur & Affichage de Texte",
            widget="Langue de l'interface",
            tab_index=0,
        ),
        SettingDescriptor(
            key="editor/font_size",
            label="Taille de police de l'éditeur",
            description="Définit la taille de caractère des éditeurs de texte et de code.",
            keywords=("police", "taille", "éditeur", "caractère", "font", "size"),
            tab="Général",
            section="Éditeur & Affichage de Texte",
            widget="Taille de police de l'éditeur",
            tab_index=0,
        ),
        SettingDescriptor(
            key="editor/line_numbers",
            label="Afficher les numéros de ligne",
            description="Affiche ou masque les numéros de ligne dans les éditeurs.",
            keywords=("numéros", "ligne", "afficher", "éditeur", "gutter"),
            tab="Général",
            section="Éditeur & Affichage de Texte",
            widget="Numéros de ligne",
            tab_index=0,
        ),
        SettingDescriptor(
            key="editor/word_wrap",
            label="Retour à la ligne automatique",
            description="Active le retour à la ligne automatique dans les éditeurs de texte.",
            keywords=("retour", "ligne", "automatique", "word wrap", "éditeur"),
            tab="Général",
            section="Éditeur & Affichage de Texte",
            widget="Retour à la ligne automatique",
            tab_index=0,
        ),
        SettingDescriptor(
            key="app/export_path",
            label="Dossier d'exportation par défaut",
            description="Répertoire utilisé par défaut pour les exportations de paquets et collections.",
            keywords=("export", "dossier", "répertoire", "chemin", "par défaut", "paquet"),
            tab="Général",
            section="Dossiers & Chemins de Sortie",
            widget="Dossier d'exportation par défaut",
            tab_index=0,
        ),
        SettingDescriptor(
            key="app/auto_startup",
            label="Ouvrir l'espace par défaut au lancement",
            description="Ouvre automatiquement l'espace de travail par défaut sans demander au démarrage.",
            keywords=("démarrage", "lancement", "espace", "par défaut", "ouvrir", "automatique"),
            tab="Général",
            section="Espaces de Travail & Démarrage",
            widget="Ouvrir l'espace par défaut au lancement",
            tab_index=0,
        ),
        SettingDescriptor(
            key="app/default_profile",
            label="Profil par défaut",
            description="Sélectionne le profil SQLite isolé utilisé au lancement de l'application.",
            keywords=("profil", "par défaut", "espace de travail", "sqlite", "isolé"),
            tab="Général",
            section="Espaces de Travail & Démarrage",
            widget="Profil par défaut",
            tab_index=0,
        ),
        SettingDescriptor(
            key="app/confirm_on_exit",
            label="Demander confirmation avant de fermer",
            description="Affiche une demande de confirmation avant la fermeture de l'application.",
            keywords=("confirmation", "fermer", "quitter", "sortie", "demander"),
            tab="Général",
            section="Espaces de Travail & Démarrage",
            widget="Demander confirmation avant de fermer",
            tab_index=0,
        ),
        SettingDescriptor(
            key="app/autosave_interval",
            label="Intervalle d'enregistrement automatique",
            description="Périodicité (en secondes) de l'enregistrement automatique des paramètres.",
            keywords=("autosave", "enregistrement", "automatique", "intervalle", "secondes"),
            tab="Général",
            section="Espaces de Travail & Démarrage",
            widget="Intervalle d'enregistrement automatique",
            tab_index=0,
        ),
        SettingDescriptor(
            key="app/restore_last_project",
            label="Restaurer le dernier projet au lancement",
            description="Rouvre le dernier projet ouvert lors du démarrage de l'application.",
            keywords=("restaurer", "dernier", "projet", "lancement", "ouverture"),
            tab="Général",
            section="Espaces de Travail & Démarrage",
            widget="Restaurer le dernier projet au lancement",
            tab_index=0,
        ),
        SettingDescriptor(
            key="notifications/system_mode",
            label="Mode de notification",
            description="Définit le mode d'affichage des notifications système (système, dock, désactivé).",
            keywords=("notification", "système", "dock", "alerte", "mode"),
            tab="Général",
            section="Notifications & Alertes",
            widget="Mode de notification",
            tab_index=0,
        ),
        SettingDescriptor(
            key="updates/channel",
            label="Canal de mise à jour",
            description="Définit le canal de distribution (stable ou nightly) des nouvelles versions.",
            keywords=("mise à jour", "canal", "stable", "nightly", "version", "versioning"),
            tab="Général",
            section="À Propos & Mises à Jour",
            widget="Canal de mise à jour",
            tab_index=0,
        ),
        SettingDescriptor(
            key="updates/check_interval",
            label="Fréquence de vérification des mises à jour",
            description="Intervalle entre deux interrogations distantes de l'API de distribution.",
            keywords=("fréquence", "vérification", "intervalle", "mises à jour", "heures"),
            tab="Général",
            section="À Propos & Mises à Jour",
            widget="Fréquence de vérification des mises à jour",
            tab_index=0,
        ),
        SettingDescriptor(
            key="feedback/prompt_on_crash",
            label="Proposer de transmettre les rapports de crash",
            description="Invite l'utilisateur à envoyer les rapports de crash au démarrage après une fermeture anormale.",
            keywords=("crash", "rapport", "transmettre", "soutien", "feedback"),
            tab="Général",
            section="À Propos & Mises à Jour",
            widget="Rapport de crash au démarrage",
            tab_index=0,
        ),
        # ── Onglet : Moteurs IA (index 1) ─────────────────────────────────────
        SettingDescriptor(
            key="ai/providers",
            label="Fournisseurs de modèles IA",
            description="Configure les clés API et les fournisseurs (OpenAI, Gemini, Anthropic, Ollama, Groq).",
            keywords=("fournisseur", "clé", "api", "openai", "gemini", "anthropic", "ollama", "groq", "ia"),
            tab="Moteurs IA",
            section="Clés API & Fournisseurs",
            widget="Clés API par fournisseur",
            tab_index=1,
        ),
        SettingDescriptor(
            key="ai/temperature",
            label="Température d'inférence",
            description="Contrôle l'aléatoire des réponses générées par les modèles de langage.",
            keywords=("température", "inférence", "aléatoire", "llm", "génération"),
            tab="Moteurs IA",
            section="Réglages d'inférence",
            widget="Température",
            tab_index=1,
        ),
        SettingDescriptor(
            key="ai/max_tokens",
            label="Nombre maximal de tokens",
            description="Limite la longueur maximale des réponses générées par les modèles IA.",
            keywords=("tokens", "maximal", "longueur", "réponse", "llm"),
            tab="Moteurs IA",
            section="Réglages d'inférence",
            widget="Max tokens",
            tab_index=1,
        ),
        SettingDescriptor(
            key="ai/advanced_generation",
            label="Paramètres avancés de génération",
            description="Options fines de contrôle de la génération (top-p, top-k, pénalité de répétition).",
            keywords=("avancé", "génération", "top-p", "top-k", "pénalité", "répétition"),
            tab="Moteurs IA",
            section="Génération & RAG Avancés",
            widget="Génération avancée",
            tab_index=1,
        ),
        SettingDescriptor(
            key="ai/advanced_rag",
            label="Paramètres avancés de RAG",
            description="Configuration de l'indexation vectorielle et du découpage sémantique des documents.",
            keywords=("avancé", "rag", "vectoriel", "découpage", "chunks", "indexation"),
            tab="Moteurs IA",
            section="Génération & RAG Avancés",
            widget="RAG avancé",
            tab_index=1,
        ),
        # ── Onglet : Anki & Formats (index 2) ─────────────────────────────────
        SettingDescriptor(
            key="anki/conflict_policy",
            label="Politique de fusion des conflits",
            description="Définit la règle d'arbitrage lors d'un conflit de contenu à l'import (local, entrant, manuel).",
            keywords=("conflit", "fusion", "import", "smart merge", "politique", "local", "entrant"),
            tab="Anki & Formats",
            section="Smart Merge & Formats",
            widget="Politique de conflit",
            tab_index=2,
        ),
        SettingDescriptor(
            key="anki/silent_merge",
            label="Fusion silencieuse des métadonnées",
            description="Fusionne automatiquement les métadonnées sans intervention lors d'un import partiel.",
            keywords=("silencieux", "fusion", "métadonnées", "import", "automatique"),
            tab="Anki & Formats",
            section="Smart Merge & Formats",
            widget="Fusion silencieuse",
            tab_index=2,
        ),
        SettingDescriptor(
            key="anki/compression",
            label="Format de compression",
            description="Choisit l'algorithme de compression des médias exportés (zstd, zip, aucun).",
            keywords=("compression", "zstd", "zip", "médias", "export", "format"),
            tab="Anki & Formats",
            section="Smart Merge & Formats",
            widget="Format de compression",
            tab_index=2,
        ),
        SettingDescriptor(
            key="anki/collection_dir",
            label="Répertoire de collection Anki",
            description="Chemin vers le dossier contenant la collection Anki (.anki2) associée au profil.",
            keywords=("collection", "répertoire", "anki2", "chemin", "dossier", "profile"),
            tab="Anki & Formats",
            section="Collection Anki",
            widget="Répertoire de collection Anki",
            tab_index=2,
        ),
        # ── Onglet : Audio & TTS (index 3) ────────────────────────────────────
        SettingDescriptor(
            key="tts/engine",
            label="Moteur de synthèse vocale",
            description="Sélectionne le fournisseur TTS (Edge, Piper, Kokoro, Système).",
            keywords=("tts", "synthèse", "voix", "moteur", "edge", "piper", "kokoro", "système"),
            tab="Audio & TTS",
            section="Moteur TTS",
            widget="Moteur de synthèse vocale",
            tab_index=3,
        ),
        SettingDescriptor(
            key="tts/voice",
            label="Voix par défaut",
            description="Définit la voix utilisée pour la synthèse audio des cartes.",
            keywords=("voix", "par défaut", "tts", "audio", "langue"),
            tab="Audio & TTS",
            section="Moteur TTS",
            widget="Voix par défaut",
            tab_index=3,
        ),
        SettingDescriptor(
            key="tts/rate",
            label="Vitesse de lecture",
            description="Ajuste la cadence de lecture de la synthèse vocale (0.75x à 2.0x).",
            keywords=("vitesse", "lecture", "cadence", "tts", "audio"),
            tab="Audio & TTS",
            section="Moteur TTS",
            widget="Vitesse de lecture",
            tab_index=3,
        ),
        SettingDescriptor(
            key="tts/install_piper",
            label="Installer Piper",
            description="Télécharge et configure le binaire sidecar Piper pour la synthèse vocale locale.",
            keywords=("piper", "installer", "sidecar", "local", "binaire", "tts"),
            tab="Audio & TTS",
            section="Installation des moteurs",
            widget="Installer Piper",
            tab_index=3,
        ),
        SettingDescriptor(
            key="tts/install_kokoro",
            label="Installer Kokoro",
            description="Télécharge et configure le moteur Kokoro-82M pour la synthèse vocale locale.",
            keywords=("kokoro", "installer", "onnx", "modèles", "local", "tts"),
            tab="Audio & TTS",
            section="Installation des moteurs",
            widget="Installer Kokoro",
            tab_index=3,
        ),
        # ── Onglet : Maintenance (index 4) ────────────────────────────────────
        SettingDescriptor(
            key="maintenance/vacuum",
            label="VACUUM de la base SQLite",
            description="Réorganise et compacte la base de données SQLite pour libérer de l'espace.",
            keywords=("vacuum", "sqlite", "base", "compacte", "espace", "maintenance"),
            tab="Maintenance",
            section="Base de données",
            widget="VACUUM",
            tab_index=4,
        ),
        SettingDescriptor(
            key="maintenance/clean_orphan_media",
            label="Nettoyer les médias orphelins",
            description="Supprime les fichiers multimédias non référencés par aucune note ou carte.",
            keywords=("médias", "orphelins", "nettoyer", "supprimer", "fichiers", "maintenance"),
            tab="Maintenance",
            section="Médias",
            widget="Nettoyer les médias orphelins",
            tab_index=4,
        ),
        SettingDescriptor(
            key="maintenance/purge_history",
            label="Purger l'historique Time Machine",
            description="Supprime les versions anciennes de notes au-delà de la durée de rétention configurée.",
            keywords=("historique", "time machine", "purge", "versions", "rétention", "notes"),
            tab="Maintenance",
            section="Time Machine",
            widget="Purger l'historique",
            tab_index=4,
        ),
        SettingDescriptor(
            key="maintenance/snapshot",
            label="Créer un snapshot de sauvegarde",
            description="Génère un instantané de sécurité de la base de données avant toute opération de maintenance.",
            keywords=("snapshot", "sauvegarde", "instantané", "base de données", "sécurité"),
            tab="Maintenance",
            section="Time Machine",
            widget="Snapshot de sauvegarde",
            tab_index=4,
        ),
        SettingDescriptor(
            key="maintenance/purge_tts_cache",
            label="Purger le cache audio TTS",
            description="Supprime les fichiers audio mis en cache par la synthèse vocale.",
            keywords=("cache", "audio", "tts", "purger", "fichiers", "sons"),
            tab="Maintenance",
            section="Audio",
            widget="Purger le cache audio TTS",
            tab_index=4,
        ),
        # ── Onglet : Extensions (index 5) ─────────────────────────────────────
        SettingDescriptor(
            key="addons/list",
            label="Liste des extensions installées",
            description="Affiche et gère les addons et extensions actifs dans l'application.",
            keywords=("extension", "addon", "installé", "liste", "gestion", "plugin"),
            tab="Extensions",
            section="Extensions",
            widget="Liste des extensions",
            tab_index=5,
        ),
        SettingDescriptor(
            key="addons/config",
            label="Configuration d'une extension",
            description="Modifie les paramètres de configuration d'un addon sélectionné.",
            keywords=("configuration", "extension", "addon", "paramètres", "éditer"),
            tab="Extensions",
            section="Extensions",
            widget="Formulaire de configuration",
            tab_index=5,
        ),
        # ── Onglet : Soutien (index 6) ────────────────────────────────────────
        SettingDescriptor(
            key="support/dialog",
            label="Dialogue de soutien",
            description="Invite à contribuer au financement du projet via une plateforme tierce.",
            keywords=("soutien", "financement", "ko-fi", "don", "contribuer", "bénévole"),
            tab="Soutien",
            section="Soutien",
            widget="Dialogue de soutien",
            tab_index=6,
        ),
        SettingDescriptor(
            key="support/startup_reminder",
            label="Rappel de soutien au démarrage",
            description="Affiche le dialogue de soutien de façon temporisée lors du lancement.",
            keywords=("rappel", "démarrage", "lancement", "soutien", "temporisé"),
            tab="Soutien",
            section="Soutien",
            widget="Rappel au démarrage",
            tab_index=6,
        ),
        # ── Onglet : Clavier (index 7) ────────────────────────────────────────
        SettingDescriptor(
            key="keyboard/shortcuts",
            label="Raccourcis clavier",
            description="Consulte et personnalise les séquences de touches des actions de l'application.",
            keywords=("raccourci", "clavier", "touche", "séquence", "action", "keybind"),
            tab="Clavier",
            section="Raccourcis",
            widget="Catalogue de raccourcis",
            tab_index=7,
        ),
        SettingDescriptor(
            key="keyboard/override",
            label="Surcharge de raccourci utilisateur",
            description="Substitue une séquence personnalisée à la séquence par défaut d'une action.",
            keywords=("surcharge", "personnalisé", "remap", "raccourci", "utilisateur"),
            tab="Clavier",
            section="Raccourcis",
            widget="Surcharge de raccourci",
            tab_index=7,
        ),
        # ── Onglet : Aide & Guides (index 8) ──────────────────────────────────
        SettingDescriptor(
            key="help/doc_reader",
            label="Lecteur de documentation embarqué",
            description="Consulte les guides et la documentation officielle hors-ligne sans navigateur externe.",
            keywords=("documentation", "guide", "lecteur", "hors-ligne", "aide"),
            tab="Aide & Guides",
            section="Documentation",
            widget="Lecteur de documentation",
            tab_index=8,
        ),
        SettingDescriptor(
            key="help/lifecycle_guide",
            label="Guide visuel du cycle de vie distribué",
            description="Illustre l'articulation des sessions entre le Studio AnkiForge et Anki Desktop.",
            keywords=("cycle de vie", "distribué", "guide", "visuel", "anki", "studio"),
            tab="Aide & Guides",
            section="Documentation",
            widget="Guide du cycle de vie",
            tab_index=8,
        ),
        # ── Onglet : Développeur (index 9) ────────────────────────────────────
        SettingDescriptor(
            key="dev/widget_gallery",
            label="Galerie de widgets (mode développeur)",
            description="Observe visuellement l'ensemble des widgets alimentés par des données factices déterministes.",
            keywords=("galerie", "widgets", "développeur", "mock", "factice", "ui"),
            tab="Développeur",
            section="Outils de développement",
            widget="Galerie de widgets",
            tab_index=9,
        ),
        SettingDescriptor(
            key="dev/mcp_server",
            label="Serveur MCP persistant",
            description="Pilote le cycle de vie du serveur MCP in-process et ses points de terminaison (SSE, Streamable HTTP).",
            keywords=("mcp", "serveur", "daemon", "sse", "http", "jeton", "bearer"),
            tab="Développeur",
            section="MCP & Agents externes",
            widget="Supervision MCP",
            tab_index=9,
        ),
    )

    @classmethod
    def all_settings(cls) -> tuple[SettingDescriptor, ...]:
        """Renvoie l'ensemble des descripteurs de réglages indexés."""
        return cls._DESCRIPTORS

    @classmethod
    def search(cls, query: str) -> list[SettingSearchResult]:
        """Recherche des réglages correspondant à la requête.

        La recherche est insensible à la casse et aux accents. Un résultat est retenu
        dès qu'un terme de la requête apparaît dans le libellé, la description ou
        l'un des mots-clés.

        Args:
            query: Saisie utilisateur (mot-clé ou phrase).

        Returns:
            Liste de résultats triée par pertinence décroissante, puis par onglet.
        """
        normalized = _normalize(query).strip()
        if not normalized:
            return []

        terms = [term for term in normalized.split() if term]
        if not terms:
            return []

        results: list[SettingSearchResult] = []
        for descriptor in cls._DESCRIPTORS:
            score, matched = cls._score_descriptor(descriptor, terms)
            if score > 0.0:
                results.append(SettingSearchResult(descriptor=descriptor, score=score, matched_fields=matched))

        results.sort(
            key=lambda result: (
                -result.score,
                result.descriptor.tab_index,
                result.descriptor.section,
                result.descriptor.label,
            )
        )
        logger.debug("Recherche « %s » : %d résultat(s)", query, len(results))
        return results

    @staticmethod
    def _score_descriptor(descriptor: SettingDescriptor, terms: list[str]) -> tuple[float, tuple[str, ...]]:
        """Calcule le score de pertinence et les champs appariés pour un descripteur."""
        label_norm = _normalize(descriptor.label)
        desc_norm = _normalize(descriptor.description)
        keywords_norm = [_normalize(kw) for kw in descriptor.keywords]

        matched: set[str] = set()
        score = 0.0

        for term in terms:
            if term in label_norm:
                score += _WEIGHT_LABEL
                matched.add("label")
            for keyword in keywords_norm:
                if term in keyword:
                    score += _WEIGHT_KEYWORD
                    matched.add("keywords")
                    break
            if term in desc_norm:
                score += _WEIGHT_DESCRIPTION
                matched.add("description")

        return score, tuple(sorted(matched))
