import re

with open("ankiforge_implementation_plan.md", "r") as f:
    content = f.read()

# 1. Architecture Cible (Mermaid)
content = content.replace(
    'F1["4.1 Multi-Profils"]\n        F2["4.2 Synchro Anki<br/>+ Merge Dialog"]\n        F3["4.3 YouTube Parsing"]\n        F4["4.4 Éditeur KaTeX<br/>+ IntelliSense"]',
    'F1["4.1 Multi-Profils"]\n        F2["4.2 YouTube Parsing"]\n        F3["4.3 Éditeur KaTeX<br/>+ IntelliSense"]',
)
content = content.replace("M1 & M2 & M3 --> F1 & F2 & F3 & F4\n    F1 & F2 & F3 & F4 --> Q1 --> Q2", "M1 & M2 & M3 --> F1 & F2 & F3\n    F1 & F2 & F3 --> Q1 --> Q2")

# 2. Arborescence Cible
content = re.sub(r"│   ├── sync/.*?│   ├── profile_manager\.py", r"│   ├── profile_manager.py", content, flags=re.DOTALL)
content = re.sub(r"│       ├── sync_worker\.py               # 🆕 CRÉER\n", r"", content)
content = re.sub(r"│   │   ├── merge_dialog\.py              # 🆕 CRÉER \(3 panneaux IntelliJ\)\n", r"", content)

# 3. Rename task numbers
content = content.replace("4.3 YouTube Parsing", "4.2 YouTube Parsing")
content = content.replace("4.4 Éditeur KaTeX+ IntelliSense", "4.3 Éditeur KaTeX+ IntelliSense")
content = content.replace("Tâche 4.3 — YouTube", "Tâche 4.2 — YouTube")
content = content.replace("Tâche 4.4 — Éditeur", "Tâche 4.3 — Éditeur")

# 4. Remove Tâche 4.2 Sync block
content = re.sub(r"### 📋 Tâche 4\.2 — Synchro Anki \+ Merge Dialog.*?### 📋 Tâche 4\.2 — YouTube Parsing", r"### 📋 Tâche 4.2 — YouTube Parsing", content, flags=re.DOTALL)

# 5. Tests
content = re.sub(r"│   ├── test_sync_engine\.py        # Sync logic, conflict detection\n", r"", content)
content = re.sub(r"│   └── test_merge_engine\.py       # 3-way merge\n", r"", content)

# 6. Summary table
content = re.sub(r"\| \*\*4\*\* \| 4\.2 Sync Anki \| `feature-sync-agent` \| `sync/\*` \(3\), `sync_worker\.py`, `merge_dialog\.py` \| 2\.3 \|\n", r"", content)
content = content.replace("| **4** | 4.3 YouTube |", "| **4** | 4.2 YouTube |")
content = content.replace("| **4** | 4.4 KaTeX Editor |", "| **4** | 4.3 KaTeX Editor |")

# 7. Total tasks calculation fix
content = content.replace("Total : 20 tâches, 17 agents", "Total : 19 tâches, 16 agents")
content = content.replace("20 tâches, 17 agents distincts", "19 tâches, 16 agents distincts")
content = content.replace("4 agents parallèles", "3 agents parallèles")
content = content.replace("4 agents simultanés", "3 agents simultanés")
content = content.replace("~30 fichiers à créer", "~24 fichiers à créer")

with open("ankiforge_implementation_plan.md", "w") as f:
    f.write(content)
