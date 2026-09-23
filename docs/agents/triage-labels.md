# Triage Labels

Les skills parlent en termes de cinq rôles de triage canoniques. Ce fichier mappe ces rôles vers les chaînes réellement utilisées dans le traqueur d'issues de ce repo.

Le traqueur est le **kanban Obsidian** (`ankiforge_obsidian/Tickets/`) : il n'a pas de labels natifs — les rôles sont portés par l'en-tête `**Statut :**` de chaque ticket.

| Rôle dans les skills | Valeur dans le traqueur (Statut) | Sens                                        |
| -------------------- | -------------------------------- | ------------------------------------------- |
| `needs-triage`       | `needs-triage`                   | À évaluer par un mainteneur                 |
| `needs-info`         | `needs-info`                     | En attente d'info de la part de l'utilisateur |
| `ready-for-agent`    | `ready-for-agent`                | Spécifié et prêt pour un agent              |
| `ready-for-human`    | `ready-for-human`                | Nécessite une implémentation humaine        |
| `wontfix`            | `wontfix`                        | Ne sera pas traité                          |

Quand un skill mentionne un rôle (ex. « applique le label prêt-agent »), utiliser la chaîne correspondante du Statut dans l'en-tête `**Statut :**` du ticket (`Statut : &#9312; À Faire · ready-for-agent`).
