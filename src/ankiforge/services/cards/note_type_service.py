"""Service partagé de gestion et de migration des types de note (NoteTypeService).

Porte la logique canonique de :
- Remappage intelligent des champs (insensible à la casse, positionnel, avec surcharges explicites).
- Migration atomique de notes vers un autre type de note (en une seule transaction SQLite).
- Préservation absolue des cartes physiques et de leurs états de révision SRS (ivl, reps, lapses, stabilité, etc.).
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from ankiforge.database.models import (
    NoteModel,
    NoteTypeModel,
    NoteVersionModel,
    db,
)

logger = logging.getLogger(__name__)


class NoteTypeService:
    """Service centralisé pour la manipulation et la migration des types de note."""

    ANKI_BUILTIN_TAGS = {"frontside", "tags", "deck", "subdeck", "card", "type", "cardflag"}

    @classmethod
    def validate_structure(cls, model_data: dict[str, Any]) -> tuple[bool, list[str]]:
        """
        Valide la structure complète d'un type de note :
        - Nom non vide
        - Au moins un champ, noms uniques (insensible à la casse) et non vides
        - Gabarits complets (nom, qfmt, afmt non vides)
        - Gabarits référençant des champs existants
        """
        errors: list[str] = []
        name = str(model_data.get("name", "")).strip()
        if not name:
            errors.append("Le nom du type de note ne peut pas être vide.")

        fields = model_data.get("fields_schema", [])
        fields_list: list[str] = []
        if not isinstance(fields, list) or not fields:
            errors.append("Le type de note doit contenir au moins un champ.")
        else:
            seen_lower: set[str] = set()
            for idx, f in enumerate(fields):
                f_name = str(f).strip()
                if not f_name:
                    errors.append(f"Le champ à la position {idx + 1} est vide.")
                    continue
                if f_name.lower() in seen_lower:
                    errors.append(f"Nom de champ en double : '{f_name}'.")
                seen_lower.add(f_name.lower())
                fields_list.append(f_name)

        templates = model_data.get("templates", [])
        if not isinstance(templates, list) or not templates:
            errors.append("Le type de note doit contenir au moins un gabarit (template).")
        else:
            field_names_lower = {f.lower() for f in fields_list}
            for idx, t in enumerate(templates):
                if not isinstance(t, dict):
                    errors.append(f"Le gabarit à la position {idx + 1} n'est pas un dictionnaire.")
                    continue
                t_name = str(t.get("name", "")).strip()
                if not t_name:
                    errors.append(f"Le gabarit à la position {idx + 1} n'a pas de nom.")
                qfmt = str(t.get("qfmt", "")).strip()
                afmt = str(t.get("afmt", "")).strip()
                if not qfmt:
                    errors.append(f"Le gabarit '{t_name or idx + 1}' doit contenir un recto (qfmt) non vide.")
                if not afmt:
                    errors.append(f"Le gabarit '{t_name or idx + 1}' doit contenir un verso (afmt) non vide.")

                for fmt_label, fmt_text in [("recto", qfmt), ("verso", afmt)]:
                    for match in re.findall(r"\{\{([^{}]+)\}\}", fmt_text):
                        tag = match.strip()
                        tag = re.sub(r"^[#^/]", "", tag).strip()
                        if ":" in tag:
                            tag = tag.split(":")[-1].strip()
                        tag_lower = tag.lower()
                        if tag_lower not in cls.ANKI_BUILTIN_TAGS and tag_lower not in field_names_lower:
                            errors.append(f"Le gabarit '{t_name or idx + 1}' ({fmt_label}) référence un champ inexistant : '{{{{{match}}}}}'.")

        return (len(errors) == 0, errors)

    @classmethod
    def remap_fields(
        cls,
        source_data: dict[str, Any],
        target_fields: list[str],
        mapping_champs: dict[str, str] | None = None,
    ) -> dict[str, str]:
        """
        Remappe les données de champs d'une note source vers les champs cibles d'un nouveau type de note.

        Ordre de priorité :
        1. Surcharge explicite via `mapping_champs` (source -> cible ou cible -> source).
        2. Correspondance insensible à la casse du nom de champ.
        3. Correspondance positionnelle selon l'ordre d'apparition d'origine.
        4. Chaîne vide par défaut.
        """
        mapped_data: dict[str, str] = {}
        old_keys = list(source_data.keys())

        # Construire une table de correspondance normalisée pour les surcharges explicites
        explicit_target_map: dict[str, str] = {}
        if mapping_champs:
            for k, v in mapping_champs.items():
                k_str = str(k).strip()
                v_str = str(v).strip()
                # Si k est un champ source et v est un champ cible
                if k_str in source_data and v_str in target_fields:
                    explicit_target_map[v_str] = str(source_data[k_str])
                # Si k est un champ cible et v est un champ source
                elif k_str in target_fields and v_str in source_data:
                    explicit_target_map[k_str] = str(source_data[v_str])
                # Tolérance insensible à la casse pour le mapping explicite
                else:
                    for src_k, src_v in source_data.items():
                        for tgt_f in target_fields:
                            if k_str.lower() == src_k.lower() and v_str.lower() == tgt_f.lower() or k_str.lower() == tgt_f.lower() and v_str.lower() == src_k.lower():
                                explicit_target_map[tgt_f] = str(src_v)

        for i, nf in enumerate(target_fields):
            # 1. Surcharge explicite
            if nf in explicit_target_map:
                mapped_data[nf] = explicit_target_map[nf]
                continue

            # 2. Correspondance par nom insensible à la casse
            matched_val = None
            for ok, ov in source_data.items():
                if ok.lower().strip() == nf.lower().strip():
                    matched_val = str(ov) if ov is not None else ""
                    break

            if matched_val is not None:
                mapped_data[nf] = matched_val
            # 3. Correspondance positionnelle
            elif i < len(old_keys):
                raw_val = source_data[old_keys[i]]
                mapped_data[nf] = str(raw_val) if raw_val is not None else ""
            # 4. Chaîne vide par défaut
            else:
                mapped_data[nf] = ""

        return mapped_data

    @classmethod
    def resolve_target_model(cls, target_model: NoteTypeModel | str | int) -> NoteTypeModel:
        """Résout un type de note cible par instance, id numérique ou nom."""
        if isinstance(target_model, NoteTypeModel):
            return target_model

        if isinstance(target_model, int):
            nt = NoteTypeModel.get_or_none(NoteTypeModel.id == target_model)
            if nt:
                return nt
            raise ValueError(f"Type de note cible #{target_model} introuvable.")

        name_str = str(target_model).strip()
        if name_str.isdigit():
            nt_by_id = NoteTypeModel.get_or_none(NoteTypeModel.id == int(name_str))
            if nt_by_id:
                return nt_by_id

        nt_by_name = NoteTypeModel.get_or_none(NoteTypeModel.name == name_str)
        if nt_by_name:
            return nt_by_name

        # Recherche insensible à la casse
        for candidate in NoteTypeModel.select():
            if candidate.name.lower() == name_str.lower():
                return candidate

        raise ValueError(f"Type de note cible '{target_model}' introuvable.")

    @classmethod
    def change_note_type(
        cls,
        note_ids: list[int],
        target_model: NoteTypeModel | str | int,
        mapping_champs: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """
        Migre un lot de notes vers un autre type de note.

        Garanties :
        - Transaction unique (atomicité totale : tout ou rien).
        - Les cartes physiques ne sont JAMAIS supprimées ni recréées.
        - L'historique et les statistiques de révision SRS restent intacts.
        - Génère un avertissement non-bloquant en cas de divergence du nombre de gabarits.
        """
        if not note_ids:
            return {
                "status": "applied",
                "migrated_count": 0,
                "note_ids": [],
                "target_model_id": 0,
                "target_model_name": "",
                "warnings": [],
            }

        target_nt = cls.resolve_target_model(target_model)

        # Extraction des champs cibles
        target_fields: list[str] = ["Front", "Back"]
        if target_nt.fields_schema:
            try:
                loaded_fields = json.loads(str(target_nt.fields_schema))
                if isinstance(loaded_fields, list) and loaded_fields:
                    target_fields = [str(f) for f in loaded_fields]
            except Exception:
                target_fields = ["Front", "Back"]

        # Extraction du nombre de gabarits cibles
        target_tmpl_count = 0
        if target_nt.templates:
            try:
                loaded_tmpls = json.loads(str(target_nt.templates))
                if isinstance(loaded_tmpls, list):
                    target_tmpl_count = len(loaded_tmpls)
            except Exception:
                target_tmpl_count = 0

        # Vérification préalable de l'existence de toutes les notes
        notes_to_migrate: list[NoteModel] = []
        warnings: list[str] = []
        warned_sources: set[int] = set()

        for nid in note_ids:
            note = NoteModel.get_or_none(NoteModel.id == nid)
            if not note:
                raise ValueError(f"Note #{nid} introuvable en base de données.")
            notes_to_migrate.append(note)

            # Vérification du nombre de gabarits du modèle source
            src_nt = note.note_type
            if src_nt and src_nt.id not in warned_sources:
                warned_sources.add(src_nt.id)
                src_tmpl_count = 0
                if src_nt.templates:
                    try:
                        s_tmpls = json.loads(str(src_nt.templates))
                        if isinstance(s_tmpls, list):
                            src_tmpl_count = len(s_tmpls)
                    except Exception:
                        src_tmpl_count = 0

                if src_tmpl_count != target_tmpl_count:
                    warnings.append(f"Le modèle source '{src_nt.name}' possède {src_tmpl_count} gabarit(s) alors que le modèle cible '{target_nt.name}' en possède {target_tmpl_count}.")

        # Exécution atomique
        with db.atomic():
            for note in notes_to_migrate:
                # Récupération du contenu actif actuel
                active_v = note.versions.where(NoteVersionModel.is_active == True).first()  # noqa: E712
                current_data: dict[str, Any] = {}
                if active_v and active_v.content:
                    try:
                        parsed = json.loads(active_v.content)
                        if isinstance(parsed, dict):
                            current_data = parsed
                    except Exception:
                        current_data = {"Front": active_v.content}

                mapped_data = cls.remap_fields(current_data, target_fields, mapping_champs=mapping_champs)

                # Mise à jour du type de note et création d'une nouvelle version
                note.note_type = target_nt
                note.save()
                note.add_version(mapped_data, source="note_type_change")

        logger.info(
            "Migration de %d note(s) vers le type de note '%s' effectuée avec succès.",
            len(notes_to_migrate),
            target_nt.name,
        )

        return {
            "status": "applied",
            "migrated_count": len(notes_to_migrate),
            "note_ids": [n.id for n in notes_to_migrate],
            "target_model_id": target_nt.id,
            "target_model_name": target_nt.name,
            "warnings": warnings,
        }

    @classmethod
    def audit_conformity(
        cls,
        note_type_name: str,
        regles: str = "",
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        """
        Audite la conformité structurelle des notes rattachées à un type de note.

        Règles supportées (vocabulaire fermé) :
        - empty_fields : Champs obligatoires vides ou note totalement vide.
        - inline_html : HTML inline ou styles en ligne présents dans les champs.
        - sound_outside_audio : Balises [sound:...] dans des champs non dédiés à l'audio.
        - field_duplicates : Champs distincts de la même note ayant un contenu identique.
        - template_field_mismatch : Discordance entre les champs déclarés et les champs utilisés dans les gabarits.
        """
        all_rules = {"empty_fields", "inline_html", "sound_outside_audio", "field_duplicates", "template_field_mismatch"}

        if regles:
            selected_rules = {r.strip() for r in regles.split(",") if r.strip()}
            active_rules = [r for r in selected_rules if r in all_rules]
        else:
            active_rules = list(all_rules)

        target_nt = cls.resolve_target_model(note_type_name)

        # Extraction des champs du modèle
        declared_fields: list[str] = ["Front", "Back"]
        if target_nt.fields_schema:
            try:
                loaded = json.loads(str(target_nt.fields_schema))
                if isinstance(loaded, list) and loaded:
                    declared_fields = [str(f) for f in loaded]
            except Exception:
                declared_fields = ["Front", "Back"]

        # Extraction des gabarits
        templates: list[dict[str, Any]] = []
        if target_nt.templates:
            try:
                t_loaded = json.loads(str(target_nt.templates))
                if isinstance(t_loaded, list):
                    templates = [t for t in t_loaded if isinstance(t, dict)]
            except Exception:
                templates = []

        # Analyse des discordances de gabarits (template_field_mismatch au niveau du modèle)
        model_template_mismatches: list[str] = []
        if "template_field_mismatch" in active_rules:
            declared_lower = {f.lower() for f in declared_fields}
            used_fields_lower: set[str] = set()

            for t in templates:
                t_name = str(t.get("name", "Gabarit"))
                for fmt_label, fmt in [("recto", t.get("qfmt", "")), ("verso", t.get("afmt", ""))]:
                    for match in re.findall(r"\{\{([^{}]+)\}\}", str(fmt)):
                        tag = match.strip()
                        tag = re.sub(r"^[#^/]", "", tag).strip()
                        if ":" in tag:
                            tag = tag.split(":")[-1].strip()
                        tag_lower = tag.lower()
                        if tag_lower in cls.ANKI_BUILTIN_TAGS:
                            continue
                        used_fields_lower.add(tag_lower)
                        if tag_lower not in declared_lower:
                            model_template_mismatches.append(f"Gabarit '{t_name}' ({fmt_label}) référence un champ non déclaré : '{{{{{match}}}}}'")

            for f in declared_fields:
                if f.lower() not in used_fields_lower:
                    model_template_mismatches.append(f"Champ déclaré '{f}' inutilisé dans les gabarits")

        # Sélection paginée des notes
        query = NoteModel.select().where(NoteModel.note_type == target_nt).order_by(NoteModel.id.asc())
        total_notes = query.count()
        eff_limit = max(1, min(limit, 100))
        eff_offset = max(0, offset)
        notes = list(query.offset(eff_offset).limit(eff_limit))

        violations_by_note: list[dict[str, Any]] = []
        rule_counts: dict[str, int] = {r: 0 for r in active_rules}

        audio_field_names = {"audio", "son", "pronunciation", "prononciation", "listening", "ecoute"}

        for note in notes:
            active_v = note.versions.where(NoteVersionModel.is_active == True).first()  # noqa: E712
            current_content: dict[str, Any] = {}
            if active_v and active_v.content:
                try:
                    loaded_content = json.loads(active_v.content)
                    if isinstance(loaded_content, dict):
                        current_content = loaded_content
                except Exception:
                    current_content = {"Front": active_v.content}

            note_violations: list[dict[str, str]] = []

            # 1. empty_fields
            if "empty_fields" in active_rules:
                for f in declared_fields:
                    val = str(current_content.get(f, "")).strip()
                    if not val:
                        note_violations.append(
                            {
                                "rule": "empty_fields",
                                "field": f,
                                "message": f"Le champ '{f}' est vide.",
                            }
                        )
                        rule_counts["empty_fields"] += 1

            # 2. inline_html
            if "inline_html" in active_rules:
                for f, val in current_content.items():
                    val_str = str(val)
                    if re.search(r"<(span|div|font|p)\b[^>]*style\s*=|style\s*=|font\s+color", val_str, re.IGNORECASE):
                        note_violations.append(
                            {
                                "rule": "inline_html",
                                "field": str(f),
                                "message": f"Style HTML inline détecté dans le champ '{f}'.",
                            }
                        )
                        rule_counts["inline_html"] += 1

            # 3. sound_outside_audio
            if "sound_outside_audio" in active_rules:
                for f, val in current_content.items():
                    f_str = str(f).lower()
                    if f_str not in audio_field_names and re.search(r"\[sound:[^\]]+\]", str(val), re.IGNORECASE):
                        note_violations.append(
                            {
                                "rule": "sound_outside_audio",
                                "field": str(f),
                                "message": f"Balise [sound:] présente dans le champ non-audio '{f}'.",
                            }
                        )
                        rule_counts["sound_outside_audio"] += 1

            # 4. field_duplicates
            if "field_duplicates" in active_rules:
                items = [(k, str(v).strip()) for k, v in current_content.items() if str(v).strip()]
                for i in range(len(items)):
                    for j in range(i + 1, len(items)):
                        k1, v1 = items[i]
                        k2, v2 = items[j]
                        if v1 == v2:
                            note_violations.append(
                                {
                                    "rule": "field_duplicates",
                                    "field": f"{k1},{k2}",
                                    "message": f"Contenu strictement identique entre les champs '{k1}' et '{k2}'.",
                                }
                            )
                            rule_counts["field_duplicates"] += 1

            # 5. template_field_mismatch rattaché au modèle
            if "template_field_mismatch" in active_rules and model_template_mismatches:
                for mm in model_template_mismatches:
                    note_violations.append(
                        {
                            "rule": "template_field_mismatch",
                            "field": "templates",
                            "message": mm,
                        }
                    )
                    rule_counts["template_field_mismatch"] += 1

            if note_violations:
                violations_by_note.append(
                    {
                        "note_id": note.id,
                        "violations": note_violations,
                    }
                )

        return {
            "note_type_name": target_nt.name,
            "total_notes": total_notes,
            "limit": eff_limit,
            "offset": eff_offset,
            "rules_evaluated": active_rules,
            "summary": {
                "total_violations": sum(len(n["violations"]) for n in violations_by_note),
                "notes_with_violations_count": len(violations_by_note),
                "by_rule": rule_counts,
            },
            "violations_by_note": violations_by_note,
        }

    @classmethod
    def preview_card_render(
        cls,
        note_id: int,
        fields_json: str = "",
        template_index: int | None = None,
        is_dark_mode: bool = False,
    ) -> dict[str, Any]:
        """
        Rend le recto, le verso et le CSS d'une note réelle en simulant le rendu Anki officiel.
        Supporte les surcharges optionnelles de champs et de gabarit.
        """
        from ankiforge.utils.anki_renderer import render_anki_card

        note = NoteModel.get_or_none(NoteModel.id == note_id)
        if not note:
            raise ValueError(f"Note #{note_id} introuvable en base de données.")

        nt = note.note_type
        if not nt:
            raise ValueError(f"Type de note manquant pour la note #{note_id}.")

        # Récupération du contenu actif
        active_v = note.versions.where(NoteVersionModel.is_active == True).first()  # noqa: E712
        fields_data: dict[str, Any] = {}
        if active_v and active_v.content:
            try:
                loaded = json.loads(active_v.content)
                if isinstance(loaded, dict):
                    fields_data = loaded
            except Exception:
                fields_data = {"Front": active_v.content}

        # Application des surcharges si fournies
        if fields_json:
            try:
                overrides = json.loads(fields_json) if isinstance(fields_json, str) else fields_json
                if isinstance(overrides, dict):
                    fields_data.update(overrides)
            except Exception as e:
                logger.warning("Échec du parsing de fields_json dans preview_card_render : %s", e)

        # Extraction des gabarits
        templates: list[dict[str, Any]] = []
        if nt.templates:
            try:
                t_loaded = json.loads(str(nt.templates))
                if isinstance(t_loaded, list) and t_loaded:
                    templates = [t for t in t_loaded if isinstance(t, dict)]
            except Exception:
                templates = []

        if not templates:
            templates = [{"name": "Carte 1", "qfmt": "{{Front}}", "afmt": "{{FrontSide}}<hr id='answer'>{{Back}}"}]

        idx = 0 if template_index is None else max(0, min(template_index, len(templates) - 1))
        tmpl = templates[idx]
        qfmt = str(tmpl.get("qfmt", "{{Front}}"))
        afmt = str(tmpl.get("afmt", "{{FrontSide}}<hr id='answer'>{{Back}}"))
        tmpl_name = str(tmpl.get("name", f"Carte {idx + 1}"))
        css_style = nt.css_style or ""

        # Rendu Recto
        front_html = render_anki_card(
            raw_html=qfmt,
            css=css_style,
            fields_dict=fields_data,
            is_recto=True,
            is_dark_mode=is_dark_mode,
            template_index=idx,
        )

        # Rendu Verso (avec transmission de front_html pour {{FrontSide}})
        back_html = render_anki_card(
            raw_html=afmt,
            css=css_style,
            fields_dict=fields_data,
            is_recto=False,
            front_html=front_html,
            is_dark_mode=is_dark_mode,
            template_index=idx,
        )

        return {
            "note_id": note.id,
            "note_type": nt.name,
            "template_index": idx,
            "template_name": tmpl_name,
            "front_html": front_html,
            "back_html": back_html,
            "css": css_style,
            "is_dark_mode": is_dark_mode,
        }
