# Services IA et Analyse (Brouillon)

## Diagnostic & Traçabilité des Sources

### Stratégie d'implémentation hybride (Modèle Source-First + Moteur d'Audit LLM)

Pour assurer une traçabilité parfaite des sources et garantir l'exactitude des cartes générées, nous combinons deux approches :

**1. Traçabilité Structurelle (Peewee ORM)**
- **SourceDocumentModel :** Une table dédiée pour stocker l'historique de chaque document ingéré (titre, type `.pdf/.md`, date, taille, moteur d'extraction utilisé comme Marker).
- **CardSourceLinkModel :** Une table de liaison qui connecte chaque carte générée à son document d'origine (ou via une Foreign Key sur `NoteModel`).
- **Indicateur de Couverture :** Calcul du ratio entre la densité de la source (nombre de tokens ou de concepts clés extraits) et le nombre de cartes générées, afin d'alerter si une source riche a généré très peu de cartes.

**2. Moteur d'Audit Anti-Hallucination (IA)**
- **Vérification Sémantique :** Lors de l'analyse, le système effectue un "batch" comparant les textes originaux (via des embeddings locaux) avec le contenu des cartes générées.
- **Score de Précision :** Ce score, affiché dans l'interface, est pénalisé s'il y a des déviations factuelles ou des informations inventées par l'IA (hallucinations). Si 5% des cartes d'une source contiennent des affirmations non sourcées, le score de précision tombe à 95%.
- **Action de l'utilisateur :** Permet à l'utilisateur d'inspecter visuellement les cartes incriminées et de les corriger via l'inspecteur.
