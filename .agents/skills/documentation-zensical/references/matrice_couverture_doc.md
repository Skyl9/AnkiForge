# Matrice de Couverture : Codebase ➔ Documentation Zensical 🗺️

Cette matrice permet à l'agent d'identifier en un coup d'œil les modules applicatifs dont la documentation est manquante, incomplète ou obsolète.

---

## 📊 Tableau de Correspondance Fonctionnelle

| Module Codebase (`src/ankiforge/`) | Page Doc (`docs/`) | Statut | Opportunités d'Améliorations Proactives |
| :--- | :--- | :---: | :--- |
| `services/ai/orchestrator.py` | `features/dag_et_rag.md` | ✅ Complet | Ajouter un diagramme Mermaid des 5 types d'étapes et de la pause `HUMAN_VALIDATION`. |
| `services/ai/mcp_server.py`, `consultant_engine.py` | `features/consultant_mcp.md` | 🔄 Partiel | Documenter le catalogue exhaustif des 24 outils MCP et la boucle ReAct multi-étapes. |
| `services/ai/personas/`, `ui/views/agents_view/` | `features/personas_et_agents.md` | ✅ Complet | Ajouter un guide de snippets Jinja2 et des exemples de personas pour différentes filières. |
| `services/batch/` | `features/ab_testing.md` | ✅ Complet | Documenter les 3 modes (Modèle, Prompt, Pipeline) et la lecture de la bannière de KPIs. |
| `services/cards/linter.py`, `analysis_view.py` | `features/linter_wozniak.md` | ✅ Complet | Ajouter des exemples avant/après pour chacune des 20 règles de formulation de Wozniak. |
| `services/cards/merge.py`, `importers/` | `features/synchro_smart_merge.md` | ✅ Complet | Schématiser le dialogue de fusion 3-panneaux et expliciter les critères stricts de conflit. |
| `services/documents/`, `services/rag/` | `features/hub_multimodal.md` | 🔄 Partiel | Documenter le support des Notebooks Jupyter (`.ipynb`), scripts `.py`, et du Web Importer avec rendu JS. |
| `ui/components/katex_editor.py`, `cloze_manager.py` | `features/editeur_notes_katex.md` | ✅ Complet | Ajouter un tableau des raccourcis clavier pour les occlusions `{{c1::...}}` et formules KaTeX. |
| `services/tts/` | `features/tts_audio.md` | ✅ Complet | Préciser les voix Edge-TTS multilingues et le cache local des fichiers audio. |
| `database/models/` (30 modèles) | `Dossier_architecture/03_modele_donnees_synchro.md` | ✅ Complet | Maintenir la synchronisation des schémas et du diagramme de classes Mermaid. |
| `services/ai/retry.py`, `flexible_service.py` | `guides/ia_fournisseurs.md` | 🔄 Partiel | Documenter la résilience (retry exponentiel, rate-limits 429) et la configuration multi-fournisseurs. |
| `ui/theme.py`, `StyleEngine` | `guides/design_system.md` | ✅ Complet | Illustrer la matrice des 12 familles de thèmes bivalentes et les tokens d'accessibilité WCAG. |
| `build_script/`, Nuitka | `dev/compilation_nuitka.md` | ✅ Complet | Spécifier les particularités de compilation par OS (macOS `.dmg`, Linux `.AppImage`, Windows `.exe`). |
| `.agents/skills/` (14 skills) | `Dossier_architecture/09_qualite_et_deploiement.md` | ✅ Complet | Créer éventuellement une page dédiée aux agents et à l'architecture des skills. |

---

## 🎯 Pistes Prioritaires de Nouvelles Pages à Proposer

1. **`docs/guides/faq_depannage.md` (FAQ & Dépannage)** :
   - Problèmes courants de connexion Ollama local (`localhost:11434`).
   - Résolution des dépendances lourdes (Marker OCR, PyTorch).
   - Droits d'accès et déblocage de bases de données verrouillées SQLite.

2. **`docs/guides/catalogue_outils_mcp.md` (Guide Détaillé des 24 Outils MCP)** :
   - Fiches pratiques pour chaque outil : signature, arguments, exemple de retour, permissions requises.

3. **`docs/dev/architecture_skills_agents.md` (Architecture des Skills & Agents)** :
   - Présentation de la philosophie Antigravity / Progressive Disclosure dans AnkiForge.
   - Comment concevoir, tester et auditer un nouveau skill.
