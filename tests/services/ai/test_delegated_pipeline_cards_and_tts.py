"""Tests de bout en bout et unitaires pour les sorties typées et batch_note_create en mode délégué MCP.

Vérifie que :
1. _execute_delegated_ia_step parse le JSON et affecte output_variable (ex: generated_cards).
2. Si le JSON contient une clé 'notes' ou 'cards', la liste est normalisée dans generated_cards.
3. L'étape AUDIO_TTS en aval s'exécute avec succès sur les cartes générées et enrichit le champ cible.
4. L'orchestrateur scelle le bundle délégué ET crée un StagedBundle avec un patch batch_note_create final.
5. DelegatedStepPatchApplier permet à apply_staged_patch et apply_bundle_all de réussir sur pipeline_step_delegated.
6. Le patch batch_note_create est applicable via apply_bundle_all et crée les notes en base avec l'audio.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from ankidraft.database.models import (
    CardModel,
    DeckModel,
    NoteModel,
    NoteTypeModel,
    PersonaModel,
    PipelineModel,
    PipelineStepModel,
    StagedPatchModel,
)
from ankidraft.services.ai.orchestrator import PipelineOrchestrator
from ankidraft.services.ai.patch_appliers import get_patch_applier
from ankidraft.services.ai.staged_patch_registry import StagedPatchRegistry


@pytest.fixture
def test_env(mock_db: Any) -> dict[str, Any]:
    deck = DeckModel.create(name="Japonais::Vocabulaire")
    note_type = NoteTypeModel.create(
        name="Japonais_Audio",
        fields_schema=json.dumps([{"name": "Front"}, {"name": "Back"}, {"name": "Audio"}]),
        templates=json.dumps([{"name": "Carte 1", "qfmt": "{{Front}}", "afmt": "{{Front}}<hr>{{Back}}<br>{{Audio}}"}]),
    )
    persona = PersonaModel.create(
        name="Sensei",
        system_prompt="Génère des fiches de vocabulaire japonais au format JSON.",
        persona_type="pipeline",
    )
    pipeline = PipelineModel.create(name="Pipeline Japonais Delegue", description="Extraction de vocabulaire.")

    # Étape 1 : LLM_PROMPT déléguée
    step1 = PipelineStepModel.create(
        pipeline=pipeline,
        persona=persona,
        step_order=1,
        step_type="LLM_PROMPT",
        config_data=json.dumps(
            {
                "output_format": "json",
                "output_variable": "generated_cards",
            }
        ),
    )

    # Étape 2 : AUDIO_TTS
    step2 = PipelineStepModel.create(
        pipeline=pipeline,
        step_order=2,
        step_type="AUDIO_TTS",
        config_data=json.dumps(
            {
                "source_field": "Front",
                "target_field": "Audio",
                "engine": "edge-tts",
                "voice": "ja-JP-NanamiNeural",
                "insertion_mode": "append",
            }
        ),
    )

    return {
        "deck": deck,
        "note_type": note_type,
        "persona": persona,
        "pipeline": pipeline,
        "step1": step1,
        "step2": step2,
    }


@pytest.mark.unit
def test_delegated_step_patch_applier_lookup_and_apply(mock_db: Any) -> None:
    """DelegatedStepPatchApplier prend en charge pipeline_step_delegated et valide la trace d'audit."""
    applier = get_patch_applier("pipeline_step_delegated")
    assert applier is not None, "get_patch_applier('pipeline_step_delegated') doit retourner une stratégie dédiée."

    bundle_id = StagedPatchRegistry.begin_bundle(title="Audit bundle", explanation="Trace d'audit")
    patch_obj = StagedPatchRegistry.create_patch(
        patch_type="pipeline_step_delegated",
        diff_payload={
            "type": "pipeline_step_delegated",
            "step_order": 1,
            "pipeline_id": 1,
            "generated_content": '{"notes": [{"Front": "食べる", "Back": "Manger"}]}',
        },
        bundle_id=bundle_id,
    )
    StagedPatchRegistry.commit_bundle(bundle_id)

    res = StagedPatchRegistry.apply_staged_patch(patch_obj.patch_id)
    assert res["status"] == "applied"
    reloaded = StagedPatchModel.get_by_id(patch_obj.id)
    assert reloaded.status == "applied"


@pytest.mark.unit
def test_execute_delegated_ia_step_json_and_output_variable(test_env: dict[str, Any]) -> None:
    """_execute_delegated_ia_step parse le JSON, positionne output_variable et extrait generated_cards."""
    pipeline = test_env["pipeline"]
    step1 = test_env["step1"]

    generated_json = json.dumps(
        {
            "notes": [
                {"Front": "日本語", "Back": "Langue japonaise"},
                {"Front": "本", "Back": "Livre"},
            ]
        }
    )

    def mock_provider(request: dict[str, Any]) -> dict[str, Any]:
        return {"content": generated_json, "status": "completed"}

    orch = PipelineOrchestrator(
        pipeline_id=pipeline.id,
        execution_mode="mcp_delegated",
        delegate_content_provider=mock_provider,
    )

    orch._execute_delegated_ia_step(step1)

    # 1. output_variable est renseigné
    out_cards = orch.state.get_variable("generated_cards")
    assert isinstance(out_cards, list)
    assert len(out_cards) == 2
    assert out_cards[0]["Front"] == "日本語"
    assert out_cards[1]["Front"] == "本"

    # 2. Le résultat d'étape est désérialisé
    res1 = orch.state.get_variable("result_step_1")
    assert isinstance(res1, dict)
    assert "notes" in res1


