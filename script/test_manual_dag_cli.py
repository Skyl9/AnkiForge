#!/usr/bin/env python3
"""
Test Manuel Interactif (CLI) du Moteur DAG d'AnkiForge.
Permet d'exécuter différents scénarios réels ou simulés pour tester :
1. Pipeline de Création avec Copilote Intentionnel (RAG -> Plan -> Pause Humaine -> Map-Reduce -> Linteur)
2. Pipeline d'Audit de Masse (Map-Reduce sur des cartes -> Détection de Cartes Malades -> Correction)
3. Graphe avec Branchements Conditionnels et Récupération d'Erreur (on_success / on_failure)

Usage:
    python script/test_manual_dag_cli.py
    ou
    uv run python script/test_manual_dag_cli.py
"""

import json
import sys
import time
from typing import Any

from PySide6.QtCore import QCoreApplication

from ankiforge.database.models import LLMConfigModel, PersonaModel, PipelineModel, PipelineStepModel, db
from ankiforge.services.ai.base import LLMProvider
from ankiforge.services.ai.flexible_service import AIManager
from ankiforge.services.ai.orchestrator import PipelineOrchestrator
from ankiforge.services.ai.state import PipelineRunState

# Couleurs ANSI pour un affichage CLI soigné
C_RESET = "\033[0m"
C_BOLD = "\033[1m"
C_CYAN = "\033[96m"
C_GREEN = "\033[92m"
C_YELLOW = "\033[93m"
C_RED = "\033[91m"
C_MAGENTA = "\033[95m"
C_BLUE = "\033[94m"


