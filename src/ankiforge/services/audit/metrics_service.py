"""
Service de calcul des métriques métier, de télémétrie et des diagnostics proactifs pour AnkiForge.
"""

from datetime import datetime, timedelta, time
import logging
from typing import Any, Dict, List, Optional
from peewee import fn

from ankiforge.database.models import (
    AuditRecordModel,
    CardModel,
    DeckModel,
    DocumentChunkModel,
    NoteChunkLinkModel,
    NoteModel,
    NoteVersionModel,
    TokenUsageModel,
)

logger = logging.getLogger(__name__)

DAY_NAMES_FR = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]


class MetricsService:
    """Calcul optimisé et asynchrone des métriques du Cockpit Global d'AnkiForge."""

    @classmethod
    def get_wozniak_health_score(cls) -> Dict[str, Any]:
        """Calcule le score de conformité aux 20 règles de Piotr Wozniak."""
        try:
            total_notes = NoteModel.select().count()
            if total_notes == 0:
                return {
                    "score": 100,
                    "compliant_count": 0,
                    "total_notes": 0,
                    "issues_count": 0,
                }

            # Nombre de cartes avec des enregistrements d'audit non conformes
            issues_count = (
                AuditRecordModel.select(fn.COUNT(fn.DISTINCT(AuditRecordModel.note)))
                .where(AuditRecordModel.is_compliant == False)  # noqa: E712
                .scalar()
                or 0
            )

            compliant_count = max(0, total_notes - issues_count)
            score = int(round((compliant_count / total_notes) * 100))
            return {
                "score": score,
                "compliant_count": compliant_count,
                "total_notes": total_notes,
                "issues_count": issues_count,
            }
        except Exception as e:
            logger.warning("Erreur lors du calcul du score Wozniak : %s", e)
            return {"score": 100, "compliant_count": 0, "total_notes": 0, "issues_count": 0}

    @classmethod
    def get_smart_coverage_rate(cls) -> Dict[str, Any]:
        """Calcule le taux de couverture documentaire RAG (Smart Coverage)."""
        try:
            total_chunks = DocumentChunkModel.select().count()
            if total_chunks == 0:
                return {
                    "coverage": 100,
                    "linked_chunks": 0,
                    "total_chunks": 0,
                    "unlinked_chunks": 0,
                }

            # Nombre de chunks ayant au moins une carte liée
            linked_chunks = DocumentChunkModel.select(fn.COUNT(fn.DISTINCT(DocumentChunkModel.id))).join(NoteChunkLinkModel, on=(NoteChunkLinkModel.chunk == DocumentChunkModel.id)).scalar() or 0

            unlinked_chunks = max(0, total_chunks - linked_chunks)
            coverage = int(round((linked_chunks / total_chunks) * 100))
            return {
                "coverage": coverage,
                "linked_chunks": linked_chunks,
                "total_chunks": total_chunks,
                "unlinked_chunks": unlinked_chunks,
            }
        except Exception as e:
            logger.warning("Erreur lors du calcul de couverture documentaire : %s", e)
            return {"coverage": 100, "linked_chunks": 0, "total_chunks": 0, "unlinked_chunks": 0}

    @classmethod
    def get_ai_telemetry(cls) -> Dict[str, Any]:
        """Extrait la télémétrie des jetons et dépenses IA."""
        try:
            cost_query = TokenUsageModel.select(fn.SUM(TokenUsageModel.estimated_cost_usd)).scalar()
            tokens_query = TokenUsageModel.select(fn.SUM(TokenUsageModel.total_tokens)).scalar()
            calls_count = TokenUsageModel.select().count()

            total_cost = float(cost_query or 0.0)
            total_tokens = int(tokens_query or 0)
            return {
                "total_cost_usd": total_cost,
                "total_tokens": total_tokens,
                "calls_count": calls_count,
            }
        except Exception as e:
            logger.warning("Erreur lors du calcul de la télémétrie IA : %s", e)
            return {"total_cost_usd": 0.0, "total_tokens": 0, "calls_count": 0}

    @classmethod
    def get_duplicate_anomalies_count(cls) -> int:
        """Compte le nombre d'anomalies de doublons nécessitant un arbitrage."""
        try:
            # Audit records étiquetés doublons / collisions ou interférences
            dup_count = (
                AuditRecordModel.select(fn.COUNT(AuditRecordModel.id))
                .where(
                    (AuditRecordModel.is_compliant == False)  # noqa: E712
                    & (
                        (AuditRecordModel.rule_broken.contains("doublon"))
                        | (AuditRecordModel.rule_broken.contains("similaire"))
                        | (AuditRecordModel.reason.contains("doublon"))
                        | (AuditRecordModel.reason.contains("similaire"))
                    )
                )
                .scalar()
                or 0
            )
            return int(dup_count)
        except Exception as e:
            logger.warning("Erreur lors du calcul des doublons : %s", e)
            return 0

    @classmethod
    def get_7_days_activity(cls) -> List[Dict[str, Any]]:
        """Agrège l'activité de création et de révision sur les 7 derniers jours."""
        activity: List[Dict[str, Any]] = []
        try:
            today = datetime.now().date()
            for i in range(6, -1, -1):
                d = today - timedelta(days=i)
                day_start = datetime.combine(d, time.min)
                day_end = datetime.combine(d, time.max)

                created_count = NoteVersionModel.select().where((NoteVersionModel.version_number == 1) & (NoteVersionModel.created_at >= day_start) & (NoteVersionModel.created_at <= day_end)).count()

                modified_count = NoteVersionModel.select().where((NoteVersionModel.version_number > 1) & (NoteVersionModel.created_at >= day_start) & (NoteVersionModel.created_at <= day_end)).count()

                day_abbr = DAY_NAMES_FR[d.weekday()]
                day_label = f"{day_abbr} {d.day}"

                activity.append(
                    {
                        "date": d.strftime("%Y-%m-%d"),
                        "label": day_label,
                        "created": created_count,
                        "modified": modified_count,
                        "total": created_count + modified_count,
                    }
                )
        except Exception as e:
            logger.warning("Erreur lors de l'agrégation de l'activité 7 jours : %s", e)
            # Fallback 7 jours vides
            today = datetime.now().date()
            for i in range(6, -1, -1):
                d = today - timedelta(days=i)
                day_abbr = DAY_NAMES_FR[d.weekday()]
                activity.append(
                    {
                        "date": d.strftime("%Y-%m-%d"),
                        "label": f"{day_abbr} {d.day}",
                        "created": 0,
                        "modified": 0,
                        "total": 0,
                    }
                )

        return activity

    @classmethod
    def get_proactive_diagnostics(cls) -> List[Dict[str, Any]]:
        """Génère la liste des diagnostics d'action proactifs avec routage 1-clic."""
        diagnostics: List[Dict[str, Any]] = []

        wozniak = cls.get_wozniak_health_score()
        if wozniak["issues_count"] > 0:
            diagnostics.append(
                {
                    "type": "wozniak",
                    "title": "Violations Wozniak Détectées",
                    "message": f"{wozniak['issues_count']} carte(s) présentent des violations de clarté ou d'atomicité.",
                    "severity": "warning",
                    "action_label": "⚡ Lancer l'audit Wozniak",
                    "target_view": "analysis",
                    "target_tab": "audit",
                    "icon": "ph.warning-circle",
                    "count": wozniak["issues_count"],
                }
            )

        coverage = cls.get_smart_coverage_rate()
        if coverage["unlinked_chunks"] > 0:
            diagnostics.append(
                {
                    "type": "coverage",
                    "title": "Lacunes de Couverture RAG",
                    "message": f"{coverage['unlinked_chunks']} fragment(s) de cours ne sont pas encore couverts par des flashcards.",
                    "severity": "info",
                    "action_label": "📖 Forger les lacunes",
                    "target_view": "analysis",
                    "target_tab": "sources",
                    "icon": "ph.book-open",
                    "count": coverage["unlinked_chunks"],
                }
            )

        dup_count = cls.get_duplicate_anomalies_count()
        if dup_count > 0:
            diagnostics.append(
                {
                    "type": "duplicate",
                    "title": "Doublons & Collisions à Arbitrer",
                    "message": f"{dup_count} doublon(s) potentiel(s) détecté(s) dans votre collection.",
                    "severity": "danger",
                    "action_label": "🤝 Résoudre dans la Fusion",
                    "target_view": "analysis",
                    "target_tab": "duplicates",
                    "icon": "ph.git-merge",
                    "count": dup_count,
                }
            )

        telemetry = cls.get_ai_telemetry()
        if telemetry["total_cost_usd"] >= 10.0:
            diagnostics.append(
                {
                    "type": "budget",
                    "title": "Suivi des Dépenses IA",
                    "message": f"Dépenses cumulées : ${telemetry['total_cost_usd']:.2f} ({telemetry['total_tokens']:,} tokens).",
                    "severity": "info",
                    "action_label": "💳 Voir le suivi financier",
                    "target_view": "analysis",
                    "target_tab": "tokens",
                    "icon": "ph.currency-dollar",
                    "count": 1,
                }
            )

        return diagnostics

    @classmethod
    def _format_macro_action(cls, group: Dict[str, Any]) -> Dict[str, Any]:
        """Formate un groupe de versions en macro-action lisible."""
        source = group.get("source", "manual")
        count = group.get("count", 1)
        deck_name = group.get("deck_name", "Par défaut")
        latest_time: datetime = group.get("latest_time", datetime.now())
        time_str = latest_time.strftime("%Y-%m-%d %H:%M")

        card_str = f"{count} carte{'s' if count > 1 else ''}"

        if source in ["ai_generator", "dag_pipeline"]:
            title = f"Génération IA ({card_str})"
            subtitle = f"Forgée{'s' if count > 1 else ''} • Paquet '{deck_name}' • {time_str}"
            icon = "ph.sparkle"
            bg_color = "rgba(99, 102, 241, 0.15)"
        elif source == "import":
            title = f"Importation de Paquet ({card_str})"
            subtitle = f"Importée{'s' if count > 1 else ''} • Paquet '{deck_name}' • {time_str}"
            icon = "ph.download-simple"
            bg_color = "rgba(245, 158, 11, 0.15)"
        elif source == "merge":
            title = f"Fusion & Smart Merge ({card_str})"
            subtitle = f"Conflits résolus • Paquet '{deck_name}' • {time_str}"
            icon = "ph.git-merge"
            bg_color = "rgba(16, 185, 129, 0.15)"
        else:
            title = f"Édition & Création ({card_str})"
            subtitle = f"Modifiée{'s' if count > 1 else ''} • Paquet '{deck_name}' • {time_str}"
            icon = "ph.pencil-simple"
            bg_color = "rgba(59, 130, 246, 0.15)"

        return {
            "title": title,
            "subtitle": subtitle,
            "source": source,
            "count": count,
            "deck_name": deck_name,
            "icon": icon,
            "bg_color": bg_color,
            "created_at": time_str,
            "sample_note_id": group.get("sample_note_id"),
        }

    @classmethod
    def get_recent_macro_actions(cls, limit: int = 8) -> List[Dict[str, Any]]:
        """Agrège l'activité récente sous forme de grandes actions (batchs, imports, forges) plutôt que carte par carte."""
        actions: List[Dict[str, Any]] = []
        try:
            recent_versions = list(NoteVersionModel.select(NoteVersionModel, NoteModel).join(NoteModel).order_by(NoteVersionModel.created_at.desc()).limit(100))

            if not recent_versions:
                return []

            note_ids = [v.note_id for v in recent_versions if v.note_id]
            deck_name_by_note: Dict[int, str] = {}
            if note_ids:
                cards = CardModel.select(CardModel.note, DeckModel.name).join(DeckModel).where(CardModel.note.in_(note_ids))
                for c in cards:
                    if c.note_id not in deck_name_by_note and c.deck:
                        deck_name_by_note[c.note_id] = c.deck.name

            current_group: Optional[Dict[str, Any]] = None

            for v in recent_versions:
                v_source = v.source or "manual"
                v_time = v.created_at
                deck_name = deck_name_by_note.get(v.note_id, "Par défaut")

                if current_group is None:
                    current_group = {
                        "source": v_source,
                        "deck_name": deck_name,
                        "count": 1,
                        "latest_time": v_time,
                        "sample_note_id": v.note.id if v.note else None,
                    }
                else:
                    time_diff = abs((current_group["latest_time"] - v_time).total_seconds())
                    if current_group["source"] == v_source and time_diff <= 600 and current_group["deck_name"] == deck_name:
                        current_group["count"] += 1
                    else:
                        actions.append(cls._format_macro_action(current_group))
                        if len(actions) >= limit:
                            return actions
                        current_group = {
                            "source": v_source,
                            "deck_name": deck_name,
                            "count": 1,
                            "latest_time": v_time,
                            "sample_note_id": v.note.id if v.note else None,
                        }

            if current_group and len(actions) < limit:
                actions.append(cls._format_macro_action(current_group))

        except Exception as e:
            logger.warning("Erreur lors de l'agrégation des macro-actions : %s", e)

        return actions

    @classmethod
    def get_recent_feed(cls, limit: int = 10) -> List[Dict[str, Any]]:
        """Récupère les dernières versions de notes créées ou éditées (compatibilité)."""
        feed_items: List[Dict[str, Any]] = []
        try:
            recent_versions = NoteVersionModel.select(NoteVersionModel, NoteModel).join(NoteModel).order_by(NoteVersionModel.created_at.desc()).limit(limit)

            for version in recent_versions:
                feed_items.append(
                    {
                        "note_id": version.note.id,
                        "source": version.source or "manual",
                        "created_at": version.created_at.strftime("%Y-%m-%d %H:%M"),
                        "version": version.version_number,
                    }
                )
        except Exception as e:
            logger.warning("Erreur lors de la récupération du flux d'activité : %s", e)

        return feed_items

    @classmethod
    def get_full_dashboard_data(cls) -> Dict[str, Any]:
        """Agrège l'ensemble des données du tableau de bord en une seule passe."""
        wozniak = cls.get_wozniak_health_score()
        coverage = cls.get_smart_coverage_rate()
        telemetry = cls.get_ai_telemetry()
        dup_count = cls.get_duplicate_anomalies_count()

        notes_count = 0
        cards_count = 0
        decks_count = 0
        try:
            notes_count = NoteModel.select().count()
            cards_count = CardModel.select().count()
            decks_count = DeckModel.select().count()
        except Exception:
            pass  # nosec B110

        return {
            "kpis": {
                "wozniak": wozniak,
                "coverage": coverage,
                "telemetry": telemetry,
                "duplicates_count": dup_count,
                "notes_count": notes_count,
                "cards_count": cards_count,
                "decks_count": decks_count,
            },
            "activity_7_days": cls.get_7_days_activity(),
            "diagnostics": cls.get_proactive_diagnostics(),
            "recent_feed": cls.get_recent_feed(10),
            "macro_activities": cls.get_recent_macro_actions(8),
        }
