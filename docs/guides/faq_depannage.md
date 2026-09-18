# FAQ & Dépannage ❓

Questions fréquentes et résolutions des incidents les plus courants d'AnkiForge. En cas de problème persistant, ouvrez une issue sur le [dépôt GitHub](https://github.com/Skyl9/AnkiForge/issues) en y joignant le contenu de `~/.ankiforge/logs/`.

---

## 🤖 1. Connexion à Ollama

### AnkiForge ne trouve pas Ollama (`localhost:11434`)

1. Vérifiez que le démon tourne : `ollama serve` (ou relancez l'application Ollama).
2. Testez l'API : `curl http://localhost:11434/api/version` doit répondre `{"version":"..."}`.
3. Assurez-vous qu'aucun proxy ne bloque le bouclage local (variables `HTTP_PROXY` / `NO_PROXY` — ajoutez `localhost:11434` à `NO_PROXY`).
4. Vérifiez que le modèle demandé existe bien : `ollama list`. Le modèle déclaré dans les paramètres doit correspondre exactement au nom de l'image présente localement.

!!! tip "Anti-SSRF"
    AnkiForge refuse de contacter des hôtes Ollama non locaux par sécurité (anti-SSRF) : une URL réseau externe est ignorée.

### Le modèle local est lent ou génère un JSON invalide

- Utilisez un modèle avec un bon support des instructions structurées (`llama3.2`, `mistral`, `qwen2.5-coder`).
- Le JSON généré est parsé de manière robuste (stratégies de réparation successives), mais un modèle trop léger peut échouer : privilégiez ≥ 7 milliards de paramètres pour la génération de cartes.

---

## 🧱 2. Dépendances Lourdes (Marker, PyTorch, Whisper)

### L'OCR Marker ou la transcription Whisper ne s'installent pas

- Marker embarque PyTorch : son installation est volumineuse (> 2 Go). AnkiForge le propose **à la demande** et fonctionne parfaitement sans lui grâce au fallback `pdfplumber` (extraction texte/tableaux).
- En environnement restreint (offline, quotas disque), désactivez l'installation de Marker dans **Paramètres ➔ Ingestion** : l'extraction PDF de base reste disponible.

!!! warning "Espace disque"
    Prévoyez plusieurs gigaoctets d'espace libre avant d'installer Marker/Whisper, et un dossier de modèles suffisamment dimensionné (`~/.ankiforge/sidecars/`).

---

## 🗄️ 3. Base de Données SQLite Verrouillée

### "database is locked" ou impossibilité d'ouvrir le profil

Cette erreur signifie généralement qu'un **second processus AnkiForge** utilise déjà la base du profil courant :

1. Fermez toutes les instances d'AnkiForge ouvertes.
2. Vérifiez qu'aucun processus résiduel tourne : `pgrep -fl ankiforge` (macOS/Linux) puis terminez-le si besoin.
3. Assurez-vous que le fichier n'est pas en lecture seule ou hébergé sur un montage réseau non fiable : copiez `~/.ankiforge/profiles/<nom>/ankiforge.db` sur le disque local.

!!! tip "Isolation par profil"
    Chaque profil possède **sa propre base** sous `~/.ankiforge/profiles/<nom>/`. Copiez/déplacez le dossier entier d'un profil pour conserver vos paires de révisions.

---

## ⚙️ 4. Extension C & Binaires

### L'extension Levenshtein ne compile pas

- AnkiForge bascule automatiquement sur le **fallback pur Python** (`ankiforge.utils.c_bridge`) : aucun blocage.
- Pour une compilation native, installez les outils de build : Xcode Command Line Tools (`xcode-select --install`), `gcc` ou MSVC.

### Quand utiliser le binaire Nuitka ? (Disponible dans les [releases GitHub](https://github.com/Skyl9/AnkiForge/releases))

- **Binaire natif** : aucune installation Python requise, idéal pour les utilisateurs finaux.
- **Source (`uv`)**: accès aux versions de développement et aux outils de diagnostic.

---

## 🔒 5. Mot de Passe & Secrets

### Mes clés API sont-elles stockées en clair ?

Non : AnkiForge confie les clés au **trousseau de l'OS** (Keychain macOS, Credential Manager Windows, Secret Service Linux) via `ankiforge.utils.secret_store`. Lire la section [Stockage sécurisé](../installation.md#stockage-securise-des-cles-api).

### Réinitialiser une clé API

Remplissez simplement la nouvelle clé dans **Paramètres ➔ Fournisseurs IA** : elle remplace l'ancienne dans le trousseau à la prochaine sauvegarde.

---

## 🖥️ 6. Problèmes d'Affichage Qt

### L'interface ne s'affiche pas ou se fige sur certaines machines

- Mettez à jour vos pilotes graphiques ; le rendu Qt 6 utilise l'accélération matérielle.
- En environnement headless/VM, lancez avec le backend logiciel : `QT_QUICK_BACKEND=software` ou `QT_QPA_PLATFORM=offscreen`.
- Si la WebEngine (Agent JS, rendu de pages) pose problème : `QTWEBENGINE_DISABLE_SANDBOX=1` est déjà activé dans les environnements de test d'AnkiForge ; sur un poste de travail, préférez le sandbox actif et vérifiez donc plutôt la présence d'`Xvfb` ou d'un environnement graphique complet.

---

## 🐛 7. Signaler un Bug

Collez dans votre issue GitHub :
- La version d'AnkiForge (`uv run ankiforge --dev` affiche la version au lancement).
- Le contenu du journal : `~/.ankiforge/logs/ankiforge.log` (les secrets y sont automatiquement masqués).
- La trace du crash éventuel : `~/.ankiforge/logs/crash.log`.
