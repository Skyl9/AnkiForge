"""
Bibliothèque de Snippets Modulaires et Résolveur de Conflits CSS pour l'Atelier de Modèles de Cartes.
Pilier 3 d'AnkiForge : Composants réutilisables HTML/CSS, détection AST/Regex et arbitrage de collisions.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from ankiforge.utils.paths import get_app_data_dir

logger = logging.getLogger(__name__)


@dataclass
class SnippetItem:
    """Représente un composant visuel modulaire réutilisable."""

    id: str
    name: str
    category: str
    description: str
    icon_name: str
    html_template: str
    css_style: str
    preview_html: str = ""
    tags: List[str] = field(default_factory=list)
    is_custom: bool = False


class SnippetLibrary:
    """Catalogue des snippets HTML/CSS préconfigurés et personnalisés pour les modèles de cartes AnkiForge."""

    @classmethod
    def get_builtin_snippets(cls) -> List[SnippetItem]:
        return [
            # --- 1. CALLOUTS & REMARQUES ---
            SnippetItem(
                id="callout_info",
                name="Encadré Info (Bleu)",
                category="Callouts & Remarques",
                description="Encadré sobre et élégant pour les remarques et informations clés.",
                icon_name="ph.info",
                html_template='<div class="af-callout af-callout-info">\n  <div class="af-callout-title">Information</div>\n  <div class="af-callout-content">\n    {{Remarque}}\n  </div>\n</div>',
                css_style=""".af-callout {
  margin: 14px 0;
  padding: 12px 16px;
  border-radius: 8px;
  text-align: left;
  font-size: 15px;
  line-height: 1.5;
}
.af-callout-info {
  background-color: rgba(59, 130, 246, 0.10);
  border-left: 4px solid #3b82f6;
  color: #1e293b;
}
.nightMode .af-callout-info {
  background-color: rgba(59, 130, 246, 0.15);
  color: #e2e8f0;
}
.af-callout-title {
  font-weight: 700;
  margin-bottom: 4px;
  font-size: 14px;
}""",
                tags=["callout", "info", "remarque"],
            ),
            SnippetItem(
                id="callout_warning",
                name="Encadré Attention (Ambre)",
                category="Callouts & Remarques",
                description="Encadré d'alerte pour les pièges et exceptions à retenir.",
                icon_name="ph.warning",
                html_template=(
                    '<div class="af-callout af-callout-warning">\n  <div class="af-callout-title">Attention / Piège</div>\n  <div class="af-callout-content">\n    {{Piege}}\n  </div>\n</div>'
                ),
                css_style=""".af-callout-warning {
  background-color: rgba(245, 158, 11, 0.10);
  border-left: 4px solid #f59e0b;
  color: #1e293b;
}
.nightMode .af-callout-warning {
  background-color: rgba(245, 158, 11, 0.15);
  color: #e2e8f0;
}""",
                tags=["callout", "warning", "piege"],
            ),
            SnippetItem(
                id="callout_danger",
                name="Encadré Erreur Fréquente (Rouge)",
                category="Callouts & Remarques",
                description="Encadré pour signaler les confusions classiques.",
                icon_name="ph.x-circle",
                html_template=(
                    '<div class="af-callout af-callout-danger">\n  <div class="af-callout-title">Ne pas confondre</div>\n  <div class="af-callout-content">\n    {{Erreur_A_Eviter}}\n  </div>\n</div>'
                ),
                css_style=""".af-callout-danger {
  background-color: rgba(239, 68, 68, 0.10);
  border-left: 4px solid #ef4444;
  color: #1e293b;
}
.nightMode .af-callout-danger {
  background-color: rgba(239, 68, 68, 0.15);
  color: #e2e8f0;
}""",
                tags=["callout", "danger", "erreur"],
            ),
            SnippetItem(
                id="callout_tip",
                name="Encadré Astuce & Mnémotechnique (Vert)",
                category="Callouts & Remarques",
                description="Encadré pour astuces mémorielles et mnémotechniques.",
                icon_name="ph.lightbulb",
                html_template=(
                    '<div class="af-callout af-callout-tip">\n  <div class="af-callout-title">Moyen Mnémotechnique</div>\n  <div class="af-callout-content">\n    {{Mnemotechnique}}\n  </div>\n</div>'
                ),
                css_style=""".af-callout-tip {
  background-color: rgba(16, 185, 129, 0.10);
  border-left: 4px solid #10b981;
  color: #1e293b;
}
.nightMode .af-callout-tip {
  background-color: rgba(16, 185, 129, 0.15);
  color: #e2e8f0;
}""",
                tags=["callout", "astuce", "mnemo"],
            ),
            SnippetItem(
                id="callout_theorem",
                name="Encadré Théorème / Définition (Violet)",
                category="Callouts & Remarques",
                description="Encadré sobre et formel pour théorèmes, lois et définitions.",
                icon_name="ph.bookmark-simple",
                html_template=(
                    '<div class="af-callout af-callout-theorem">\n  <div class="af-callout-title">Définition / Théorème</div>\n  <div class="af-callout-content">\n    {{Definition}}\n  </div>\n</div>'
                ),
                css_style=""".af-callout-theorem {
  background-color: rgba(139, 92, 246, 0.10);
  border-left: 4px solid #8b5cf6;
  color: #1e293b;
}
.nightMode .af-callout-theorem {
  background-color: rgba(139, 92, 246, 0.15);
  color: #e2e8f0;
}""",
                tags=["callout", "theoreme", "definition", "math"],
            ),
            # --- 2. BADGES & ÉTIQUETTES ---
            SnippetItem(
                id="badge_difficulty",
                name="Badge Niveau de Difficulté",
                category="Badges & Étiquettes",
                description="Pilule de niveau de difficulté (Facile, Moyen, Difficile).",
                icon_name="ph.star",
                html_template='<span class="af-badge af-badge-diff-moyen">Niveau : Moyen</span>',
                css_style=""".af-badge {
  display: inline-block;
  padding: 3px 10px;
  border-radius: 9999px;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.3px;
  margin-bottom: 8px;
}
.af-badge-diff-facile {
  background-color: rgba(16, 185, 129, 0.15);
  color: #10b981;
  border: 1px solid rgba(16, 185, 129, 0.3);
}
.af-badge-diff-moyen {
  background-color: rgba(245, 158, 11, 0.15);
  color: #f59e0b;
  border: 1px solid rgba(245, 158, 11, 0.3);
}
.af-badge-diff-difficile {
  background-color: rgba(239, 68, 68, 0.15);
  color: #ef4444;
  border: 1px solid rgba(239, 68, 68, 0.3);
}""",
                tags=["badge", "difficulte", "niveau"],
            ),
            SnippetItem(
                id="badge_exam",
                name="Badge Examen / Concours",
                category="Badges & Étiquettes",
                description="Badge doré pour les notions indispensables aux concours.",
                icon_name="ph.trophy",
                html_template='<span class="af-badge af-badge-exam">Notion Concours</span>',
                css_style=""".af-badge-exam {
  background-color: rgba(234, 179, 8, 0.15);
  color: #eab308;
  border: 1px solid rgba(234, 179, 8, 0.4);
}""",
                tags=["badge", "concours", "examen"],
            ),
            # --- 3. QCM & CHOIX MULTIPLES ---
            SnippetItem(
                id="qcm_options",
                name="Grille de Propositions QCM (A, B, C, D)",
                category="QCM & Choix Multiples",
                description="Mise en page structurée en 4 propositions distinctes.",
                icon_name="ph.list-checks",
                html_template=(
                    '<div class="af-qcm-container">\n'
                    '  <div class="af-qcm-option"><span class="af-qcm-letter">A</span> {{Choix_A}}</div>\n'
                    '  <div class="af-qcm-option"><span class="af-qcm-letter">B</span> {{Choix_B}}</div>\n'
                    '  <div class="af-qcm-option"><span class="af-qcm-letter">C</span> {{Choix_C}}</div>\n'
                    '  <div class="af-qcm-option"><span class="af-qcm-letter">D</span> {{Choix_D}}</div>\n'
                    "</div>"
                ),
                css_style=""".af-qcm-container {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin: 14px 0;
  text-align: left;
}
.af-qcm-option {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
  border-radius: 6px;
  background-color: rgba(100, 116, 139, 0.08);
  border: 1px solid rgba(100, 116, 139, 0.2);
  font-size: 14px;
}
.nightMode .af-qcm-option {
  background-color: rgba(255, 255, 255, 0.05);
  border-color: rgba(255, 255, 255, 0.12);
}
.af-qcm-letter {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border-radius: 4px;
  background-color: #6366f1;
  color: #ffffff;
  font-weight: 700;
  font-size: 12px;
}""",
                tags=["qcm", "choix", "options"],
            ),
            # --- 4. FORMULES MATHÉMATIQUES KATEX ---
            SnippetItem(
                id="math_block",
                name="Cadre Formule Mathématique KaTeX",
                category="KaTeX & Mathématiques",
                description="Cadre centré pour équations et théorèmes avec numérotation.",
                icon_name="ph.function",
                html_template=(
                    '<div class="af-math-box">\n  <div class="af-math-formula">\\[ {{Formule_LaTeX}} \\]</div>\n  <div class="af-math-caption">Équation (1) : {{Nom_Formule}}</div>\n</div>'
                ),
                css_style=""".af-math-box {
  margin: 16px 0;
  padding: 14px;
  border-radius: 8px;
  background: rgba(99, 102, 241, 0.06);
  border: 1px solid rgba(99, 102, 241, 0.25);
  text-align: center;
}
.af-math-formula {
  font-size: 18px;
  margin-bottom: 6px;
}
.af-math-caption {
  font-size: 12px;
  color: #64748b;
  font-style: italic;
}
.nightMode .af-math-caption {
  color: #94a3b8;
}""",
                tags=["math", "katex", "formule", "latex"],
            ),
            # --- 5. CODE DÉVELOPPEUR ---
            SnippetItem(
                id="code_card",
                name="Bloc Code Développeur (JetBrains Mono)",
                category="Code Développeur",
                description="Bloc de code sombre avec en-tête et étiquette de langage.",
                icon_name="ph.code",
                html_template=(
                    '<div class="af-code-card">\n'
                    '  <div class="af-code-header">\n'
                    '    <span class="af-code-lang">Python</span>\n'
                    '    <span class="af-code-title">{{Titre_Code}}</span>\n'
                    "  </div>\n"
                    '  <pre class="af-code-body"><code>{{Extrait_Code}}</code></pre>\n'
                    "</div>"
                ),
                css_style=""".af-code-card {
  margin: 14px 0;
  border-radius: 8px;
  background-color: #0f172a;
  border: 1px solid #334155;
  overflow: hidden;
  text-align: left;
}
.af-code-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 12px;
  background-color: #1e293b;
  border-bottom: 1px solid #334155;
  font-size: 11px;
  color: #94a3b8;
}
.af-code-lang {
  font-weight: 700;
  color: #38bdf8;
  text-transform: uppercase;
}
.af-code-body {
  margin: 0;
  padding: 12px;
  font-family: 'JetBrains Mono', 'Fira Code', monospace;
  font-size: 13px;
  line-height: 1.5;
  color: #e2e8f0;
  overflow-x: auto;
}""",
                tags=["code", "developer", "syntaxe"],
            ),
        ]

    @classmethod
    def _get_storage_file(cls) -> Path:
        """Retourne le chemin vers le fichier de persistance des snippets personnalisés."""
        app_dir = get_app_data_dir()
        app_dir.mkdir(parents=True, exist_ok=True)
        return app_dir / "custom_snippets.json"

    @classmethod
    def get_custom_snippets(cls) -> List[SnippetItem]:
        """Charge la liste des snippets personnalisés depuis le stockage JSON."""
        file_path = cls._get_storage_file()
        if not file_path.exists():
            return []
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, list):
                return []
            result: List[SnippetItem] = []
            for item in data:
                result.append(
                    SnippetItem(
                        id=item.get("id", ""),
                        name=item.get("name", "Sans nom"),
                        category=item.get("category", "Personnalisé"),
                        description=item.get("description", ""),
                        icon_name=item.get("icon_name", "ph.sparkle"),
                        html_template=item.get("html_template", ""),
                        css_style=item.get("css_style", ""),
                        preview_html=item.get("preview_html", ""),
                        tags=item.get("tags", []),
                        is_custom=True,
                    )
                )
            return result
        except Exception as e:
            logger.warning("Erreur lors de la lecture des snippets personnalisés: %s", e)
            return []

    @classmethod
    def get_all_snippets(cls) -> List[SnippetItem]:
        """Retourne l'ensemble des snippets (intégrés + personnalisés)."""
        builtins = cls.get_builtin_snippets()
        customs = cls.get_custom_snippets()

        # Remplacement des built-ins modifiés par l'utilisateur
        custom_dict = {c.id: c for c in customs}
        result: List[SnippetItem] = []
        for b in builtins:
            if b.id in custom_dict:
                result.append(custom_dict.pop(b.id))
            else:
                result.append(b)
        # Ajout des nouveaux snippets personnalisés
        result.extend(custom_dict.values())
        return result

    @classmethod
    def save_snippet(cls, snippet: SnippetItem) -> None:
        """Sauvegarde ou met à jour un snippet dans le fichier custom_snippets.json."""
        snippet.is_custom = True
        customs = cls.get_custom_snippets()

        # Vérifier si déjà présent
        found = False
        for idx, s in enumerate(customs):
            if s.id == snippet.id:
                customs[idx] = snippet
                found = True
                break
        if not found:
            customs.append(snippet)

        file_path = cls._get_storage_file()
        try:
            serialized = [asdict(s) for s in customs]
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(serialized, f, indent=2, ensure_ascii=False)
            logger.info("Snippet modulaire '%s' (%s) enregistré avec succès.", snippet.name, snippet.id)
        except Exception as e:
            logger.error("Impossible d'enregistrer le snippet custom: %s", e)
            raise

    @classmethod
    def delete_snippet(cls, snippet_id: str) -> bool:
        """Supprime un snippet personnalisé."""
        customs = cls.get_custom_snippets()
        initial_len = len(customs)
        customs = [s for s in customs if s.id != snippet_id]
        if len(customs) == initial_len:
            return False

        file_path = cls._get_storage_file()
        try:
            serialized = [asdict(s) for s in customs]
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(serialized, f, indent=2, ensure_ascii=False)
            logger.info("Snippet modulaire '%s' supprimé avec succès.", snippet_id)
            return True
        except Exception as e:
            logger.error("Erreur lors de la suppression du snippet: %s", e)
            return False

    @classmethod
    def create_custom_snippet(
        cls,
        name: str,
        category: str,
        description: str,
        icon_name: str,
        html_template: str,
        css_style: str,
        tags: Optional[List[str]] = None,
    ) -> SnippetItem:
        """Crée et enregistre un nouveau snippet personnalisé."""
        snippet_id = f"custom_{uuid.uuid4().hex[:8]}"
        snippet = SnippetItem(
            id=snippet_id,
            name=name,
            category=category or "Personnalisé",
            description=description,
            icon_name=icon_name or "ph.sparkle",
            html_template=html_template,
            css_style=css_style,
            tags=tags or [],
            is_custom=True,
        )
        cls.save_snippet(snippet)
        return snippet

    @classmethod
    def get_categories(cls) -> List[str]:
        snippets = cls.get_all_snippets()
        categories: List[str] = []
        for s in snippets:
            if s.category not in categories:
                categories.append(s.category)
        return categories

    @classmethod
    def get_by_category(cls, category: str) -> List[SnippetItem]:
        return [s for s in cls.get_all_snippets() if s.category == category]

    @classmethod
    def get_by_id(cls, snippet_id: str) -> Optional[SnippetItem]:
        for s in cls.get_all_snippets():
            if s.id == snippet_id:
                return s
        return None


