# ADR 0048 : Troncature des arguments tool-call et plafonds volumétriques des lots MCP

**Statut :** accepté (corrige la motivation d'ADR 0046 §C et complète ADR 0043 sur les Staged Bundles)

---

## 1. Contexte & Problématique

Lors de campagnes de création ou de refactorisation de masse, les agents externes soumettent des lots de plusieurs dizaines de cartes en un seul appel MCP (`create_notes_batch`, `propose_cards_batch_refactor`). Au-delà d'environ 10 000 caractères d'argument, l'outil échoue avec :

```
JSONDecodeError: Unterminated string starting at ...
```

Le ticket initial attribuait cette panne à un « buffer JSON-RPC plafonné à ~10k caractères » et demandait de porter le buffer de transport à 2–5 Mo. Cette hypothèse est fausse et le remède proposé serait inopérant : il faut d'abord localiser la coupure, puis borner le contrat des lots.

---

## 2. Diagnostic : la coupure est en amont de la trame JSON-RPC

### A. Faits vérifiés dans le SDK `mcp 2.1.1`

| Élément | Constat |
| --- | --- |
| `mcp/server/transport_security.py:15` | `DEFAULT_MAX_REQUEST_BODY_SIZE = 4 * 1024 * 1024`, soit **4 194 304 octets (4 Mio)** |
| Application HTTP | `RequestBodyLimitMiddleware` sur Streamable HTTP (`streamable_http_manager.py`) et SSE (`sse.py`) ; dépassement = **HTTP 413 avant tout traitement** |
| `mcp/server/stdio.py:187` | `async for line in stdin` : **aucune borne de taille** sur le transport stdio |
| `mcp_daemon.py:584-585` | `streamable_http_app()` / `sse_app()` sont appelés **sans** `max_request_body_size` : la valeur par défaut de 4 Mio s'applique |

Le plafond de transport réel est donc de 4 Mio, soit déjà très au-dessus de la cible « 2 à 5 Mo » du ticket et **deux ordres de grandeur au-dessus** du seuil de panne observé (~10 k caractères). Relever ce plafond n'aurait donc strictement aucun effet.

### B. Faits vérifiés dans le code AnkiForge

| Élément | Constat |
| --- | --- |
| `mcp_server.py` → `create_notes_batch` | `json.loads(notes_json)` direct, **aucune borne de volume**, aucune métadonnée d'échec |
| `mcp_tool_registry.py` → `propose_cards_batch_refactor` | `robust_json_loads` + **plafond de 100 cartes uniquement**, sans borne de caractères |
| `staged_patch_registry.py` | La création de patch intervient **après** validation complète du lot ; rien n'est écrit en cas d'exception |

### C. Conclusion diagnostique

Si le transport avait coupé la requête, le SDK aurait rejeté la trame (`413`, ou échec de `jsonrpc_message_adapter.validate_json`) **avant** d'invoquer l'outil. Or l'exception `Unterminated string` est levée **à l'intérieur** de `create_notes_batch`, donc :

1. l'enveloppe JSON-RPC est arrivée **complète et valide** ; seule la **valeur de l'argument** est incohérente ;
2. la chaîne est coupée en plein littéral, ce qui est la signature d'une **interruption de génération** côté modèle (fenêtre de sortie saturée) ou d'une troncature dans le client, jamais d'une limite d'octets serveur ;
3. l'agent, recevant une erreur de parsing opaque, réémet souvent le même lot : la boucle d'échec est auto-entretenue.

L'expression « buffer JSON-RPC plafonné à 10k » est donc trompeuse et proscrite : le buffer n'est pas en cause.

---

## 3. Décision

### A. Périmètre : garde-fou sur les deux outils de lot existants

Le plafond s'applique à :

- `create_notes_batch` (`notes_json`) ;
- `propose_cards_batch_refactor` (`refactors_json`).

Aucune nouvelle API « chunked » ni paramètre de pagination d'écriture n'est introduite : la fragmentation s'obtient par des **appels successifs** sur un `Staged Bundle` maintenu ouvert (`begin_staged_bundle` / `commit_staged_bundle`, ADR 0043). Les outils unitaires (`note_create`, `propose_card_refactor`) restent inchangés et servent de repli pour une note isolée exceptionnellement volumineuse.

### B. Double seuil : plafond serveur dur et recommandation de guide

| Rôle | Notes max | Caractères max | Portée |
| --- | --- | --- | --- |
| **Plafond serveur dur** (refus) | **100** | **32 000** | Appliqué par l'outil avant mise en attente |
| **Recommandation de sous-lot** (guide d'agent) | **5 à 8** | **8 000** | Documentée dans les guides d'amorçage MCP |

Les deux bornes du plafond dur sont **cumulatives** : un lot est refusé dès que **l'une** des deux est franchie. Le plafond existant de 100 cartes est donc conservé et complété par une borne textuelle, car un lot de 100 cartes peut parfaitement dépasser la fenêtre de génération de l'agent et produire la troncature décrite en §2.

Le seuil de 32 000 caractères est mesuré sur la **chaîne d'argument telle que reçue**, avant tout parsing : le garde-fou doit pouvoir refuser un payload monstrueux sans tenter de le décoder.

### C. Refus structuré, immédiat et sans état partiel

Tout dépassement produit une réponse JSON d'erreur explicite, retournée à l'agent, sans création de patch, sans bundle partiel et sans tentative de réparation du JSON :

```json
{
  "status": "error",
  "error_code": "PAYLOAD_TOO_LARGE",
  "tool": "create_notes_batch",
  "received_chars": 48213,
  "max_chars": 32000,
  "received_notes": null,
  "max_notes": 100,
  "suggestion": "Fractionnez en sous-lots de 5 à 8 notes (≈ 8 000 caractères) via des appels successifs sur le même Staged Bundle.",
  "no_state_written": true
}
```

Les champs non encore déterminables au moment du contrôle valent `null` : lors d'un `PAYLOAD_TOO_LARGE`, le nombre de notes n'est pas connu puisque le payload n'a pas été décodé.

Trois codes d'erreur, dans cet ordre d'évaluation :

1. `PAYLOAD_TOO_LARGE` — volume de la chaîne reçue supérieur au plafond, évalué **avant** `json.loads` ; porte `received_chars` et `max_chars` ;
2. `INVALID_JSON` — échec de parsing d'un payload pourtant sous le plafond ; porte `received_chars` et `error_position` (position de l'erreur `JSONDecodeError`), jamais le contenu partiel ;
3. `TOO_MANY_NOTES` — lot bien formé mais trop nombreux ; porte `received_notes` et `max_notes`.

Une réparation automatique (fermeture de crochets/accolades, complétion de littéraux) est **refusée** : elle inventerait du contenu de carte et produirait des notes fantômes validables par l'utilisateur.

### D. Instrumentation : métadonnées seulement

Chaque invocation des deux outils de lot émet une ligne de journal (niveau `WARNING` pour un refus, `DEBUG`/`INFO` sinon) ne contenant **que** des métadonnées :

- nom de l'outil ;
- caractères et octets reçus ;
- empreinte **SHA-256** tronquée de l'argument (corrélation d'épisodes sans conservation du contenu) ;
- validité JSON (`true` / `false`) et position d'erreur le cas échéant ;
- drapeau `truncated_suspected` (erreur de type « Unterminated string » ou position terminale) ;
- nombre de notes demandées et code d'erreur éventuel.

