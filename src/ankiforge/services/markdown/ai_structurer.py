"""Service de structuration documentaire et optimisation des retranscriptions par IA."""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

from ankiforge.services.ai.base import LLMProvider, MockProvider
from ankiforge.services.ai.flexible_service import AIManager
from ankiforge.services.markdown.formatter import MarkdownFormatter
from ankiforge.services.markdown.models import FormatOptions

logger = logging.getLogger(__name__)


class StructuringProfile(StrEnum):
    """Profils de restructuration documentaire selon l'objectif d'apprentissage."""

    DIDACTIC = "didactic"  # Synthèse de cours, définitions, KaTeX, points clés
    POLISHED_VERBATIM = "polished_verbatim"  # Nettoyage oral, ponctuation, chapitrage temporel
    EXECUTIVE_SUMMARY = "executive_summary"  # Fiche synthétique, tableaux, points clés


@dataclass(frozen=True)
class StructuringOptions:
    """Options de configuration pour la restructuration d'un document par IA."""

    profile: StructuringProfile = StructuringProfile.DIDACTIC
    preserve_timestamps: bool = True
    normalize_katex: bool = True
    include_executive_summary: bool = True
    include_key_takeaways: bool = True
    language: str = "fr"
    max_chunk_words: int = 1500


class AIDocumentStructurer:
    """Moteur de transformation de textes bruts et retranscriptions en documents AI-Ready.

    Caractéristiques :
    - Élimination des tics de langage, hésitations et répétitions orales.
    - Chapitrage hiérarchique H2 / H3 avec préservation des repères temporels [MM:SS].
    - Encadrement des définitions et mise en valeur du vocabulaire clé en gras.
    - Formalisation mathématique et scientifique en KaTeX ($..$ / $$..$$).
    - Support Single-Pass pour textes courts et Map-Reduce pour très longues conférences.
    """

    @classmethod
    def build_system_prompt(cls, options: StructuringOptions) -> str:
        """Construit un prompt système adapté au profil de structuration sélectionné."""
        base_prompt = (
            "Tu es un expert en pédagogie cognitive, ingénierie de la connaissance et sciences de l'apprentissage.\n"
            "Ta mission est de transformer une retranscription orale ou un texte brut non structuré en un document "
            "Markdown de référence, hautement organisé, d'une clarté exemplaire et optimisé pour la révision espacée (SRS / Anki).\n\n"
            "DIRECTIVES DE FORME ET DE SYNTAXE (OBLIGATOIRES) :\n"
            "1. Sortie en pur Markdown GitHub / CommonMark uniquement. Pas de préambule ni d'explication méta.\n"
            "2. Titres hiérarchiques stricts : # Titre Principal, ## Chapitre, ### Sous-section. Aucun saut de niveau illégal (jamais de H1 -> H3).\n"
            "3. Règle absolue KaTeX : Toute formule mathématique ou symbole scientifique DOIT utiliser le délimiteur dollar : "
            "$...$ pour les formules inline et $$\\n...\\n$$ pour les blocs display. Ne JAMAIS utiliser \\( \\) ni \\[ \\].\n"
            "4. Richesse terminologique : Mettre en GRAS (**terme**) les concepts, dates, formules et vocabulaire clé pour "
            "faciliter la création ultérieure de cartes mémoires (Q/R ou Cloze deletion).\n"
        )

        if options.preserve_timestamps:
            base_prompt += (
                "5. Horodatage : Conserve rigoureusement les repères temporels présents (ex: [02:15] ou <!-- TIME: ... -->) "
                "au début des chapitres et sections pour permettre la navigation vidéo/audio.\n"
            )

        if options.profile == StructuringProfile.DIDACTIC:
            base_prompt += (
                "\nPROFIL : SYNTHÈSE DIDACTIQUE & PÉDAGOGIQUE (COURS D'ÉTUDE)\n"
                "- Structure le document avec :\n"
                "  • Un titre H1 explicite et descriptif.\n"
                "  • Un chapeau introductif (Sujet, public cible, résumé exécutif en 3-4 phrases).\n"
                "  • Des chapitres thématiques (H2) progressifs, découpés en sous-parties (H3).\n"
                "  • Les définitions fondamentales encadrées en blockquotes : `> **Définition :** ...`\n"
                "  • Des listes à puces ou tableaux comparatifs pour les classifications et étapes logiques.\n"
                "  • En fin de document, une section obligatoire `## 📌 Points Clés à Retenir` récapitulant les 5 à 8 enseignements vitaux.\n"
                "- Élimine tous les tics oraux (*euh*, *en fait*, répétitions, digressions inutiles) sans omettre aucune information technique de fond.\n"
            )
        elif options.profile == StructuringProfile.POLISHED_VERBATIM:
            base_prompt += (
                "\nPROFIL : RETRANSCRIPTION POLIE & CHAPITRÉE (VERBATIM STRUCTURÉ)\n"
                "- Conserve la totalité du propos de l'orateur et la fidélité mot-à-mot du contenu.\n"
                "- Nettoie uniquement la forme : rétablis une ponctuation irréprochable, découpe en paragraphes aérés.\n"
                "- Supprime les scories orales évidentes (*euh*, bafouillages, faux départs de phrases).\n"
                "- Ajoute des titres H2 et H3 avec horodatage [MM:SS] pour découper la lecture sans altérer le texte source.\n"
            )
        elif options.profile == StructuringProfile.EXECUTIVE_SUMMARY:
            base_prompt += (
                "\nPROFIL : FICHE DE SYNTHÈSE & RÉSUMÉ EXÉCUTIF (CHEATSHEET)\n"
                "- Produis un document ultra-condensé, direct et sans verbiage.\n"
                "- Fiche d'identité synthétique, tableaux récapitulatifs, définitions concises et bullet points percutants.\n"
                "- Idéal pour une révision éclair avant un examen ou une réunion.\n"
            )

        return base_prompt

    @classmethod
    def structure_document(
        cls,
        content: str,
        options: StructuringOptions | None = None,
        ai_provider: LLMProvider | None = None,
        progress_callback: Callable[[str, float], None] | None = None,
    ) -> str:
        """Restructure un document ou une transcription en document pédagogique AI-Ready.

        Args:
            content: Texte brut ou retranscription horodatée.
            options: Options de profil et de mise en forme.
            ai_provider: Fournisseur d'IA (si None, utilise le provider actif d'AIManager).
            progress_callback: Callback optionnel pour remonter l'avancement (message, ratio 0.0-1.0).

        Returns:
            Contenu Markdown structuré et formaté.
        """
        if not content or not content.strip():
            return ""

        opts = options or StructuringOptions()
        provider = ai_provider or cls._resolve_provider()

        total_words = len(content.split())
        logger.info(
            "Démarrage de la structuration IA (%d mots, profil=%s, provider=%s)",
            total_words,
            opts.profile.value,
            type(provider).__name__,
        )

        if progress_callback:
            progress_callback("Analyse de la structure et préparation du document...", 0.1)

        system_prompt = cls.build_system_prompt(opts)

        # Si le document est de taille modérée (< 3500 mots), traitement direct Single-Pass
        if total_words <= opts.max_chunk_words * 2 or isinstance(provider, MockProvider):
            raw_result = cls._structure_single_pass(content, system_prompt, provider, progress_callback)
        else:
            # Document volumineux (longue conférence / cours de 1h+) -> Partitionnement Map-Reduce
            raw_result = cls._structure_map_reduce(content, opts, system_prompt, provider, progress_callback)

        # Post-traitement déterministe avec MarkdownFormatter
        if progress_callback:
            progress_callback("Normalisation des formules et alignement des tableaux...", 0.95)

        fmt_options = FormatOptions(
            dehyphenate_ocr=True,
            normalize_katex=opts.normalize_katex,
            align_tables=True,
            normalize_headings=True,
            clean_whitespace=True,
        )
        format_res = MarkdownFormatter.format(raw_result, fmt_options)
        final_text = format_res.formatted_text

        if progress_callback:
            progress_callback("Structuration achevée avec succès !", 1.0)

        logger.info("Structuration IA terminée avec succès (%d caractères générés)", len(final_text))
        return final_text

    @classmethod
    def _resolve_provider(cls) -> LLMProvider:
        """Résout le fournisseur d'IA configuré dans l'application."""
        try:
            ai_mgr = AIManager()
            return ai_mgr.provider
        except Exception as e:
            logger.warning("Impossible d'initialiser AIManager, repli sur MockProvider : %s", e)
            return MockProvider()

    @classmethod
    def _structure_single_pass(
        cls,
        content: str,
        system_prompt: str,
        provider: LLMProvider,
        progress_callback: Callable[[str, float], None] | None,
    ) -> str:
        """Exécute la structuration en une passe unique."""
        if progress_callback:
            progress_callback("Génération de la structure par l'IA...", 0.4)

        user_prompt = f"Voici le texte brut / la retranscription à structurer :\n\n{content}"
        response = provider.generate(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_format="text",
        )
        return response.strip()

    @classmethod
    def _structure_map_reduce(
        cls,
        content: str,
        options: StructuringOptions,
        system_prompt: str,
        provider: LLMProvider,
        progress_callback: Callable[[str, float], None] | None,
    ) -> str:
        """Traite les longs documents par tranches temporelles / thématiques (Map-Reduce)."""
        chunks = cls._split_into_logical_chunks(content, options.max_chunk_words)
        total_chunks = len(chunks)
        structured_parts: list[str] = []

        logger.info("Traitement Map-Reduce du document en %d segments", total_chunks)

        for idx, chunk in enumerate(chunks, 1):
            if progress_callback:
                ratio = 0.2 + (0.6 * (idx / total_chunks))
                progress_callback(f"Structuration du chapitre {idx}/{total_chunks}...", ratio)

            chunk_user_prompt = (
                f"Voici la partie {idx}/{total_chunks} d'une longue retranscription.\nRestructure cette partie en chapitres clairs avec titres H2/H3 et horodatages si présents.\n\n{chunk}"
            )
            part_res = provider.generate(
                system_prompt=system_prompt,
                user_prompt=chunk_user_prompt,
                response_format="text",
            )
            structured_parts.append(part_res.strip())

        combined_body = "\n\n".join(structured_parts)

        # Étape Reduce : Génération de l'en-tête de synthèse et des points clés globaux
        if progress_callback:
            progress_callback("Synthèse globale et finalisation des points clés...", 0.85)

        synthesis_prompt = (
            "À partir des chapitres structurés suivants, génère UNIQUEMENT le bloc d'introduction globale "
            "(Titre H1, fiche d'identité et résumé exécutif de 3-5 phrases) ainsi que le bloc final "
            "`## 📌 Points Clés à Retenir` (5-8 points majeurs).\n\n"
            f"{combined_body[:4000]}"
        )
        try:
            synthesis_res = provider.generate(
                system_prompt=system_prompt,
                user_prompt=synthesis_prompt,
                response_format="text",
            )
            return f"{synthesis_res.strip()}\n\n---\n\n{combined_body}"
        except Exception as e:
            logger.warning("Échec de la passe de synthèse globale Reduce : %s", e)
            return combined_body

    @classmethod
    def _split_into_logical_chunks(cls, content: str, target_words: int) -> list[str]:
        """Découpe un texte volumineux en tranches logiques respectant les pauses et marqueurs."""
        paragraphs = content.split("\n\n")
        chunks: list[str] = []
        current_paras: list[str] = []
        current_words = 0

        for p in paragraphs:
            p_strip = p.strip()
            if not p_strip:
                continue

            words = len(p_strip.split())
            if current_paras and (current_words + words > target_words):
                chunks.append("\n\n".join(current_paras))
                current_paras = [p_strip]
                current_words = words
            else:
                current_paras.append(p_strip)
                current_words += words

        if current_paras:
            chunks.append("\n\n".join(current_paras))

        return chunks or [content]
