"""
Service métier de Masquage d'Images Intelligent (Image Occlusion IA).
Gère la détection multimodale des légendes via Vision LLM, la génération des masques SVG
(modes Hide All / Hide One avec support de l'éradication des fuites contextuelles)
et la création des cartes au standard 'Image Occlusion Enhanced'.
"""

from __future__ import annotations

import base64
import json
import logging
import mimetypes
import re
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from PIL import Image

from ankiforge.database.base import db
from ankiforge.database.models import CardModel, DeckModel, NoteModel, NoteTypeModel
from ankiforge.services.ai.base import LLMProvider, MockProvider
from ankiforge.services.ai.flexible_service import AIManager
from ankiforge.services.cards.media_manager import MediaManager

logger = logging.getLogger(__name__)

IOE_MODEL_NAME = "Image Occlusion Enhanced"
IOE_FIELDS = [
    "id",
    "Header",
    "Image",
    "Question Mask",
    "Answer Mask",
    "Original Mask",
    "Footer",
    "Remarks",
    "Sources",
    "Extra 1",
    "Extra 2",
]


@dataclass
class OcclusionBox:
    """Représente un masque rectangulaire d'occlusion sur une image."""

    id: int
    x: float  # Coordonnée X en pixels réels de l'image
    y: float  # Coordonnée Y en pixels réels de l'image
    width: float  # Largeur en pixels
    height: float  # Hauteur en pixels
    text: str = ""  # Texte ou label masqué
    hint: str = ""  # Indice optionnel

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OcclusionBox:
        return cls(
            id=int(data.get("id", 1)),
            x=float(data.get("x", 0.0)),
            y=float(data.get("y", 0.0)),
            width=float(data.get("width", 50.0)),
            height=float(data.get("height", 30.0)),
            text=str(data.get("text", "")),
            hint=str(data.get("hint", "")),
        )


