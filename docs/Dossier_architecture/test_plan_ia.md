# 🧪 Plan de Test IA - AnkiForge

Ce document répertorie tous les tests à effectuer pour garantir le fonctionnement optimal des différents éléments IA intégrés dans AnkiForge. 

---

## 1. ⚙️ Configuration des Moteurs IA (Settings)

**Objectif :** Vérifier que les moteurs IA s'ajoutent correctement à la base de données et sont rechargeables à la volée.

- [ ] **Ajout d'Ollama :** Dans *Paramètres > Moteurs IA*, cliquer sur "Ajouter Ollama". Vérifier que l'entrée apparaît dans le tableau.
- [ ] **Ajout de Gemini :** Saisir une fausse (ou vraie) clé d'API dans le champ Gemini, puis cliquer sur "Ajouter Gemini". L'entrée doit s'ajouter au tableau avec le modèle `gemini-2.5-flash`.
- [ ] **Suppression :** Sélectionner un moteur dans le tableau et cliquer sur "Supprimer". L'entrée doit disparaître instantanément.
- [ ] **Édition à la volée :** Double-cliquer sur la cellule "Identifiant Modèle" de l'entrée Ollama, la remplacer par `qwen2.5:7b` (ou un autre modèle local dont vous disposez), et appuyer sur Entrée.

---

## 2. 🧠 Le Consultant IA (Tool Calling & Boucle ReAct)

**Objectif :** Valider que le moteur est capable de raisonner, d'invoquer des outils natifs ou manuels, et de s'auto-corriger.

### Test A : Invocation Basique
1. Allez dans le **Consultant IA**.
2. Sélectionnez **Gemini** dans la liste déroulante des moteurs.
3. Demandez : *"Combien d'agents sont configurés dans la base de données ?"*
4. **Comportement attendu :** Un indicateur "⏳ J'utilise l'outil query_peewee..." apparaît temporairement, puis l'IA répond de manière conversationnelle avec le chiffre exact (ex: "Il y a 3 agents").

### Test B : Auto-correction des erreurs (Fallback ReAct)
1. Sélectionnez **Ollama (Qwen)**.
2. Posez la même question : *"Combien d'agents y a-t-il ?"*
3. **Comportement attendu :** L'IA doit réussir à formater le bloc JSON. S'il génère une requête invalide, il ne doit **pas** vous l'afficher. Vous devriez voir l'indicateur d'utilisation d'outil s'afficher plusieurs fois d'affilée en cas de correction interne.

### Test C : L'interdiction d'hallucination de Flashcards
1. Demandez au consultant : *"Fais une requête SQL pour voir les tables."*
2. **Comportement attendu :** L'IA exécute la requête, donne la liste des tables, mais ne vous propose **à aucun moment** de créer une carte Anki avec ce contenu.

---

## 3. 📎 Ingestion Contextuelle (RAG & Analyse)

**Objectif :** S'assurer que le Consultant IA reçoit bien le contexte des documents et paquets de cartes, et l'utilise pour répondre.

- [ ] **Attacher un Paquet :** Cliquez sur le bouton `+` ou tapez `@` dans la barre de chat. Sélectionnez un Paquet (Deck). Vérifiez que le nombre de cartes modifiées/impactées s'affiche en bas.
- [ ] **Question Contextuelle :** Demandez : *"Fais-moi un résumé pédagogique des cartes présentes dans ce paquet."*
- [ ] **Comportement attendu :** L'IA analyse les données JSON du paquet (récupérées en base par le *ConsultantWorker*) et formule une critique ou un résumé détaillé de son contenu.
- [ ] **Réinitialisation :** Cliquez sur le bouton "balai" (Vider la mémoire). Le contexte attaché doit disparaître.

---

## 4. 🎭 Éditeur de Personas (Agents)

**Objectif :** Vérifier l'interconnexion entre la création d'Agents et le menu du Consultant.

- [ ] **Création :** Allez dans l'onglet **Agents**. Créez un nouvel agent appelé "Expert en Biologie" avec le prompt système *"Tu ne parles que de biologie."* et enregistrez-le.
- [ ] **Propagation :** Retournez dans l'onglet **Consultant IA**. Déroulez la liste des Agents en haut à gauche. L'"Expert en Biologie" doit s'y trouver.
- [ ] **Test de personnalité :** Sélectionnez cet agent, et demandez-lui *"Bonjour"*. Il doit adapter sa réponse selon son prompt (ex: *"Bonjour, de quel aspect de la biologie souhaitez-vous discuter ?"*).

---

## 5. 🛠️ Robustesse de l'Interface

- [ ] **Spam de messages :** Cliquez rapidement plusieurs fois sur le bouton Envoyer. Le bouton doit se griser (disabled) pendant que l'IA génère sa réponse pour éviter les envois multiples en parallèle.
- [ ] **Erreurs fatales :** Si vous sélectionnez un moteur Ollama mais que l'application Ollama est éteinte sur votre Mac, le chat doit afficher une bulle rouge d'Erreur (Connection Refused) de manière élégante dans la conversation, sans faire crasher l'application.
