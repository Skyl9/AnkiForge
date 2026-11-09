# Guide Normatif Conventional Comments — AnkiForge

Cette référence définit le standard de restitution des commentaires de revue de code au sein du projet AnkiForge, inspiré du standard international [Conventional Comments](https://conventionalcomments.org/).

---

## 1. Structure d'un Commentaire de Revue

Chaque commentaire de revue doit respecter scrupuleusement la structure suivante :

```markdown
### `[chemin/relatif/fichier.py:Lxx-Lyy](file:///chemin/absolu/fichier.py#Lxx-Lyy)`
**<label> (<decorations>):** <Titre concis du problème>

> Extrait de code exact :
> ```python
> <lignes exactes extraites du diff>
> ```

*Risque / Justification* :
<Explication claire et factuelle de la défaillance ou de la violation de règle.>

*Correction suggérée* :
```python
<patch ou bloc de remplacement prêt à l'emploi>
```
```

---

## 2. Étiquettes (`Labels`) et Décorateurs (`Decorations`)

| Label | Signification | Niveau de priorité |
|---|---|---|
| `issue` | Problème avéré de conformité aux standards, bogue logique ou régression. | Haute |
| `suggestion` | Proposition d'amélioration alternative (lisibilité, idiomatisme Python 3.12). | Moyenne |
| `nitpick` | Remarque cosmétique mineure non bloquante. | Basse |
| `question` | Demande d'éclaircissement sur une intention ou un cas limite non explicite. | Neutre |
| `thought` | Réflexion d'architecture ou perspective d'évolution future hors périmètre. | Information |
| `praise` | Félicitation pour un pattern particulièrement élégant ou bien testé. | Positif |

### Décorateurs Recommandés
- `(blocking)` : Résolution obligatoire avant merge ou commit (bloque le verdict).
- `(non-blocking)` : Amélioration recommandée mais qui n'empêche pas la validation.
- `(security)` : Risque de sécurité, injection ou fuite de données/secret.
- `(test)` : Lacune de couverture ou mock non conforme.

---

## 3. Verdicts Finaux Standardisés

À l'issue de la consolidation et du filtre critique, la revue formule un verdict unique parmi les 3 suivants :

### 🟢 `APPROVE`
- **Condition** : 0 `issue (blocking)`.
- **Signification** : Le diff respecte tous les standards AnkiForge et satisfait la spécification du ticket. Les suggestions éventuelles sont non bloquantes.

### 🔴 `REQUEST_CHANGES`
- **Condition** : $\ge 1$ `issue (blocking)`.
- **Signification** : Des violations critiques ou des critères non remplis empêchent la clôture. Le plan de remédiation fourni doit être appliqué avant nouvelle vérification.

### 🟡 `COMMENT`
- **Condition** : 0 `issue (blocking)`, mais des questions d'architecture ou des arbitrages métier (`question` / `thought`) nécessitent une réponse explicite de l'utilisateur.

---

## 4. Bloc de Synthèse pour Ticket Obsidian

En clôture de revue, un bloc récapitulatif prêt à être collé dans le ticket Obsidian doit être généré :

```markdown
## 📋 Résultat de la Revue de Code (Code Review)
- **Date** : <AAAA-MM-JJ HH:MM>
- **Point de référence** : `<base>...HEAD`
- **Verdict** : `APPROVE` | `REQUEST_CHANGES` | `COMMENT`
- **Couverture & Score CRAP** : Conforme (CRAP diff $\le 25$)
- **Synthèse des constats** :
  - Bloquants : 0
  - Suggestions non bloquantes : X
  - Critères du ticket : 100 % validés `[MET]`
```
