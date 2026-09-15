# Compilation Binaire Autonome (Nuitka) 📦

Pour distribuer AnkiForge sous forme d'application de bureau professionnelle ne nécessitant aucune installation préalable de Python ou de packages, le projet utilise le compilateur **Nuitka**.

---

## ⚡ 1. Pourquoi Nuitka ?

Contrairement à des empaqueteurs conventionnels (comme PyInstaller) qui se contentent d'archiver un interpréteur Python et des fichiers `.pyc` dans un fichier ZIP auto-extractible :
- **Traduction C Native** : Nuitka traduit le code Python en code machine C avant de le compiler avec `clang`, `gcc` ou `MSVC`.
- **Accélération des Performances** : Réduction du temps de démarrage de l'application et optimisation des boucles d'exécution.
- **Protection du Code Source** : Le code métier et les algorithmes sont intégrés sous forme de binaires compilés.
- **Support Natif de PySide6** : Intégration transparente du runtime Qt, des plugins de plateforme (`cocoa`, `xcb`, `windows`) et de WebEngine.

---

## 🛠️ 2. Commande de Compilation Recommandée

La compilation s'effectue via les scripts préparés dans `script/` ou via la ligne de commande suivante :

```bash
uv run python -m nuitka \
    --standalone \
    --enable-plugin=pyside6 \
    --include-package=ankiforge \
    --include-data-dir=src/ankiforge/resources=resources \
    --macos-create-app-bundle \
    --macos-app-name="AnkiForge" \
    --output-dir=dist \
    src/ankiforge/main.py
```

### Explications des Options Clés
- `--standalone` : Génère un dossier autonome contenant toutes les bibliothèques dynamiques requises.
- `--enable-plugin=pyside6` : Inclut automatiquement les bindings Qt nécessaires et exclut les modules Qt non utilisés (comme Qt3D ou QtSensors) pour alléger l'exécutable.
- `--include-data-dir=src/ankiforge/resources=resources` : Embarque les assets statiques essentiels, notamment la bibliothèque **KaTeX** (`katex.min.js`, `katex.min.css`, polices mathématiques WOFF2).
- `--macos-create-app-bundle` : Produit un bundle `.app` natif macOS avec icône et métadonnées `Info.plist`.

---

## 📦 3. Architecture des Sidecars & Poids de l'Exécutable

Pour maintenir un binaire d'une taille raisonnable (< 80 Mo) :
- Les dépendances ultra-lourdes de Deep Learning (Marker OCR, PyTorch) et les moteurs de voix neuronaux (Piper TTS) ne sont **pas intégrés dans le binaire principal**.
- Ils sont gérés sous forme de **sidecars** téléchargés à la demande dans le répertoire persistant de l'utilisateur (`~/.ankiforge/sidecars/`).
- Ainsi, les mises à jour mineures d'AnkiForge n'obligent pas l'utilisateur à re-télécharger plusieurs gigaoctets d'actifs de calcul.
