# Matrice de Couverture : Codebase ➔ Documentation Zensical 🗺️

Cette matrice permet à l'agent d'identifier en un coup d'œil les modules applicatifs dont la documentation est manquante, incomplète ou obsolète.

---

## 📊 Tableau de Correspondance Fonctionnelle

| Module Codebase (`src/ankiforge/`) | Page Doc (`docs/`) | Statut | Opportunités d'Améliorations Proactives |
| :--- | :--- | :---: | :--- |
| `services/ai/orchestrator.py` | `features/dag_et_rag.md` | ✅ Complet | Diagramme `stateDiagram` des sauts conditionnels on_success/on_failure ajouté (2026-09). |
| `services/ai/mcp_server.py`, `consultant_engine.py` | `features/consultant_mcp.md` + `guides/catalogue_outils_mcp.md` | ✅ Complet | Catalogue exhaustif des 29 outils MCP, 4 ressources et 3 prompts désormais documenté. |
| `services/ai/personas/`, `ui/views/agents_view/` | `features/personas_et_agents.md` | ✅ Complet | Ajouter un guide de snippets Jinja2 et des exemples de personas pour différentes filières. |
| `services/batch/` | `features/ab_testing.md` | ✅ Complet | Documenter les 3 modes (Modèle, Prompt, Pipeline) et la lecture de la bannière de KPIs. |
| `services/cards/linter.py`, `analysis_view.py` | `features/linter_wozniak.md` | ✅ Complet | Ajouter des exemples avant/après pour chacune des 20 règles de formulation de Wozniak. |
| `services/cards/merge.py`, `importers/` | `features/synchro_smart_merge.md` | ✅ Complet | Schématiser le dialogue de fusion 3-panneaux et expliciter les critères stricts de conflit. |
| `services/documents/`, `services/rag/` | `features/hub_multimodal.md` | ✅ Complet | Support Jupyter (`.ipynb`), Python (`.py`), EPUB et rendu JS Web documenté (2026-09). |
| `ui/components/katex_editor.py`, `cloze_manager.py` | `features/editeur_notes_katex.md` | ✅ Complet | Ajouter un tableau des raccourcis clavier pour les occlusions `{{c1::...}}` et formules KaTeX. |
| `services/tts/` | `features/tts_audio.md` | ✅ Complet | Préciser les voix Edge-TTS multilingues et le cache local des fichiers audio. |
| `database/models/` (30 modèles) | `Dossier_architecture/03_modele_donnees_synchro.md` | ✅ Complet | Diagramme du cycle de vie Note → Card → Flashcard ajouté (2026-09). |
| `services/ai/retry.py`, `flexible_service.py` | `guides/ia_fournisseurs.md` | ✅ Complet | Résilience (retry, 429), télémétrie et catalogue de modèles actualisés (2026-09). |
| `ui/theme.py`, `StyleEngine` | `guides/design_system.md` | ✅ Complet | Illustrer la matrice des 12 familles de thèmes bivalentes et les tokens d'accessibilité WCAG. |
| `build_script/`, Nuitka | `dev/compilation_nuitka.md` | ✅ Complet | Spécifier les particularités de compilation par OS (macOS `.dmg`, Linux `.AppImage`, Windows `.exe`). |
| `.agents/skills/` (15 skills) | `Dossier_architecture/09_qualite_et_deploiement.md` | 🔄 Partiel | Créer une page dédiée `docs/dev/architecture_skills_agents.md` (Antigravity / Progressive Disclosure). |

---

## 🎯 Pistes Prioritaires de Nouvelles Pages à Proposer

> ✅ **Fait en 2026-09** : `docs/guides/catalogue_outils_mcp.md` (29 outils MCP) et `docs/guides/faq_depannage.md` (Ollama, Marker, SQLite verrouillée, secrets) ont été créés et référencés dans `zensical.toml`.

1. **`docs/dev/architecture_skills_agents.md` (Architecture des Skills & Agents)** :
   - Présentation de la philosophie Antigravity / Progressive Disclosure dans AnkiForge.
   - Comment concevoir, tester et auditer un nouveau skill.

2. **`docs/guides/guide_jinja2_personas.md` (Snippets de prompts & personas par filière)** :
   - Extraits de templates Jinja2 réutilisables et cas d'usage concrets (médecine, droit, langues, code).
