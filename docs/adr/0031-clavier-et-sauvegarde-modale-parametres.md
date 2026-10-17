# Sécurisation du clavier et persistance explicite de la modale de paramètres

**Statut :** accepté

Afin d'éliminer toute perte de données et toute fermeture impromptue lors de la configuration de l'application, nous neutralisons le comportement par défaut de `QDialog` sur la touche Entrée au sein de `SettingsModal`, nous lions l'appui sur `Entrée` dans les champs de saisie à la sauvegarde immédiate sans fermeture, et nous instaurons le raccourci universel `Ctrl+S` / `Cmd+S` pour la persistance à chaud de l'ensemble des onglets.

---

## Le Problème

1. **Fermeture accidentelle sans persistance (`QDialog.accept`)** : `SettingsModal` hérite de `QDialog`. Par défaut dans Qt, tout `QPushButton` instancié dans un dialogue possède l'attribut `autoDefault = True`. Lors d'un appui sur la touche `Entrée` dans un champ de saisie (`QLineEdit`), l'événement remonte au dialogue et déclenche soit le premier bouton actif (`btn_cancel` ou `btn_close`), soit la méthode native `QDialog.accept()`. Comme `SettingsModal` ne surchargeait pas `accept()`, la modale se fermait instantanément sans invoquer `_save_all()`, annulant silencieusement toutes les modifications utilisateur.
2. **Frustration sur les champs de drapeaux Anki (`AnkiSyncTab`)** : Lors de la personnalisation des libellés des 7 drapeaux colorés d'Anki, l'utilisateur valide instinctivement sa frappe par `Entrée` pour enregistrer son libellé. Cette frappe expulsait l'utilisateur de la modale sans sauvegarder son texte.
3. **Absence de raccourci clavier standard pour la sauvegarde** : La modale disposait du raccourci `Échap` pour fermer, mais d'aucun raccourci clavier pour enregistrer les paramètres sans recourir à la souris.

---

## Options Considérées

1. **Conserver le comportement natif de `QDialog` en activant `setDefault(True)` sur `btn_save_all`** :
   *Rejeté*. Dans Qt, un dialogue modal standard interprète l'acceptation par Entrée comme une volonté de valider *et fermer* la fenêtre. Or, dans une modale riche à 7 onglets (Général, Moteurs IA, Anki, TTS, Maintenance, Extensions, Support), l'utilisateur configure fréquemment plusieurs sections à la suite. Fermer brutalement la fenêtre casse son flux de travail.
2. **Interdire purement et simplement la touche Entrée dans les champs** :
   *Rejeté*. La touche Entrée deviendrait inopérante, ce qui va à l'encontre des habitudes ergonomiques des utilisateurs qui s'attendent à valider leur saisie.
3. **Neutralisation de la fermeture accidentelle, validation par Entrée en place avec toast et raccourci `Ctrl+S` / `Cmd+S`** :
   *Retenu*.

---

## Décisions et Règles d'Architecture

### 1. Neutralisation du comportement de fermeture de `QDialog`
- Désactivation explicite d'`autoDefault` sur tous les boutons secondaires, icônes et boutons de fermeture de `SettingsModal` (`setAutoDefault(False)`).
- Surcharge de `keyPressEvent(event)` dans `SettingsModal` : interception des touches `Qt.Key.Key_Return` et `Qt.Key.Key_Enter` au niveau racine pour interdire l'appel aveugle à `QDialog.accept()`.
- Surcharge préventive de `accept()` pour rediriger vers `_save_all()` au lieu d'une fermeture muette.

### 2. Validation par Entrée sur les champs de saisie simple (`QLineEdit`)
- Dans `AnkiSyncTab` et l'ensemble des onglets de configuration, la touche `Entrée` (`returnPressed`) dans un `QLineEdit` (notamment les 7 champs `flag_inputs`) déclenche l'enregistrement global `_save_all()`.
- L'enregistrement persiste les réglages modifiés, applique les changements d'apparence/thème à chaud, affiche le statut vert et émet un toast non bloquant de confirmation sans fermer la modale.

### 3. Navigation ergonomique par tabulation (`Tab` / `Shift+Tab`)
- La navigation séquentielle entre les 7 drapeaux d'Anki (indices 1 à 7) est garantie dans l'ordre croissant via le focus order de Qt et l'enchaînement des widgets dans la grille.
- L'utilisateur peut ainsi enchaîner les saisies avec `Tab` puis valider l'ensemble à la fin avec `Entrée` ou `Ctrl+S`.

### 4. Raccourci universel d'enregistrement `Ctrl+S` / `Cmd+S`
- Ajout d'un `QShortcut` mappé sur `QKeySequence.StandardKey.Save` (`Ctrl+S` sous Windows/Linux, `Cmd+S` sous macOS) dans `SettingsModal`.
- Ce raccourci déclenche `_save_all()`, offrant une parité clavier totale avec l'action du bouton principal de pied de page.

### 5. Repli canonique sur les libellés de drapeaux vides
- Un champ de drapeau laissé vide ou vidé par l'utilisateur lors de la saisie applique automatiquement le repli vers le nom par défaut du jeton Anki (`DesignTokens.FLAG_NAMES[idx]`, ex: « Drapeau 1 »).
- Aucun drapeau ne conserve un libellé vide dans la base de données de profil.