class ImageOcclusionService:
    """Service gérant l'inférence vision, la génération de masques SVG et la persistance des notes IOE."""

    def __init__(self, media_manager: MediaManager | None = None) -> None:
        self.media_manager = media_manager or MediaManager()

    @classmethod
    def ensure_ioe_model_exists(cls) -> NoteTypeModel:
        """Garantit l'existence du modèle de note standard 'Image Occlusion Enhanced'."""
        existing = NoteTypeModel.select().where(NoteTypeModel.name == IOE_MODEL_NAME).first()
        if existing:
            return existing

        templates = [
            {
                "name": "Image Occlusion",
                "qfmt": (
                    "{{#Header}}<div style='font-weight: bold; margin-bottom: 8px;'>{{Header}}</div>{{/Header}}\n"
                    "<div id='image-wrapper'>\n"
                    "    {{Image}}\n"
                    "    {{Question Mask}}\n"
                    "</div>\n"
                    "{{#Footer}}<div style='margin-top: 8px; font-size: 0.9em; opacity: 0.8;'>{{Footer}}</div>{{/Footer}}"
                ),
                "afmt": (
                    "{{#Header}}<div style='font-weight: bold; margin-bottom: 8px;'>{{Header}}</div>{{/Header}}\n"
                    "<div id='image-wrapper'>\n"
                    "    {{Image}}\n"
                    "    {{Answer Mask}}\n"
                    "</div>\n"
                    "{{#Footer}}<div style='margin-top: 8px; font-size: 0.9em; opacity: 0.8;'>{{Footer}}</div>{{/Footer}}\n"
                    "{{#Remarks}}<hr id=answer><div style='text-align: left; margin-top: 8px;'>{{Remarks}}</div>{{/Remarks}}"
                ),
            }
        ]

        css_style = (
            ".card {\n"
            "  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;\n"
            "  font-size: 16px;\n"
            "  text-align: center;\n"
            "  color: palette(text);\n"
            "}\n"
            "#image-wrapper {\n"
            "  position: relative;\n"
            "  display: inline-block;\n"
            "  max-width: 100%;\n"
            "}\n"
            "#image-wrapper img {\n"
            "  max-width: 100%;\n"
            "  height: auto;\n"
            "}\n"
            "#image-wrapper img:first-child {\n"
            "  display: block;\n"
            "  position: static;\n"
            "}\n"
            "#image-wrapper img:not(:first-child) {\n"
            "  position: absolute;\n"
            "  top: 0;\n"
            "  left: 0;\n"
            "  width: 100%;\n"
            "  height: 100%;\n"
            "  pointer-events: none;\n"
            "}\n"
        )

        model = NoteTypeModel.create(
            name=IOE_MODEL_NAME,
            description="Masquage d'images (Image Occlusion). Découverte active sur schémas et planches.",
            fields_schema=json.dumps(IOE_FIELDS, ensure_ascii=False),
            templates=json.dumps(templates, ensure_ascii=False),
            css_style=css_style,
        )
        logger.info("Modèle de note '%s' créé avec succès en base de données.", IOE_MODEL_NAME)
        return model

    def detect_labels_with_vision(
        self,
        image_path: str | Path,
        provider: LLMProvider | None = None,
        provider_name: str | None = None,
        model_id: str | None = None,
    ) -> list[OcclusionBox]:
        """
        Détecte les légendes et coordonnées (bounding boxes) sur une image via un modèle de vision.
        Gère la normalisation 0-1000 et le re-calibrage sur les dimensions réelles de l'image.
        """
        path_obj = Path(image_path)
        if not path_obj.exists():
            raise FileNotFoundError(f"L'image source '{image_path}' est introuvable.")

        with Image.open(path_obj) as img:
            img_w, img_h = img.size

        # Résolution du provider si non fourni
        active_provider = provider
        if active_provider is None:
            if provider_name and model_id:
                active_provider = AIManager.create_provider(provider_name, model_id)
            else:
                ai_manager = AIManager()
                active_provider = ai_manager.provider

        if isinstance(active_provider, MockProvider):
            logger.info("MockProvider détecté : génération de masques de test déterministes.")
            return self._get_mock_boxes(img_w, img_h)

        # Encodage de l'image en base64 pour requête multimodale
        image_bytes = path_obj.read_bytes()
        b64_data = base64.b64encode(image_bytes).decode("ascii")
        mime_type, _ = mimetypes.guess_type(str(path_obj))
        mime_type = mime_type or "image/png"

        system_prompt = (
            "Tu es un expert en vision par ordinateur et en conception de flashcards d'apprentissage (Image Occlusion).\n"
            "Analyse ce schéma / diagramme / planche anatomique.\n"
            "Détecte toutes les étiquettes textuelles, légendes, noms de composants ou annotations clés.\n"
            "Pour chaque légende détectée, fournis son rectangle englobant (bounding box).\n"
            "Les coordonnées DOIVENT être des entiers normalisés entre 0 et 1000 : [ymin, xmin, ymax, xmax].\n"
            "- ymin : bord supérieur (0 = haut, 1000 = bas)\n"
            "- xmin : bord gauche (0 = gauche, 1000 = droite)\n"
            "- ymax : bord inférieur\n"
            "- xmax : bord droit\n"
            "Fournis également le texte ('text') lisible de la légende.\n\n"
            "Réponds STRICTEMENT sous ce format JSON :\n"
            "{\n"
            '  "labels": [\n'
            '    {"id": 1, "text": "Intitulé", "box_2d": [ymin, xmin, ymax, xmax]}\n'
            "  ]\n"
            "}"
        )

        user_content: list[dict[str, Any]] = [
            {
                "type": "text",
                "text": "Détecte toutes les annotations et légendes textuelles sur cette image pour créer des masques d'occlusion.",
            },
            {
                "type": "image_url",
                "image_url": {"url": f"data:{mime_type};base64,{b64_data}"},
            },
        ]

        try:
            raw_response = active_provider.generate(
                system_prompt=system_prompt,
                user_prompt=user_content,
                response_format="json",
            )
            return self._parse_vision_json(raw_response, img_w, img_h)
        except Exception as err:
            logger.error("Échec de la détection de vision sur %s : %s", path_obj.name, err)
            raise RuntimeError(f"Erreur d'analyse visuelle par l'IA : {err}") from err

    @staticmethod
    def _parse_vision_json(json_str: str, img_w: int, img_h: int) -> list[OcclusionBox]:
        """Parse et valide le JSON renvoyé par le modèle de vision en pixels réels."""
        # Nettoyage des balises markdown potentielles ```json ... ```
        cleaned = re.sub(r"^```json\s*", "", json_str.strip(), flags=re.MULTILINE)
        cleaned = re.sub(r"\s*```$", "", cleaned.strip(), flags=re.MULTILINE)

        data = json.loads(cleaned)
        labels = data.get("labels", []) if isinstance(data, dict) else []

        boxes: list[OcclusionBox] = []
        for idx, item in enumerate(labels, start=1):
            if not isinstance(item, dict):
                continue

            text = str(item.get("text", "")).strip()
            box_2d = item.get("box_2d")

            if not isinstance(box_2d, list) or len(box_2d) < 4:
                continue

            # Format [ymin, xmin, ymax, xmax] normalisé 0-1000
            ymin, xmin, ymax, xmax = (float(v) for v in box_2d[:4])

            # Conversion en pixels réels
            px_x = (xmin / 1000.0) * img_w
            px_y = (ymin / 1000.0) * img_h
            px_w = ((xmax - xmin) / 1000.0) * img_w
            px_h = ((ymax - ymin) / 1000.0) * img_h

            # Garde-fous et clamping
            px_x = max(0.0, min(float(img_w), px_x))
            px_y = max(0.0, min(float(img_h), px_y))
            px_w = max(4.0, min(float(img_w - px_x), px_w))
            px_h = max(4.0, min(float(img_h - px_y), px_h))

            boxes.append(
                OcclusionBox(
                    id=idx,
                    x=round(px_x, 1),
                    y=round(px_y, 1),
                    width=round(px_w, 1),
                    height=round(px_h, 1),
                    text=text,
                    hint="",
                )
            )

        # Tri top-to-bottom puis left-to-right pour un ordre d'étude naturel
        boxes.sort(key=lambda b: (b.y, b.x))
        for i, box in enumerate(boxes, start=1):
            box.id = i

        return boxes

    @staticmethod
    def _get_mock_boxes(img_w: int, img_h: int) -> list[OcclusionBox]:
        """Retourne 3 masques de démonstration pour les tests unitaires et le mode déconnecté."""
        return [
            OcclusionBox(
                id=1,
                x=round(img_w * 0.15, 1),
                y=round(img_h * 0.2, 1),
                width=round(img_w * 0.25, 1),
                height=round(img_h * 0.08, 1),
                text="Légende 1",
            ),
            OcclusionBox(
                id=2,
                x=round(img_w * 0.6, 1),
                y=round(img_h * 0.45, 1),
                width=round(img_w * 0.28, 1),
                height=round(img_h * 0.08, 1),
                text="Légende 2",
            ),
            OcclusionBox(
                id=3,
                x=round(img_w * 0.2, 1),
                y=round(img_h * 0.75, 1),
                width=round(img_w * 0.3, 1),
                height=round(img_h * 0.08, 1),
                text="Légende 3",
            ),
        ]

    def generate_svg_mask(
        self,
        boxes: list[OcclusionBox],
        image_width: int,
        image_height: int,
        active_box_id: int | None = None,
        mode: str = "hide_all",  # "hide_all" ou "hide_one"
        is_answer: bool = False,
        keep_other_masks_on_answer: bool = True,
    ) -> str:
        """
        Génère la chaîne XML SVG pour le masque de Question ou de Réponse.

        Styles visuels :
        - Masque actif en Question : rectangle rouge (#e11d48) avec badge numéroté.
        - Masque actif en Réponse : contour vert pointillé (#10b981, dashed) sans remplissage (révélé).
        - Masques inactifs :
          * Si 'hide_all' et (Question ou keep_other_masks_on_answer) : rectangle ambré/jaune (#f59e0b).
          * Si 'hide_one' ou pas de persistance : transparent (non dessiné).
        """
        svg_parts = [
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {image_width} {image_height}" width="100%" height="100%">',
            "  <defs>",
            "    <style>",
            "      .mask-active-q { fill: #e11d48; stroke: #be123c; stroke-width: 2; rx: 4px; ry: 4px; }",
            "      .mask-inactive { fill: #f59e0b; stroke: #d97706; stroke-width: 2; rx: 4px; ry: 4px; }",
            "      .mask-active-a { fill: none; stroke: #10b981; stroke-width: 2.5; stroke-dasharray: 4,4; rx: 4px; ry: 4px; }",
            "      .mask-badge { font-family: Arial; font-size: 11px; font-weight: bold; fill: #fff; text-anchor: middle; dominant-baseline: middle; }",
            "    </style>",
            "  </defs>",
        ]

        for box in boxes:
            is_active = active_box_id is not None and box.id == active_box_id
            center_x = box.x + (box.width / 2.0)
            center_y = box.y + (box.height / 2.0)

            if is_active:
                if not is_answer:
                    # Masque question actif
                    svg_parts.append(
                        f'  <g id="box_{box.id}">\n'
                        f'    <rect class="mask-active-q" x="{box.x}" y="{box.y}" width="{box.width}" height="{box.height}" />\n'
                        f'    <text class="mask-badge" x="{center_x}" y="{center_y}">[{box.id}]</text>\n'
                        f"  </g>"
                    )
                else:
                    # Masque réponse actif (révélé avec délimitation verte pointillée)
                    svg_parts.append(f'  <g id="box_{box.id}">\n    <rect class="mask-active-a" x="{box.x}" y="{box.y}" width="{box.width}" height="{box.height}" />\n  </g>')
            else:
                # Masque inactif
                should_draw_inactive = False
                if active_box_id is None:
                    # Masque original (tous les rectangles affichés)
                    should_draw_inactive = True
                elif mode == "hide_all" and (not is_answer or keep_other_masks_on_answer):
                    should_draw_inactive = True

                if should_draw_inactive:
                    svg_parts.append(
                        f'  <g id="box_{box.id}">\n'
                        f'    <rect class="mask-inactive" x="{box.x}" y="{box.y}" width="{box.width}" height="{box.height}" />\n'
                        f'    <text class="mask-badge" x="{center_x}" y="{center_y}">[{box.id}]</text>\n'
                        f"  </g>"
                    )

        svg_parts.append("</svg>")
        return "\n".join(svg_parts)

    def create_occlusion_notes(
        self,
        image_path: str | Path,
        boxes: list[OcclusionBox],
        deck_id: int,
        header: str = "",
        mode: str = "hide_all",
        keep_other_masks_on_answer: bool = True,
        tags: list[str] | None = None,
    ) -> list[NoteModel]:
        """
        Crée l'ensemble des notes et cartes d'occlusion au standard Image Occlusion Enhanced.
        Sauvegarde l'image de base et les masques SVG vectoriels dans media_dir.
        """
        if not boxes:
            raise ValueError("Au moins un rectangle d'occlusion est requis.")

        deck = DeckModel.get_or_none(DeckModel.id == deck_id)
        if not deck:
            raise ValueError(f"Le paquet Anki ID={deck_id} est introuvable.")

        note_type = self.ensure_ioe_model_exists()

        path_obj = Path(image_path)
        with Image.open(path_obj) as img:
            img_w, img_h = img.size

        # Archivage de l'image de base dans le dossier média
        base_media = self.media_manager.store_document_source(str(path_obj))
        if not base_media:
            raise RuntimeError(f"Impossible d'archiver l'image source '{path_obj.name}' dans les médias.")
        base_img_filename = base_media.filename

        # Préfixe stable pour le groupe d'occlusions
        group_id = f"occl_{int(time.time())}_{uuid.uuid4().hex[:6]}"

        # Sauvegarde du masque original global (Original Mask)
        orig_svg = self.generate_svg_mask(boxes, img_w, img_h, active_box_id=None, mode=mode)
        orig_filename = f"{group_id}_o.svg"
        self.media_manager.store_media_bytes(orig_svg.encode("utf-8"), orig_filename, mime_type="image/svg+xml")

        final_tags = list(tags) if tags else ["image-occlusion"]
        created_notes: list[NoteModel] = []

        with db.atomic():
            for box in boxes:
                # 1. Masque Question
                q_svg = self.generate_svg_mask(
                    boxes,
                    img_w,
                    img_h,
                    active_box_id=box.id,
                    mode=mode,
                    is_answer=False,
                    keep_other_masks_on_answer=keep_other_masks_on_answer,
                )
                q_filename = f"{group_id}_q_{box.id}.svg"
                self.media_manager.store_media_bytes(q_svg.encode("utf-8"), q_filename, mime_type="image/svg+xml")

                # 2. Masque Réponse
                a_svg = self.generate_svg_mask(
                    boxes,
                    img_w,
                    img_h,
                    active_box_id=box.id,
                    mode=mode,
                    is_answer=True,
                    keep_other_masks_on_answer=keep_other_masks_on_answer,
                )
                a_filename = f"{group_id}_a_{box.id}.svg"
                self.media_manager.store_media_bytes(a_svg.encode("utf-8"), a_filename, mime_type="image/svg+xml")

                # 3. Création de la Note
                note = NoteModel.create(
                    note_type=note_type,
                    tags=json.dumps(final_tags, ensure_ascii=False),
                    status="new",
                )

                content_dict = {
                    "id": f"{group_id}_{box.id}",
                    "Header": header,
                    "Image": f'<img src="{base_img_filename}">',
                    "Question Mask": f'<img src="{q_filename}">',
                    "Answer Mask": f'<img src="{a_filename}">',
                    "Original Mask": f'<img src="{orig_filename}">',
                    "Footer": "",
                    "Remarks": box.text or "",
                    "Sources": path_obj.name,
                    "Extra 1": box.hint or "",
                    "Extra 2": f"Mode: {mode}",
                }

                note.add_version(content_dict, source="image_occlusion")

                # 4. Création de la Carte physique Anki
                CardModel.create(
                    note=note,
                    deck=deck,
                    template_index=0,
                )

                created_notes.append(note)

        logger.info(
            "Création de %d notes Image Occlusion réussie pour l'image '%s' dans le paquet '%s'.",
            len(created_notes),
            path_obj.name,
            deck.name,
        )
        return created_notes
