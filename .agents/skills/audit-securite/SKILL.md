---
name: audit-securite
description: Audit sécurité du code source d'AnkiForge. Use when the user asks to "audit sécurité", "vérifier les secrets", "bandit", "scan de clés API", "durcissement", "sandbox PYTHON_TOOL", "SSRF", "extraction zip dangereuse", "WebEngine" or to find hardcoded API keys, dangerous subprocess/exec, or missing redaction in logs. Runs bandit + gitleaks and produces a targetted security report under audits/.
---

# Audit Sécurité AnkiForge

En tant qu'**Auditeur Sécurité & Code Review Expert**, tu inspectes le code source d'AnkiForge pour identifier les vulnérabilités exploitables, les fuites de secrets, les exécutions non confinées et les accès réseau non validés, puis tu produis un rapport de sécurité priorisé.

## 1. Périmètre & Sources de Vérité

- `GEMINI.md` : règle 4 (outils MCP sécurisés), règle 10 (agnosticisme LLM, Ollama localhost), règle 12 (extension C), règle 19 (logging asynchrone, `SecretRedactionFilter`, zéro secret en clair).
- `src/ankiforge/` : cible de l'audit (exclure `tests/` et `database/migrations/` sauf indication contraire).
- Docs : `docs/Dossier_architecture/05_services_ia_et_analyse.md`, `docs/Dossier_architecture/06_moteur_orchestration_ia.md`.

## 2. Exécution des Outils (Obligatoire)

Lance ces commandes et traite leurs sorties dans le rapport :

```bash
# 1) Bandit (config: pyproject.toml, skips B104/B110, tests exclus)
uv run bandit -c pyproject.toml -r src/

# 2) Gitleaks (si le binaire est disponible, sinon repli grep ci-dessous)
gitleaks detect --source . -c .gitleaks.toml --no-banner --verbose 2>/dev/null || echo "gitleaks indisponible — repli sur grep patterns"

# 3) Patterns de secrets (repli systématique)
grep -rInE "(sk-[A-Za-z0-9]{20,}|AIza[0-9A-Za-z_-]{30,}|sk-ant-[A-Za-z0-9]{20,}|-----BEGIN [A-Z ]*PRIVATE KEY-----)" src/ || true
grep -rInE "(api[_-]?key|secret|token|password|bearer)\s*[=:]\s*[\"'][^\"']{8,}[\"']" src/ --include="*.py" || true
```

## 3. Points de Contrôle

Examine chaque point et note toute violation (fichier:ligne, règle, extrait, correction) :

1. **Exécution de code arbitraire / sandbox** — `src/ankiforge/services/tools/tool_sandbox.py` :
   - `exec` uniquement présent ici, avec `# nosec B102` justifié.
   - `_SAFE_BUILTINS` : vérifier que `__import__`, `open`, `eval`, `exec`, `compile`, `globals`, `locals`, `input`, `exit`, `quit`, `breakpoint` sont bien exclus.
   - Timeout réel : traceur `sys.settrace` à échéance + `worker.join` (aucune thread zombie en cas de boucle infinie).
2. **Subprocess** (toutes occurrences) : `shell=False` par défaut, argv sous forme de liste, jamais de chaîne concaténée avec entrée utilisateur ; chaque `# nosec B603/B607/B606` doit avoir une justification en ligne. `grep -rn "subprocess" src/`.
3. **`eval`/`compile`/`__import__`** hors sandbox : `grep -rnE "(eval|compile|__import__)\(" src/ --include="*.py"` — toute occurrence hors `tool_sandbox.py` est une violation critique si elle touche une entrée utilisateur/IA.
4. **Secrets & stockage** — `src/ankiforge/utils/secret_store.py` :
   - Aucune clé API en dur dans `src/` (grep §1.3) ; l'écriture/lecture des clés doit passer par `store_secret`/`load_secret` (keyring OS), avec fallback argumenté.
   - `src/ankiforge/ui/widgets/settings_modal/tabs/ai_engines_tab.py` : les clés saisies sont stockées via le keyring, pas en BDD/plaine.
5. **Extraction d'archives** — `src/ankiforge/utils/archive_utils.py` : `safe_extract_zip`/`safe_extract_tar` bloquent-ils `..`, chemins absolus, symlinks et zip-bombs ? Y a-t-il des appels directs à `zipfile.extractall`/`tarfile.extract` ailleurs ?
6. **SSRF / réseau local** — `src/ankiforge/services/ai/model_catalog.py` `_is_loopback_url` : toute URL Ollama/API doit être validée comme loopback (grep `requests.get|http://|localhost:` dans `services/ai/`).
7. **Interface Web embarquée** — `src/ankiforge/ui/widgets/safe_web_preview.py` : `LocalContentCanAccessRemoteUrls=False`, `JavascriptCanOpenWindows=False`, allow-list de schémas de navigation ; pas de balisage `https://cdn` dans les templates KaTeX/MathJax (`grep -rn "cdn" src/`).
8. **Logging & exfiltration** — `src/ankiforge/utils/logger.py` : `SecretRedactionFilter` masque bien `sk-*`, `AIza*`, `sk-ant-*`, `Bearer`, tokens ; vérifier qu'aucun code ne log une valeur de clé avant filtrage.
9. **Téléchargements réseau** — `src/ankiforge/services/cards/tts_service.py` : téléchargements Piper vérifiés par hash SHA-256, plafonds de taille et timeouts.
10. **Protocole MCP** — `src/ankiforge/services/ai/mcp_server.py` : les outils exposés ne doivent jamais renvoyer de secret ; `query_peewee`/`execute_python_tool` restent dans le périmètre de l'utilisateur local.

## 4. Rapport d'Audit

Écris le rapport dans `audits/audit-securite.md` (avance absolue champ d'action, `mkdir -p audits`) :

### 📊 Synthèse
Tableau : anomalies par sévérité (Critique/Majeur/Mineur) et par catégorie (Sandbox, Subprocess, Secrets, Réseau, Web, Logs, Archives).

### 🔍 Violations détaillées
Pour chaque violation : lien cliquable absolu `[fichier.py:Lnn](file://<abs>/...#Lnn)` · règle violée (référence GEMINI.md §X ou motif CWE) · extrait incriminé · diff de correction proposé.

### 🗺️ Plan de remédiation priorisé
Actions ordonnées (critiques d'abord : secrets exposés, exécution non confinée, SSRF), avec commandes de vérification associées.

## 5. Clôture

1. Résume dans le chat les résultats majeurs (nombre de problématiques, les plus critiques).
2. Indique le chemin absolu du rapport.
3. Propose d'appliquer les correctifs (ou lance les sous-agents de correction si demandé).