class MockInteractiveProvider(LLMProvider):
    """Fournisseur IA simulé produisant des réponses structurées instantanément."""

    def generate(self, system_prompt: str, user_prompt: str | list[dict[str, Any]], response_format: str = "json") -> str:
        prompt_str = (system_prompt + " " + str(user_prompt)).lower()

        # Scénario Plan de cours
        if "architecte" in prompt_str or "plan" in prompt_str:
            return json.dumps(
                {
                    "titre_cours": "Introduction aux Réseaux de Neurones",
                    "concepts_cles": [
                        "1. Le Perceptron et la fonction d'activation",
                        "2. La rétropropagation du gradient",
                        "3. L'overfitting et la régularisation (Dropout/L2)",
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )

        # Scénario Linteur Wozniak / Audit
        if any(k in prompt_str for k in ["linter", "audit", "analyse", "conforme", "malade"]):
            return json.dumps(
                {
                    "cards": [
                        {
                            "Front": f"[Audit OK] {str(user_prompt)[:50]}...",
                            "Back": "Formulation courte, univoque et conforme aux 20 règles de Wozniak.",
                            "status": "VALID",
                        }
                    ]
                },
                ensure_ascii=False,
                indent=2,
            )

        # Scénario Génération de cartes
        if any(k in prompt_str for k in ["générateur", "rédacteur", "flashcard", "item", "concept"]):
            return json.dumps(
                {
                    "cards": [
                        {
                            "Front": f"Quel est le rôle du concept suivant : {str(user_prompt)[:60]} ?",
                            "Back": "Il permet d'ajuster les poids synaptiques pour minimiser la fonction de perte.",
                        }
                    ]
                },
                ensure_ascii=False,
                indent=2,
            )

        if response_format == "json":
            return json.dumps({"result": "Réponse JSON simulée par défaut"}, ensure_ascii=False)
        return "Réponse textuelle simulée par défaut."


def setup_in_memory_db():
    """Initialise une base de données temporaire pour le test."""
    from ankiforge.database.models import (
        DeckModel,
        NoteTypeModel,
        NoteModel,
        CardModel,
        PersonaModel,
        PipelineModel,
        PipelineStepModel,
    )

    db.init(":memory:")
    db.connect()
    db.create_tables(
        [
            DeckModel,
            NoteTypeModel,
            NoteModel,
            CardModel,
            PersonaModel,
            PipelineModel,
            PipelineStepModel,
            LLMConfigModel,
        ]
    )


def print_banner(title: str):
    print(f"\n{C_CYAN}{'=' * 70}{C_RESET}")
    print(f"{C_BOLD}{C_CYAN} 🧪 {title.upper()}{C_RESET}")
    print(f"{C_CYAN}{'=' * 70}{C_RESET}\n")


def attach_console_signals(orchestrator: PipelineOrchestrator, on_human_pause_fn=None):
    """Connecte les signaux de l'orchestrateur aux logs console."""

    def on_step_start(order: int, desc: str):
        print(f" {C_YELLOW}▶ [{order}]{C_RESET} {desc}")

    def on_step_progress(curr: int, total: int, msg: str):
        print(f"    {C_BLUE}↳ Prog: [{curr}/{total}]{C_RESET} {msg}")

    def on_step_done(order: int, state: PipelineRunState):
        print(f" {C_GREEN}✔ Étape {order} terminée avec succès.{C_RESET}")

    def on_human(state: PipelineRunState):
        print(f"\n{C_MAGENTA}{'!' * 60}")
        print(" ⏸️  INTERRUPTION : VALIDATION HUMAINE REQUISE (Copilote Intentionnel)")
        print(f"{'!' * 60}{C_RESET}\n")
        if on_human_pause_fn:
            on_human_pause_fn(orchestrator, state)

    def on_finish(state: PipelineRunState):
        print(f"\n{C_GREEN}{C_BOLD}🎉 PIPELINE TERMINÉ AVEC SUCCÈS !{C_RESET}")
        print(f" 📊 Nombre d'étapes dans l'historique : {len(state.execution_history)}")
        cards = state.get_variable("generated_cards", [])
        if not cards:
            cards = state.get_variable("map_reduce_results", [])
        print(f" 🗂️  Résultats / Cartes : {len(cards)}")
        for i, card in enumerate(cards, 1):
            if isinstance(card, dict):
                front = card.get("Front", card.get("front", card.get("result", str(card))))
                back = card.get("Back", card.get("back", card.get("status", "")))
                print(f"    Item #{i} | Recto/Info: {front} => Verso/Statut: {back}")
            else:
                print(f"    Item #{i} | {card}")

    def on_error(err: str):
        print(f"\n{C_RED}{C_BOLD}❌ ERREUR FATALE : {err}{C_RESET}")

    orchestrator.signals.step_started.connect(on_step_start)
    orchestrator.signals.step_progress.connect(on_step_progress)
    orchestrator.signals.step_completed.connect(on_step_done)
    orchestrator.signals.human_validation_required.connect(on_human)
    orchestrator.signals.pipeline_finished.connect(on_finish)
    orchestrator.signals.error_occurred.connect(on_error)


# ==============================================================================
# SCÉNARIO 1 : Pipeline de Création avec Copilote Intentionnel
# ==============================================================================
def run_scenario_creation(ai_provider: LLMProvider):
    print_banner("Scénario 1 : Création Complète avec Copilote Intentionnel (Validation Humaine)")

    pipeline = PipelineModel.create(name="Pipeline Création & Validation")

    # Étape 1 : RAG
    PipelineStepModel.create(
        pipeline=pipeline,
        step_order=1,
        step_type="RAG_RETRIEVAL",
    )

    # Étape 2 : Architecte de cours (Génération du Plan)
    p_architecte = PersonaModel.create(
        name="Architecte de Cours",
        system_prompt="Extrais les concepts clés du cours sous format JSON { 'titre_cours': str, 'concepts_cles': list }.",
        output_format="json",
    )
    PipelineStepModel.create(
        pipeline=pipeline,
        persona=p_architecte,
        step_order=2,
        step_type="LLM_PROMPT",
    )

    # Étape 3 : Pause interactive (Validation Humaine)
    PipelineStepModel.create(
        pipeline=pipeline,
        step_order=3,
        step_type="HUMAN_VALIDATION",
    )

    # Étape 4 : Map-Reduce sur les concepts validés
    p_redacteur = PersonaModel.create(
        name="Rédacteur Flashcards",
        system_prompt="Génère des flashcards parfaites au format JSON { 'cards': [{'Front': '...', 'Back': '...'}] } pour le concept : {{ item }}.",
        output_format="json",
    )
    PipelineStepModel.create(
        pipeline=pipeline,
        persona=p_redacteur,
        step_order=4,
        step_type="MAP_REDUCE",
    )

    # Étape 5 : Linter Wozniak de finition
    p_linter = PersonaModel.create(
        name="Linter Wozniak",
        system_prompt="Valide et nettoie les flashcards générées : {{ last_output }}.",
        output_format="json",
    )
    PipelineStepModel.create(
        pipeline=pipeline,
        persona=p_linter,
        step_order=5,
        step_type="LLM_PROMPT",
    )

    initial_state = PipelineRunState(initial_prompt="Introduction aux Réseaux de Neurones Profonds")
    initial_state.set_variable(
        "text_source",
        "Le Perceptron est l'unité de base. La rétropropagation permet de calculer le gradient de l'erreur. Le surapprentissage (overfitting) se combat avec le Dropout et la régularisation L2.",
    )

    def handle_human_pause(orch: PipelineOrchestrator, state: PipelineRunState):
        last_out = state.get_variable("last_output", {})
        print(f"{C_BOLD}Plan extrait par l'IA :{C_RESET}")
        print(json.dumps(last_out, ensure_ascii=False, indent=2))

        print(f"\n{C_YELLOW}Options :{C_RESET}")
        print(" [1] Valider le plan tel quel")
        print(" [2] Modifier / Ajouter un concept avant de continuer")
        choice = input(f"{C_CYAN}Votre choix (défaut=1) : {C_RESET}").strip() or "1"

        if choice == "2":
            new_concept = input(f"{C_CYAN}Entrez un concept additionnel : {C_RESET}").strip()
            if new_concept:
                if isinstance(last_out, dict) and "concepts_cles" in last_out:
                    last_out["concepts_cles"].append(new_concept)
                    state.set_variable("last_output", last_out)
                    state.set_variable("map_items", last_out["concepts_cles"])
                    print(f"{C_GREEN}Concept ajouté avec succès !{C_RESET}")
        else:
            if isinstance(last_out, dict) and "concepts_cles" in last_out:
                state.set_variable("map_items", last_out["concepts_cles"])

        print(f"{C_GREEN}▶ Reprise du Pipeline...{C_RESET}\n")
        orch.resume(state)

    orchestrator = PipelineOrchestrator(
        pipeline_id=pipeline.id,
        initial_state=initial_state,
        ai_provider=ai_provider,
    )
    attach_console_signals(orchestrator, handle_human_pause)
    orchestrator.run()


# ==============================================================================
# SCÉNARIO 2 : Audit Médical de Paquet par Map-Reduce
# ==============================================================================
def run_scenario_audit_map_reduce(ai_provider: LLMProvider):
    print_banner("Scénario 2 : Audit Médical de Paquet par Map-Reduce")

    pipeline = PipelineModel.create(name="Pipeline Audit Wozniak")

    p_linter = PersonaModel.create(
        name="Linter de Conformité",
        system_prompt="Analyse cette carte : {{ item }}. Indique si elle est conforme ou malade.",
        output_format="json",
    )
    PipelineStepModel.create(
        pipeline=pipeline,
        persona=p_linter,
        step_order=1,
        step_type="MAP_REDUCE",
    )

    # 4 cartes de test
    sample_cards = [
        {"Front": "Quelle est la capitale de l'Australie ?", "Back": "Canberra"},
        {"Front": "Expliquez toute l'histoire de la Révolution Française en 10 pages", "Back": "Beaucoup trop long..."},
        {"Front": "Formule d'Euler", "Back": "e^(i*pi) + 1 = 0"},
        {"Front": "Quels sont les 12 symptômes de la maladie X ?", "Back": "A, B, C, D, E, F, G, H, I, J, K, L"},
    ]

    initial_state = PipelineRunState()
    initial_state.set_variable("map_items", sample_cards)

    orchestrator = PipelineOrchestrator(
        pipeline_id=pipeline.id,
        initial_state=initial_state,
        ai_provider=ai_provider,
    )
    attach_console_signals(orchestrator)
    orchestrator.run()


# ==============================================================================
# SCÉNARIO 3 : Branchements DAG & Gestion d'Erreur (on_success / on_failure)
# ==============================================================================
def run_scenario_dag_branching(ai_provider: LLMProvider):
    print_banner("Scénario 3 : Branchements DAG Conditionnels et Récupération d'Erreur")

    pipeline = PipelineModel.create(name="Pipeline Branchements")
    persona_main = PersonaModel.create(name="Action Normale", system_prompt="Action Normale", output_format="text")
    persona_skip = PersonaModel.create(name="Action Sautée", system_prompt="Action Sautée", output_format="text")
    persona_target = PersonaModel.create(name="Action Cible Saut", system_prompt="Action Cible", output_format="text")

    step1 = PipelineStepModel.create(pipeline=pipeline, persona=persona_main, step_order=1, step_type="LLM_PROMPT")
    PipelineStepModel.create(pipeline=pipeline, persona=persona_skip, step_order=2, step_type="LLM_PROMPT")
    step3_target = PipelineStepModel.create(pipeline=pipeline, persona=persona_target, step_order=3, step_type="LLM_PROMPT")

    # Branchement : Étape 1 saute directement à Étape 3
    step1.on_success_step = step3_target
    step1.save()

    orchestrator = PipelineOrchestrator(
        pipeline_id=pipeline.id,
        ai_provider=ai_provider,
    )
    attach_console_signals(orchestrator)
    orchestrator.run()


# ==============================================================================
# MENU PRINCIPAL
# ==============================================================================
def main():
    # Initialisation Qt minimal pour signaux
    app = QCoreApplication.instance()
    if not app:
        app = QCoreApplication(sys.argv)

    setup_in_memory_db()

    print(f"\n{C_BOLD}{C_GREEN}🚀 ANKIFORGE — SUITE DE TESTS MANUELS DU MOTEUR DAG{C_RESET}")
    print("Choisissez le moteur d'exécution :")
    print(" [1] Mode Simulé Rapide (MockProvider - Recommandé pour tester sans clé/sans serveur)")
    print(" [2] Mode Réel (Utilise le fournisseur IA configuré dans AnkiForge : Ollama / Gemini / Groq)")

    mode_choice = input(f"\n{C_CYAN}Votre choix (défaut=1) : {C_RESET}").strip() or "1"

    if mode_choice == "2":
        try:
            ai_mgr = AIManager()
            provider = ai_mgr.provider
            print(f"{C_GREEN}✔ Fournisseur IA réel connecté : {type(provider).__name__}{C_RESET}")
        except Exception as e:
            print(f"{C_RED}Erreur d'initialisation du provider réel ({e}), bascule sur Mock.{C_RESET}")
            provider = MockInteractiveProvider()
    else:
        provider = MockInteractiveProvider()
        print(f"{C_GREEN}✔ Fournisseur Mock actif.{C_RESET}")

    while True:
        print(f"\n{C_BOLD}--- MENU DES SCÉNARIOS ---{C_RESET}")
        print(" [1] Scénario 1 : Création de cours avec validation humaine (Copilote)")
        print(" [2] Scénario 2 : Audit de paquet par Map-Reduce")
        print(" [3] Scénario 3 : Branchements DAG conditionnels (on_success / skip)")
        print(" [4] Lancer TOUS les scénarios à la suite")
        print(" [Q] Quitter")

        choice = input(f"\n{C_CYAN}Sélectionnez un scénario : {C_RESET}").strip().upper()

        if choice == "1":
            run_scenario_creation(provider)
        elif choice == "2":
            run_scenario_audit_map_reduce(provider)
        elif choice == "3":
            run_scenario_dag_branching(provider)
        elif choice == "4":
            run_scenario_creation(provider)
            time.sleep(1)
            run_scenario_audit_map_reduce(provider)
            time.sleep(1)
            run_scenario_dag_branching(provider)
        elif choice in ["Q", "QUIT", "EXIT"]:
            print(f"{C_CYAN}Fin des tests manuels. Au revoir !{C_RESET}\n")
            break
        else:
            print(f"{C_RED}Option non reconnue.{C_RESET}")


if __name__ == "__main__":
    main()
