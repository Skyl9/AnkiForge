---
name: codebase-design
description: >-
  Vocabulaire et principes de conception de modules profonds (deep modules) et de coutures (seams) dans AnkiForge. Permet de concevoir des interfaces compactes cachant une grande complexité, faciles à tester et à maintenir.
  Use when the user asks to "codebase-design", "concevoir un module", "modularisation profonde", "deep modules", "placer une couture", "définir une interface", or wants to design clean interfaces with high leverage.
  When NOT to use: Do not use for domain glossary and ADRs (use domain-modeling), writing tests first (use tdd) or running full feature implementation (use implement).
---

# 🏛️ Conception de Modules Profonds (Codebase Design)

Concevoir des **modules profonds (deep modules)** : une grande richesse de comportement métier masquée derrière une interface publique compacte, positionnée sur une couture (seam) nette, testable directement via cette interface. L'objectif est l'**effet de levier** pour les appelants, la **localité** pour les mainteneurs et la **testabilité** sans couplage.

> **Guides associés** :
> - [DEEPENING.md](DEEPENING.md) : Approfondissement d'un groupe de modules selon ses catégories de dépendances.
> - [DESIGN-IT-TWICE.md](DESIGN-IT-TWICE.md) : Exploration d'interfaces alternatives par sous-agents parallèles.

---

## 1. Glossaire Canonique

Employer ces termes avec rigueur :

- **Module** : toute unité associant une interface et une implémentation (fonction, classe, service ou découpage applicatif). *À éviter* : composant, unité, service (termes trop flous).
- **Interface** : tout ce qu'un appelant doit connaître pour utiliser le module correctement (signatures de types, préconditions, invariants, erreurs levées et garanties de performance). *À éviter* : signature, API (trop restrictif).
- **Implémentation** : le corps interne du module masqué derrière l'interface.
- **Profondeur (Depth)** : rapport entre la puissance du comportement fourni et la simplicité de l'interface à apprendre. Un module est **profond** quand une interface réduite pilote une logique riche (ex: `ChunkingService`). Il est **superficiel (shallow)** quand l'interface est presque aussi volumineuse que le code interne.
- **Couture (Seam)** : l'emplacement précis où se situe l'interface et où le comportement peut être altéré (ex: substitution d'un provider IA pour un test) sans modifier l'appelant.
- **Adaptateur (Adapter)** : classe ou fonction concrète satisfaisant une interface à une couture (ex: `OpenAIProvider`, `OllamaProvider` pour `LLMProvider`).
- **Effet de levier (Leverage)** : gain pour les appelants : un petit effort d'apprentissage débloque une grande capacité réutilisable sur N sites d'appel et M tests.
- **Localité (Locality)** : gain pour la maintenance : les modifications, corrections de bogues et vérifications sont concentrées au même endroit plutôt que dispersées.

---

## 2. Modules Profonds vs Superficiels

```
┌─────────────────────────────────┐
│     Interface Réduite           │  ← 2 à 3 méthodes publiques, paramètres simples
├─────────────────────────────────┤
│                                 │
│  Implémentation Profonde        │  ← Logique riche (parsing, cache, fallback)
│                                 │
└─────────────────────────────────┘
```

Lors de la conception d'un module sous `src/ankiforge/`, se poser 3 questions :
1. Peut-on réduire le nombre de méthodes publiques exposées ?
2. Peut-on simplifier les paramètres requis (évitement des dictionnaires fourre-tout) ?
3. Peut-on encapsuler davantage de complexité à l'intérieur ?

---

## 3. Conception pour la Testabilité en Python 3.12

Une bonne interface rend les tests naturels :

### 1. Accepter les dépendances au lieu de les instancier en dur
```python
# TESTABLE : le provider est injecté (seam)
class ExtractionService:
    def __init__(self, provider: LLMProvider | None = None) -> None:
        self.provider = provider or create_default_provider()


# DIFFICILE À TESTER : instanciation interne d'un client externe
class ExtractionService:
    def __init__(self) -> None:
        self.client = OpenAIClient(api_key=os.environ["API_KEY"])
```

### 2. Retourner des résultats purs plutôt que produire des effets de bord
```python
# TESTABLE : fonction pure retournant un rapport
def evaluate_coverage(document: Document, notes: list[Note]) -> CoverageReport: ...


# DIFFICILE À TESTER : modifie directement l'état global ou l'UI
def evaluate_coverage(document: Document, notes: list[Note]) -> None:
    global_state.coverage = 42
    ui_label.setText("42%")
```

---

## When NOT to use this skill

- Ne pas utiliser pour définir le vocabulaire métier ou enregistrer des ADRs → utiliser `/domain-modeling` ou `/grill-with-docs`.
- Ne pas utiliser pour dérouler la boucle Red-Green-Refactor → utiliser `/tdd`.
- Ne pas utiliser pour piloter la réalisation d'un ticket Obsidian de bout en bout → utiliser `/implement`.