class CSSConflictResolver:
    """Analyseur de sélecteurs CSS et moteur de résolution des collisions."""

    _CLASS_SELECTOR_REGEX = re.compile(r"\.([a-zA-Z0-9_\-]+)\s*(?:\{|:|,|\s|\.|>)")

    @classmethod
    def extract_classes(cls, css_text: str) -> set[str]:
        """Extrait l'ensemble des noms de classes CSS définies dans un bloc CSS."""
        if not css_text:
            return set()
        matches = cls._CLASS_SELECTOR_REGEX.findall(css_text)
        # Filtrer les pseudo-classes et pseudos-éléments courants
        ignored = {"nightMode", "card", "cloze"}
        return {m for m in matches if m not in ignored}

    @classmethod
    def find_conflicts(cls, existing_css: str, new_css: str) -> List[str]:
        """Retourne la liste des classes CSS en collision entre l'existant et le nouveau CSS."""
        existing_classes = cls.extract_classes(existing_css)
        new_classes = cls.extract_classes(new_css)
        conflicts = list(existing_classes.intersection(new_classes))
        conflicts.sort()
        return conflicts

    @classmethod
    def rename_classes(cls, html: str, css: str, class_mapping: Dict[str, str]) -> Tuple[str, str]:
        """Renomme les classes CSS en collision dans le HTML et le CSS fourni."""
        renamed_html = html
        renamed_css = css

        # Trier les clés par longueur décroissante pour éviter que .af-callout ne remplace .af-callout-info
        sorted_classes = sorted(class_mapping.keys(), key=len, reverse=True)

        for old_class in sorted_classes:
            new_class = class_mapping[old_class]
            # Remplacement dans le CSS (sélecteur .old_class)
            css_pattern = re.compile(rf"\.{re.escape(old_class)}(?![a-zA-Z0-9_\-])")
            renamed_css = css_pattern.sub(f".{new_class}", renamed_css)

            # Remplacement dans le HTML (nom de classe strict)
            html_pattern = re.compile(rf"(?<![a-zA-Z0-9_\-]){re.escape(old_class)}(?![a-zA-Z0-9_\-])")
            renamed_html = html_pattern.sub(new_class, renamed_html)

        return renamed_html, renamed_css

    @classmethod
    def merge_css(cls, existing_css: str, new_css: str, strategy: str = "append", replace_classes: Optional[List[str]] = None) -> str:
        """Fusionne le nouveau CSS avec l'existant selon la stratégie demandée."""
        if not new_css.strip():
            return existing_css

        if strategy == "replace" and replace_classes:
            # Remplacer les blocs de règles existants contenant les classes en collision
            updated_css = existing_css
            for cls_name in replace_classes:
                # Regex pour supprimer le bloc .cls_name { ... }
                pattern = re.compile(rf"\.{re.escape(cls_name)}\s*\{{[^}}]*\}}\n*", re.MULTILINE)
                updated_css = pattern.sub("", updated_css)
            return (updated_css.rstrip() + "\n\n" + new_css.strip()).strip()

        # Stratégie append par défaut
        if not existing_css.strip():
            return new_css.strip()

        return f"{existing_css.rstrip()}\n\n/* --- Snippet Ajouté --- */\n{new_css.strip()}"
