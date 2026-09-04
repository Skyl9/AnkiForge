 ### 🩺 Parcours 1 : Violation d'Atomicité & Scission de Carte Surchargée (Card Split)

  • Objectif : Tester la détection des violations des règles 4 (Atomicité) et 11 (Listes de Wozniak) et le mécanisme de scission en 1-clic avec Garde-Fou humain.
  • Données de test (Carte à insérer en BDD) :
      • Paquet : Médecine::Cardiologie
      • Front : Quels sont les signes cliniques majeurs et les mécanismes physiopathologiques du choc cardiogénique ?
      • Back : Signes cliniques : Hypotension artérielle (PAS < 90 mmHg), oligurie (< 0.5 ml/kg/h), marbrures cutanées des extrémités, confusion, tachycardie compensatrice, râles crépitants aux bases pulmonaires. Mécanisme :
      Défaillance aiguë de la pompe myocardique entraînant un effondrement du débit cardiaque et une élévation des pressions de remplissage ventriculaire gauche.
  • Déroulement du test :
      1. L'utilisateur mentionne la carte : "@card_1 Analyse cette carte avec les règles de Wozniak et propose une solution."
      2. Comportement IA (ReAct) :
          • Outil appelé : audit_card_wozniak(note_id=1)
          • Détection : Règle n°4 (Atomicité violée : surcharge de 6 symptômes + mécanisme dans une seule carte) et Règle n°11 (Listes à proscrire).
          • Outil appelé : propose_card_split(note_id=1, new_cards=[...])
      3. Rendu Visuel attendu :
          • Widget thought_step_widget.py : étape d'analyse affichée.
          • Widget inline_diff_card_widget.py : Proposition de scission en 2 cartes distinctes (Carte A : Définition hémodynamique / Carte B : Signes d'hypoperfusion périphérique avec Cloze {{c1::...}}).
          • Clic sur [ ✅ Appliquer en BDD ] ➔ Découpage effectif en base SQLite, incrément du compteur "Cartes Optimisées".


  ──────
  ### ⚖️ Parcours 2 : Détection de Doublons & Interférences (Levenshtein / C-Bridge)
  • Objectif : Tester l'algorithme C-Bridge de similarité Levenshtein et la résolution de conflits de formulation.
  • Données de test (2 Cartes en BDD dans le paquet Droit::Constitutionnel) :
      • Carte A (Note #12) :
          • Front : En quoi consiste la procédure de l'article 49 alinéa 3 de la Constitution ?
          • Back : Le Premier ministre engage la responsabilité du Gouvernement sur le vote d'un texte. Le texte est considéré comme adopté sauf motion de censure votée dans les 48 heures.
      • Carte B (Note #15) :
          • Front : Quel article permet d'adopter une loi sans vote des députés à l'Assemblée ?
          • Back : L'article 49.3 de la Constitution, via engagement de responsabilité.

  • Déroulement du test :
      1. L'utilisateur saisit : "/duplicates" ou "Trouve les doublons et formulations redondantes dans @deck_Droit"
      2. Comportement IA :
          • Outil appelé : find_duplicate_cards(deck_name="Droit::Constitutionnel", threshold=0.75)
          • L'IA identifie que les cartes 12 et 15 créent une interférence d'apprentissage (Règle n°10 de Wozniak).
          • Elle propose de fusionner la carte 15 en une formulation Cloze bidirectionnelle sur la note 12 et d'archiver la 15.
      3. Rendu Visuel attendu :
          • Diff interactif comparant Note #12 vs Note #15.
          • Validation ou bouton [ Ouvrir dans l'Éditeur ↗ ] pour basculer directement sur la note dans l'onglet Édition.

  ──────
  ### 📐 Parcours 3 : Rénovation de Modèle de Carte & Retouche CSS (KaTeX / Dark Mode)

  • Objectif : Tester les outils list_note_types, get_note_type_details et propose_css_tune pour moderniser l'apparence des cartes avec KaTeX et respect de DESIGN.md.
  • Données de test :
      • Modèle de note : Modèle Physique-Maths
      • Carte exemple :
          • Front : Donner l'équation de Schrödinger dépendante du temps.
          • Back : i \hbar \frac{\partial \Psi}{\partial t} = \hat{H} \Psi

  • Déroulement du test :
      1. Saisie utilisateur : "@model_Physique-Maths Améliore le CSS pour mettre en valeur les formules KaTeX et ajouter un cadre moderne en mode sombre."
      2. Comportement IA :
          • Outil appelé : get_note_type_details(note_type_name="Modèle Physique-Maths")
          • Outil appelé : propose_css_tune(note_type_name="Modèle Physique-Maths", css_snippet="...")
      3. Rendu Visuel attendu :
          • Détection du bloc CSS dans view.py:1320.
          • Le workspace_inspector_widget.py affiche l'aperçu du code CSS et le rendu simulé avec boutons d'application immédiate sur le modèle.


  ──────
  ### 📚 Parcours 4 : Smart Coverage & RAG Documentaire (Détection de Trous d'Apprentissage)

  • Objectif : Vérifier l'intégration documentaire FAISS / Peewee (search_attached_documents, analyze_coverage_gaps).
  • Données de test :
      • Document attaché : cours_respiration_cellulaire.pdf (contenant : Glycolyse, Cycle de Krebs, Chaîne respiratoire mitochondriale, Bilan ATP).
      • Paquet existant : Ne contient que 2 cartes sur la Glycolyse.
  • Déroulement du test :
      1. Saisie utilisateur : "Compare mon paquet @deck_Biologie avec mon cours @doc_cours_respiration_cellulaire.pdf et identifie les notions oubliées."
      2. Comportement IA :
          • Outil appelé : analyze_coverage_gaps(deck_name="Biologie", document_title="cours_respiration_cellulaire.pdf")
          • Observation : 0 carte détectée sur le Cycle de Krebs (complexe pyruvate déshydrogénase) et sur la phosphorylation oxydative (ATP synthase).
          • Proposition proactive de 3 nouvelles cartes atomiques prêtes à être forgées.
      3. Rendu Visuel attendu :
          • Liste de suggestions d'actions directes dans next_steps du volet droit.


  ──────
  ### 🔄 Parcours 5 : Panorama 360°, Analyse Rétention FSRS et Rollback (Undo Time Machine)

  • Objectif : Tester les métriques globales, l'identification des cartes sangsues (Leeches) et la résilience aux erreurs via la commande /undo.
  • Déroulement du test :
      1. Saisie utilisateur : "/panorama" ou "/deepscan"
      2. Comportement IA :
          • Outil appelé : get_collection_panorama_360() et inspect_deck_deep_scan(deck_name="...")
          • L'IA synthétise le nombre total de cartes, le taux de rétention moyen, et liste les cartes ayant un taux d'échec anormal (> 4 lapses).
          • L'IA propose une reformulation de la carte la plus difficile.
      3. L'utilisateur clique sur [ ✅ Appliquer en BDD ].
      4. L'utilisateur tape ensuite : "/undo"
      5. Comportement système :
          • Déclenchement de _undo_last_card_modification() : restauration instantanée de la version précédente depuis note.py, mise à jour du compteur et notification Toast confirmant le rollback.
