# ruff: noqa: E501
import json
import logging

from ankiforge.database.models.audit import LinterRuleModel

logger = logging.getLogger(__name__)


def seed_default_linter_rules() -> None:
    """Peuple les règles d'audit Wozniak personnalisables par défaut si la table est vide."""
    if LinterRuleModel.select().count() > 0:
        return

    default_rules = [
        {
            "name": "Principe d'Atomicité Minimale",
            "category": "cat-atomicite",
            "category_label": "Atomicité & Restructuration",
            "description": "Une carte ne doit traiter que d'un seul concept ou fait univoque. Si le recto ou le verso contient une liste à puces ou plus de 2 faits distincts, scinder en sous-cartes atomiques.",
            "is_active": True,
            "color": "#f87171",
            "icon_name": "squares-four",
            "prompt_injection": "Vérifie l'atomicité de la carte. Si elle contient une énumération, une liste de plus de 2 éléments, ou pose plusieurs questions à la fois, signale l'erreur 'Principe d'Atomicité Minimale' et propose une scission concise.",
            "example_bad": json.dumps(
                {
                    "Recto": "Expliquer l'allocateur C++20, Valgrind, new vs malloc et delete vs free.",
                    "Verso": "L'allocateur gère le heap, Valgrind détecte les fuites, new alloue avec constructeur, delete détruit.",
                },
                ensure_ascii=False,
            ),
            "example_good": json.dumps(
                {
                    "Recto": "Quel est le rôle de l'allocateur C++20 ?",
                    "Verso": "Gérer l'allocation dynamique de mémoire sur le heap.",
                    "Champ Annexe Extra": "Valgrind et new/delete sont traités dans des cartes dédiées.",
                },
                ensure_ascii=False,
            ),
        },
        {
            "name": "Formatage KaTeX & Clarté Mathématique",
            "category": "cat-katex",
            "category_label": "Formules & Clarté KaTeX",
            "description": "Toute formule mathématique ou chimique doit être rigoureusement formatée en LaTeX entourée de $$...$$ ou $...$.",
            "is_active": True,
            "color": "#c084fc",
            "icon_name": "function",
            "prompt_injection": "Vérifie les notations scientifiques. Si une équation est en texte brut (ex: 'P(A|B) = P(B|A)*P(A)/P(B)') ou si le LaTeX est mal formé, signale 'Formatage KaTeX' et fournis la formule KaTeX exacte.",
            "example_bad": json.dumps({"Recto": "Quelle est la formule du Théorème de Bayes ?", "Verso": "P(A|B) = P(B|A)*P(A)/P(B)"}, ensure_ascii=False),
            "example_good": json.dumps(
                {
                    "Recto": "Quelle est la formule du Théorème de Bayes ?",
                    "Verso": "$$P(A \\mid B) = \\frac{P(B \\mid A) \\cdot P(A)}{P(B)}$$",
                    "Champ Annexe Extra": "P(A|B) = probabilité a posteriori.",
                },
                ensure_ascii=False,
            ),
        },
        {
            "name": "Questions Univoques & Suppression Cloze Surchargé",
            "category": "cat-cloze",
            "category_label": "Questions Univoques Q/R",
            "description": "Les textes à trous ne doivent pas masquer une phrase entière ni créer d'ambiguïté. Remplacer les clozes complexes par des questions directes.",
            "is_active": True,
            "color": "#f59e0b",
            "icon_name": "question",
            "prompt_injection": "Vérifie si la carte utilise un cloze (texte à trous) trop vaste ou ambigu. Si oui, signale 'Questions Univoques' et propose une conversion en question/réponse directe et sans équivoque.",
            "example_bad": json.dumps(
                {"Texte": "Les 5 principes SOLID sont {{c1::Single Responsibility}}, {{c2::Open-Closed}}, {{c3::Liskov}}, {{c4::Interface Segregation}} et {{c5::Dependency Inversion}}."},
                ensure_ascii=False,
            ),
            "example_good": json.dumps(
                {
                    "Recto": "Quel principe SOLID stipule qu'une classe ne doit avoir qu'une seule raison de changer ?",
                    "Verso": "Le principe de responsabilité unique (Single Responsibility Principle - SRP).",
                    "Champ Annexe Extra": "SOLID = SRP, OCP, LSP, ISP, DIP.",
                },
                ensure_ascii=False,
            ),
        },
        {
            "name": "Désambiguïsation & Non-Interférence",
            "category": "cat-interference",
            "category_label": "Désambiguïsation & Contexte",
            "description": "Une question ne doit pas être vague ou prêter à confusion entre deux domaines ou concepts proches. Préciser le contexte minimal.",
            "is_active": True,
            "color": "#3b82f6",
            "icon_name": "circles-three",
            "prompt_injection": "Vérifie que la question n'est pas trop courte ou ambiguë hors contexte. Si deux réponses différentes sont possibles selon la discipline, signale 'Désambiguïsation' et ajoute le préfixe de contexte [Discipline].",
            "example_bad": json.dumps({"Recto": "Quelle est la vitesse limite ?", "Verso": "La vitesse de la lumière c."}, ensure_ascii=False),
            "example_good": json.dumps(
                {
                    "Recto": "[Relativité Restreinte] Quelle est la vitesse limite absolue dans le vide ?",
                    "Verso": "$$c \\approx 3 \\times 10^8 \\text{ m/s}$$",
                    "Champ Annexe Extra": "Invariance de la vitesse de la lumière.",
                },
                ensure_ascii=False,
            ),
        },
    ]

    from ankiforge.database.base import db

    with db.atomic():
        for r in default_rules:
            LinterRuleModel.create(**r)
