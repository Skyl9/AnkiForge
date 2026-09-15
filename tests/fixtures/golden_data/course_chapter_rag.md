# Chapitre 1 : Architecture des Systèmes Distribués

## 1.1 Théorème CAP
Formulé par Eric Brewer, le théorème CAP stipule qu'un système distribué ne peut garantir simultanément que deux des trois propriétés suivantes :

1. **Cohérence (Consistency)** : Chaque lecture reçoit l'écriture la plus récente ou une erreur.
2. **Disponibilité (Availability)** : Chaque requête non-échouée reçoit une réponse non-erronée.
3. **Tolérance au Partitionnement (Partition Tolerance)** : Le système continue de fonctionner malgré la perte de messages réseau.

## 1.2 Consensus Distribué : Paxos et Raft
Le consensus dans les systèmes tolérants aux pannes est résolu via :
- **Paxos** : Algorithme classique à quorum, prouvé mathématiquement par Leslie Lamport.
- **Raft** : Algorithme conçu par Diego Ongaro et John Ousterhout pour être plus intelligible que Paxos.

Raft s'articule autour de trois rôles : *Leader*, *Follower*, et *Candidate*. Les élections utilisent des délais de garde aléatoires (*election timeouts*).