@pytest.mark.unit
def test_delegated_pipeline_end_to_end_with_tts_and_batch_note_create(test_env: dict[str, Any]) -> None:
    """Un pipeline complet délégué enchaîne l'étape IA, la synthèse AUDIO_TTS, puis crée batch_note_create."""
    pipeline = test_env["pipeline"]
    deck = test_env["deck"]
    note_type = test_env["note_type"]

    cards_json = json.dumps(
        [
            {"Front": "猫", "Back": "Chat"},
            {"Front": "犬", "Back": "Chien"},
        ]
    )

    def mock_provider(request: dict[str, Any]) -> dict[str, Any]:
        return {"content": cards_json, "status": "completed"}

    orch = PipelineOrchestrator(
        pipeline_id=pipeline.id,
        execution_mode="mcp_delegated",
        delegate_content_provider=mock_provider,
    )
    orch.state.set_variable("deck_name", deck.name)
    orch.state.set_variable("note_type_name", note_type.name)
    orch.state.set_variable("auto_stage_bundle", True)

    fake_tts = MagicMock()
    fake_tts.synthesize.side_effect = [
        ("[sound:neko.mp3]", 1200),
        ("[sound:inu.mp3]", 1100),
    ]

    with patch("ankidraft.services.cards.tts_service.get_tts_service", return_value=fake_tts):
        orch.run()

    # 1. Les cartes dans l'état ont été enrichies par AUDIO_TTS
    final_cards = orch.state.get_variable("generated_cards")
    assert len(final_cards) == 2
    assert "[sound:neko.mp3]" in final_cards[0]["Audio"]
    assert "[sound:inu.mp3]" in final_cards[1]["Audio"]

    # 2. Le bundle d'audit délégué est scellé
    delegated_patches = list(StagedPatchModel.select().where(StagedPatchModel.patch_type == "pipeline_step_delegated"))
    assert len(delegated_patches) == 1
    assert delegated_patches[0].bundle is not None
    assert delegated_patches[0].bundle.status == "pending"

    # 3. Le bundle final contient le patch batch_note_create
    batch_patches = list(StagedPatchModel.select().where(StagedPatchModel.patch_type == "batch_note_create"))
    assert len(batch_patches) == 1
    batch_patch = batch_patches[0]
    assert batch_patch.bundle is not None
    batch_payload = json.loads(batch_patch.diff_payload)
    assert batch_payload["type"] == "batch_note_create"
    assert len(batch_payload["notes"]) == 2
    assert "[sound:neko.mp3]" in batch_payload["notes"][0]["fields"]["Audio"]

    # 4. On peut appliquer le bundle de création de cartes via apply_bundle_all
    apply_res = StagedPatchRegistry.apply_bundle_all(batch_patch.bundle.bundle_id)
    assert apply_res["status"] == "applied"
    assert apply_res["applied_steps_count"] == 1

    # 5. Les notes et cartes existent maintenant en base SQLite avec l'audio injecté
    created_notes = list(NoteModel.select())
    assert len(created_notes) == 2
    created_cards = list(CardModel.select().where(CardModel.deck == deck))
    assert len(created_cards) == 2
    note1 = created_notes[0]
    v1 = note1.versions.first()
    assert v1 is not None
    assert "[sound:neko.mp3]" in v1.content or "[sound:inu.mp3]" in v1.content


@pytest.mark.unit
def test_apply_bundle_all_with_delegated_step_and_batch_create(test_env: dict[str, Any]) -> None:
    """apply_bundle_all s'exécute sans échec sur un bundle combinant pipeline_step_delegated et batch_note_create."""
    deck = test_env["deck"]
    note_type = test_env["note_type"]

    bundle_id = StagedPatchRegistry.begin_bundle(
        title="Bundle mixte audit et création",
        explanation="Test mixité d'étapes",
    )

    # Patch 1 : pipeline_step_delegated (audit)
    StagedPatchRegistry.create_patch(
        patch_type="pipeline_step_delegated",
        diff_payload={
            "type": "pipeline_step_delegated",
            "step_order": 1,
            "pipeline_id": 99,
            "generated_content": "Trace brute",
        },
        bundle_id=bundle_id,
    )

    # Patch 2 : batch_note_create
    StagedPatchRegistry.create_patch(
        patch_type="batch_note_create",
        diff_payload={
            "type": "batch_note_create",
            "notes": [
                {
                    "deck": deck.name,
                    "note_type": note_type.name,
                    "fields": {"Front": "桜", "Back": "Cerisier en fleurs", "Audio": "[sound:sakura.mp3]"},
                    "tags": ["nature"],
                }
            ],
            "count": 1,
            "default_deck": deck.name,
            "default_note_type": note_type.name,
        },
        bundle_id=bundle_id,
    )

    StagedPatchRegistry.commit_bundle(bundle_id)

    res = StagedPatchRegistry.apply_bundle_all(bundle_id)
    assert res["status"] == "applied"
    assert res["applied_steps_count"] == 2

    # Vérification que la note existe bien
    notes = list(NoteModel.select().join(CardModel).where(CardModel.deck == deck))
    assert any("桜" in n.versions.first().content for n in notes if n.versions.first())
