# Théorème de Bayes

Le **théorème de Bayes** est un résultat fondamental en théorie des probabilités qui exprime la probabilité conditionnelle d'un événement $A$ sachant un événement $B$ :

$$P(A \mid B) = \frac{P(B \mid A) \cdot P(A)}{P(B)}$$

Où :
- $P(A)$ est la probabilité *a priori* de l'événement $A$.
- $P(B \mid A)$ est la vraisemblance de $B$ sachant $A$.
- $P(A \mid B)$ est la probabilité *a posteriori*.
- $P(B)$ est la probabilité totale marginale :

$$P(B) = \sum_{i} P(B \mid A_i) \cdot P(A_i)$$

## Applications en Intelligence Artificielle

En apprentissage automatique, les classifieurs Bayésiens Naïfs reposent sur l'hypothèse d'indépendance conditionnelle des variables explicatives :

$$P(y \mid x_1, \dots, x_n) \propto P(y) \prod_{i=1}^n P(x_i \mid y)$$
