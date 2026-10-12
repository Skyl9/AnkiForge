# Synchronisation & Fusion 3 Voies (Smart Merge) 🔄

AnkiForge fonctionne selon un modèle déconnecté (*air-gapped*) vis-à-vis d'Anki : il possède sa propre base SQLite isolée et communique via l'import de paquets `.apkg` ou de collections `.colpkg` et l'export de paquets `.apkg`.

Pour éviter toute perte de données ou écrasement intempestif de vos révisions, AnkiForge intègre un moteur de **fusion intelligente 3 voies (*Smart Merge*)**.

---

## 🛡️ 1. La Règle d'Or de la Fusion

Lors de la synchronisation entre AnkiForge et votre profil Anki, la politique de fusion repose sur un principe fondamental :

!!! warning "Règle d'Or"
    Seules les modifications concurrentes du **contenu textuel brut** d'une note (Question ou Réponse) déclenchent un conflit nécessitant un arbitrage humain.

    Les changements d'organisation (déplacement d'une carte vers un autre paquet, ajout de tags) et l'historique de révision (dates d'échéance, intervalles FSRS/SM-2, compteurs de répétition) sont **fusionnés silencieusement** pour ne jamais perturber votre progression d'apprentissage !

---

## 🎛️ 2. Le Dialogue de Fusion à 3 Panneaux (`MergeView`)

Inspiré des outils de merge différentiel des IDEs professionnels (JetBrains IntelliJ, VS Code), le dialogue de fusion affiche trois colonnes synchronisées :

```text
┌──────────────────────┬──────────────────────┬──────────────────────┐
│  VERSION LOCALE      │   RÉSULTAT FUSION    │   VERSION DISTANTE   │
│   (AnkiForge)        │     (Interactif)     │    (Paquet Anki)     │
├──────────────────────┼──────────────────────┼──────────────────────┤
│ Recto:               │ Recto:               │ Recto:               │
│ "Qu'est-ce que FSRS?"│ "Qu'est-ce que FSRS?"│ "Définition de FSRS ?"│
│                      │                      │                      │
│ Verso:               │ Verso:               │ Verso:               │
│ [Version mise à jour]│                      │ [Ancienne version]   │
│                      │  <<< Adopter Gauche  │                      │
│                      │  Adopter Droite >>>  │                      │
└──────────────────────┴──────────────────────┴──────────────────────┘
```

### Fonctionnalités Clés
- **Coloration Différentielle** : Les portions de texte ajoutées, supprimées ou modifiées sont surlignées en temps réel.
- **Flèches d'Arbitrage en 1-Clic** : Cliquez sur les chevrons `<<<` ou `>>>` pour injecter immédiatement la version locale ou distante dans le résultat final.
- **Édition Manuelle Live** : Le panneau central reste un éditeur de texte complet dans lequel vous pouvez combiner ou reformuler librement les deux versions.
- **Validation Globale** : Un bouton "Tout résoudre automatiquement" permet d'appliquer la stratégie par défaut (ex: donner priorité à la version AnkiForge pour les cartes modifiées récemment).

---

## 📦 3. Import & Export de Paquets

### Exportation `.apkg`
- Génère une archive standard compatible avec toutes les versions d'Anki (Desktop, AnkiDroid, AnkiMobile iOS).
- Inclut automatiquement l'ensemble des fichiers médias (images, schémas, sons TTS MP3) associés aux cartes.
- Préserve la structure des sous-paquets hiérarchiques (`Parent::Enfant`).
- Transporte le **contenu** uniquement : notes, types de note, gabarits, CSS, médias, drapeaux 1-7 et suspension. La Forge ne fabrique **jamais** d'ordonnancement (dates d'échéance, intervalles FSRS/SM-2, journal de révision) : les cartes exportées redémarrent leur flux dans Anki (ADR 0022).

> [!NOTE]
> L'export `.colpkg` n'est pas proposé : la Forge produit exclusivement des paquets `.apkg` de contenu. Une sauvegarde intégrale de collection, si elle est un jour souhaitée, fera l'objet d'un chantier successeur.

### Garantie oracle (Anki officiel)
Les paquets produits sont validés de bout en bout par le **moteur Anki officiel** en dépendance de développement (`anki`), en headless : ouverture sans corruption, fidélité de contenu (comptes notes/cartes, champs/gabarits/CSS, hiérarchie, `guid`, médias MD5), drapeaux et suspension, non-mutation à l'import. Voir `tests/integration/test_anki_export_oracle.py`.
