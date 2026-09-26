# Découpage des vues monolithiques en parcours MVVM

**Statut : accepté**

Pour rendre les parcours de création, batch et documents testables sans modifier
leur comportement observable, les vues principales seront découpées en widgets
de section et en ViewModels par parcours métier. Les ViewModels porteront l'état
métier/réactif et la coordination des workers, tandis que les widgets porteront
l'état temporaire, la présentation et les intentions utilisateur. Les services
et repositories resteront des contrats stables ; les façades et signaux publics
des vues seront conservés pour limiter le risque de régression.

Cette option est préférée à une réécriture de services ou à un ViewModel unique
par vue : elle réduit le couplage local et permet des tests de parcours complets
avec dépendances injectées, tout en évitant de recréer un nouveau monolithe.
Chaque tranche doit gérer explicitement l'annulation et les erreurs des workers,
restaurer les sélections documentaires persistées et ne permettre une
optimisation que lorsqu'elle est mesurée ou couverte par un test.