Aucun champ de carte, aucun tag, aucun extrait du payload, aucun secret ne doit apparaître dans ces lignes — l'objectif est de distinguer une troncature de génération d'un défaut de client, pas de journaliser la collection. Le buffer de télémétrie existant (`MCPActivityTracker`, 100 enregistrements) reste borné par construction grâce au plafond de 32 000 caractères (ordre de quelques mégaoctets au pire cas).

### E. Recette client obligatoire

La correction est réputée vérifiée lorsqu'elle est reproduite avec le client réellement fautif :

- **Client** : Antigravity CLI / Gemini via **Streamable HTTP** (jeton Bearer du cockpit MCP) ;
- **Scénario 1 (refus)** : demande d'un lot d'environ 40 notes dont l'argument dépasse 10 000 caractères. Si la génération est interrompue sous le plafond dur, la réponse attendue est `INVALID_JSON` ; si le volume franchit 32 000 caractères, `PAYLOAD_TOO_LARGE`. Dans les deux cas, **aucun** patch n'apparaît dans le Garde-Fou ;
- **Scénario 2 (succès fragmenté)** : deux sous-lots de 6 notes (≈ 8 000 caractères chacun) sur un même bundle ouvert → 12 étapes unitaires inspectables dans le Garde-Fou ;
- **Scénario 3 (non-régression)** : un lot sous les deux seuils produit exactement le comportement d'ADR 0046 (bundle auto-scellé si aucun bundle n'était ouvert).

