# Signatures de Release & Trousseau Ed25519

Ce répertoire contient les artefacts de signature manuelle et les consignes pour les releases officielles AnkiForge.

## 1. Signature rétroactive de la release v1.3.0
Le fichier `v1.3.0_checksums.txt.sig` (64 octets binaires) est la signature officielle Ed25519 du fichier `checksums.txt` de la release GitHub v1.3.0.
Pour l'attacher à la release existante sur GitHub :
1. Rendez-vous sur https://github.com/Skyl9/AnkiForge/releases/tag/v1.3.0
2. Cliquez sur **« Edit release »**
3. Glissez-déposez le fichier `v1.3.0_checksums.txt.sig` dans la zone des assets
4. Cliquez sur **« Update release »**

## 2. Configuration CI GitHub Actions (Releases futures)
La clé publique active ajoutée à `TRUSTED_PUBLIC_KEYS` dans `src/ankiforge/security/signatures.py` est :
`04e2b926e7bb5069118799aa85744ad4c6c5c691e018d6feee984d4d8aa2057a`

La clé privée correspondante doit être ajoutée comme Secret de dépôt :
- URL : https://github.com/Skyl9/AnkiForge/settings/secrets/actions
- Nom : `ANKIFORGE_RELEASE_SIGNING_KEY_ED25519`
- Valeur : `cc79d86e4ac1cbffa356b866c38f43612cc5599ca60d9eec80312153e36bbc0c`
