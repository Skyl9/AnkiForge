# 🩺 Grille des Critères de Santé d'un ADR (Architecture Decision Record)

Cette référence définit les 4 critères d'évaluation diagnostique employés lors d'une revue du registre `docs/adr/`.

---

## 1. Obsolescence face au Code Réel

Un ADR n'est pas une archive figée sans lien avec le présent : il doit refléter fidèlement l'état de l'architecture.

### Symptômes d'obsolescence :
- **Classes ou modules fantômes** : L'ADR mentionne des classes (`ConsultantView`, `ConsultantSessionModel`), des tables de base de données ou des fichiers qui ont été renommés ou supprimés du dépôt.
- **Contradiction avec des décisions ultérieures** : Une option marquée comme « Rejetée » dans un ancien ADR a finalement été retenue dans un ADR plus récent (ou inversement).
- **Inversion d'arbitrage** : Le parti pris technique a été abandonné lors d'une refonte majeure sans que le statut de l'ancien ADR ne soit mis à jour.

### Actions correctives :
1. Mettre à jour le champ `Statut :` (ex: `Remplacé par ADR-0034`).
2. Si la décision a été entièrement absorbée ou caduque, engager la procédure de concaténation ou de dépréciation formelle.

---

## 2. Émiettement & Fragmentation Thématique

Les décisions d'architecture ont tendance à s'étendre au fil des itérations : plusieurs ADRs successifs traitent du même sujet à des moments différents, dispersant la vérité architecturale.

### Symptômes de fragmentation :
- **Grappe d'ADRs rapprochés sur le même domaine** : Exemples :
  - Thèmes & styles : ADRs 0004, 0005, 0006.
  - Raccourcis clavier : ADRs 0031, 0032.
  - Évolution du protocole MCP / Consultant IA : ADRs 0001, 0002, 0014, 0030, 0033, 0034.
- **Micro-décisions successives** : Plusieurs documents de 10 lignes qui complètent un même choix initial au lieu d'avoir un ADR de référence consolidé.

### Actions correctives :
- Fusionner la grappe en un **ADR consolidé unique** (ou rattacher à l'ADR le plus récent / structurant).
- Rediriger toutes les références du dépôt vers la nouvelle section.
- Supprimer physiquement les ADRs absorbés pour assainir `docs/adr/`.

---

## 3. Verbosité & Sur-Spécification d'Implémentation

Un ADR doit consigner **pourquoi** un choix a été fait parmi des alternatives, et non servir de spécification détaillée de chaque ligne de code.

### Symptômes de dérive :
- **Taille démesurée (> 250 lignes)** : Détails d'implémentation de widgets, longs extraits de code transitoire, captures d'écrans textuelles ou protocoles temporaires.
- **Absence d'arbitrage réel** : Description d'un travail mécanique ou d'une évidence sans qu'il y ait eu de contre-options crédibles étudiées.

### Actions correctives :
- Raccourcir l'ADR en le recentrant sur le contexte, la décision retenue, les options rejetées et les conséquences architecturales.
- Déporter les détails d'implémentation dans la documentation Zensical (`docs/Dossier_architecture/`) ou les docstrings du code.

---

## 4. Statut Formel & Traçabilité

Tout ADR présent dans `docs/adr/` doit comporter un statut unifié et lisible dès les premières lignes du document.

### Statuts autorisés dans AnkiForge :
| Statut | Signification |
| :--- | :--- |
| `Accepté` | Décision active, en vigueur dans l'architecture actuelle. |
| `Proposé` | Décision en cours de discussion, non encore actée. |
| `Remplacé par ADR-XXXX` | Décision caduque, supplantée par une décision plus récente (avec lien vers l'ADR de remplacement). |
| `Consolidé dans ADR-XXXX` | Décision absorbée dans un ADR unifié plus large (avant purge ou avec redirection). |
| `Obsolète / Déprécié` | Choix technique devenu hors d'usage sans remplacement direct (ex: fonctionnalité supprimée). |
| `Rejeté` | Proposition d'arbitrage écartée après étude comparative. |
