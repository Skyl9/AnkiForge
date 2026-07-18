---
name: peewee-expert
description: Bonnes pratiques pour l'utilisation de Peewee dans AnkiForge
---

# Compétence : Expert Peewee ORM

En tant qu'expert Peewee pour AnkiForge, tu dois respecter ces règles strictes extraites du GEMINI.md global, déclinées pour ton périmètre :

1. **Intégrité Référentielle** : 
   - Utilise systématiquement `on_delete='CASCADE'` sur les `ForeignKeyField`. Les données orphelines sont proscrites (ex: la suppression d'un Profil doit cascader vers ses Decks et Cartes).
   - Respecte scrupuleusement les contraintes `null=False` (qui correspond au `NOT NULL` de SQLite).

2. **Transactions & Performance** : 
   - Utilise TOUJOURS `db.atomic()` pour les opérations d'écriture/suppression multiples.

3. **Indépendance** :
   - Tes modèles ne doivent jamais faire appel à la logique d'interface. Ne print rien, lève des exceptions métier claires si besoin.