Le transport reste à **4 Mio** (valeur par défaut du SDK), sans relèvement ni paramétrage explicite : ce n'est pas un levier de cette décision. Un passage explicite de `max_request_body_size` ne sera introduit que si une mesure ultérieure démontre une saturation réelle du corps HTTP.

### F. Guides d'amorçage

`mcp_init_shared_workflows.md.j2` et les guides `mcp_init_guide_*.md.j2` doivent exposer le **sous-lot de génération** : viser 5 à 8 notes et moins de 8 000 caractères par appel, réutiliser le bundle ouvert pour les sous-lots suivants, et ne jamais réémettre un lot refusé à l'identique. Aucun de ces gabarits ne mentionne aujourd'hui de fragmentation : c'est un ajout net, cohérent avec le plafond dur.

---

## 4. Conséquences

### Bénéfices

- **Diagnostic rétabli** : les agents reçoivent une cause exploitable (`PAYLOAD_TOO_LARGE` / `INVALID_JSON` / `TOO_MANY_NOTES`) au lieu d'une exception de parsing opaque, ce qui casse la boucle de réémission.
- **Intégrité préservée** : refus avant toute écriture, aucun bundle ni patch partiel, conformité totale au Two-Phase Commit (ADR 0034, ADR 0043).
- **Coût de contexte maîtrisé** : les sous-lots réduisent la pression sur la fenêtre de génération et la latence perçue par l'utilisateur.
- **Observabilité honnête** : les empreintes et volumes permettent d'instruire un incident sans jamais journaliser le contenu des cartes.

### Contraintes acceptées

- **Allers-retours supplémentaires** : un lot de 40 notes nécessite plusieurs appels ; le gain de latence d'un envoi unique (ADR 0046) est plafonné en pratique.
- **Refus de lots volumineux mais valides** : un lot de 100 notes très denses sera refusé ; le message doit rester actionnable, sinon l'agent boucle.
- **Note unitaire volumineuse** : au-delà de 32 000 caractères dans un seul argument, seuls les outils unitaires restent disponibles.
- **Pas de relèvement du buffer** : la piste initiale du ticket est abandonnée et documentée comme telle ; toute réouverture exige une mesure montrant un `413` ou un échec de validation de trame côté SDK.

---

## 5. Stratégie de vérification (TDD)

1. `create_notes_batch` avec 101 notes → `TOO_MANY_NOTES`, aucun patch créé.
2. `create_notes_batch` avec un payload dépassant 32 000 caractères → `PAYLOAD_TOO_LARGE`, `received_chars` exact, aucun patch créé.
3. `create_notes_batch` avec un JSON tronqué en plein littéral → `INVALID_JSON` avec `error_position`, aucun patch créé.
4. Les trois cas ci-dessus rejoués sur `propose_cards_batch_refactor`.
5. Lot sous les deux seuils → staging nominal (non-régression ADR 0046) et ligne de journal sans aucun contenu de carte (assertion d'absence d'une valeur sentinelle dans `caplog`).
6. Deux sous-lots successifs sur un bundle ouvert → 12 étapes dans un unique bundle.

---

## 6. Références

- [ADR 0046](0046-refactorisation-par-lot-mcp-et-staged-bundles-multi-etapes.md) — Refactorisation par lot. Son §C a été mis à jour : la motivation « débordement de buffer JSON-RPC » y est remplacée par la troncature d'arguments tool-call, la consigne de scission « sous-lots de 50 à 100 cartes » par la recommandation de 5 à 8 notes / 8 000 caractères, et le plafond de 100 cartes est complété par la borne de 32 000 caractères.
- [ADR 0043](0043-regime-staged-bundles-atomicite-sequentielle-et-overlay-mcp.md) — Staged Bundles, atomicité séquentielle et overlay.
- [ADR 0034](0034-architecture-mcp-garde-fou-2pc-et-centrage-harness.md) — Garde-Fou MCP et Two-Phase Commit.
