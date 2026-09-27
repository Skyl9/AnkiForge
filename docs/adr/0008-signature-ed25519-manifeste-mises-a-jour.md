# Signature Ed25519 des mises à jour par manifeste d'intégrité et politique Fail-Closed

Pour garantir l'authenticité et l'intégrité absolue des binaires téléchargés lors des auto-mises à jour sans dépendre exclusivement des certificats de plateformes tierces, AnkiForge adopte un modèle de signature asymétrique Ed25519 basé sur un manifeste consolidé (`checksums.txt` et `checksums.txt.sig`). Le client valide la signature du manifeste via un trousseau de clés publiques immuables embarqué, puis compare l'empreinte SHA-256 du binaire téléchargé. Toute incohérence, altération ou absence de signature entraîne le rejet immédiat du binaire, sa purge du disque et le blocage de l'installation (politique stricte Fail-Closed).

## Statut
Accepté

## Options considérées
- **Signature par fichier sidecar unitaire (`.sig` par binaire)** : Rejeté car cela multiplierait les fichiers de signatures distants (6 fichiers par release) et obligerait à des requêtes multiples, alors que la signature d'un manifeste unique consolidé (`checksums.txt`) lie atomiquement l'ensemble des artefacts d'une même release en un seul fichier de 64 octets.
- **Vérification permissive avec avertissement ("Fail-Open" ou bypass utilisateur)** : Rejeté car autoriser l'exécution d'un binaire exécutable corrompu ou falsifié expose l'utilisateur à des risques critiques d'élévation de privilèges ou de compromission de son système.
- **Dépendance pure Python sans bibliothèque externe** : Rejeté au profit de `cryptography` (PyCA), qui garantit une résistance éprouvée contre les attaques par canaux auxiliaires, une conformité stricte RFC 8032 et une intégration native transparente avec le compilateur Nuitka.
- **Notarisation macOS bloquante en CI sans secrets** : Découplée pour permettre une signature applicative Ed25519 universelle immédiate sur tous les OS, tout en préparant les étapes de notarisation Apple sous condition de présence des secrets de compte développeur.
