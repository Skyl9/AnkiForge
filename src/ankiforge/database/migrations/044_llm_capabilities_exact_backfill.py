"""Migration 044 : remplace des capacités LLM *inférées* par des capacités *déclarées*.

La migration 029 a recopié `ModelCatalog.get_model_spec()`, une aide à la **découverte** : elle
approxime, ignore le fournisseur (`get_model_spec("azure-openai", "gpt-4o")` recopie la fiche
OpenAI, capacités comme tarifs) et se rabat sur des marqueurs de nom. Ses réponses sont depuis
lues comme des déclarations (cf. `vision_capability.resolve_vision_support`), plus comme un simple
affichage : sans réparation, un moteur se voit annoncer « Vision native » — ou « Vision
indisponible » — à partir d'une inférence, et une génération multimodal part vers une API qui la
refuse.

**Seules les lignes dont le couple (fournisseur, modèle) figure au catalogue exact sont corrigées**,
 et uniquement si la valeur diffère. Cette borne est délibérée : la 029 pouvait avoir inventé une
capacité par approximation, mais une valeur *juste* peut aussi venir d'une détection réelle — le
projecteur CLIP d'un Ollama local, que ni le catalogue hors ligne ni une inférence par nom ne savent
évaluer. Rétrograder une ligne de cette catégorie serait une perte d'information sans remède (l'UI
n'offre aucun éditeur de `supports_vision`), alors que corriger une ligne cataloguée n'est que la
restauration d'un fait vérifiable.

Un moteur absent du catalogue est donc laissé tel quel : la curation du catalogue est le remède à
une inférence hasardeuse, pas une inhibition de la Vision par défaut.
"""

import json
import logging

import peewee as pw
from peewee_migrate import Migrator

from ankiforge.services.ai.model_catalog import ModelCatalog

logger = logging.getLogger(__name__)


def migrate(migrator: Migrator, database: pw.Database, *, fake: bool = False) -> None:
    """Migration 044 : recale les capacités sur la fiche curatée exacte du modèle."""
    if not fake and database.table_exists("llm_configs"):
        try:
            with database.atomic():
                cursor = database.execute_sql("SELECT id, provider, model_id, supports_vision, description FROM llm_configs")
                recatalogued = 0
                for r_id, prov, m_id, declared_vision, declared_desc in cursor.fetchall():
                    spec = ModelCatalog.get_declared_capabilities(prov or "", m_id or "")
                    if spec is None:
                        continue
                    # Même source que la 029 : son `ankiforge_use_case` prime, sinon la 044 effacerait
                    # les descriptions d'usage déjà enregistrées sur les profils existants.
                    description = spec.ankiforge_use_case or spec.description
                    if int(declared_vision or 0) == int(spec.supports_vision) and (declared_desc or "") == description:
                        continue
                    database.execute_sql(
                        "UPDATE llm_configs SET supports_vision = ?, supports_thinking = ?, supports_json = ?, speed_rating = ?, quality_tier = ?, recommended_tasks = ?, description = ? WHERE id = ?",
                        (
                            int(spec.supports_vision),
                            int(spec.supports_thinking),
                            int(spec.supports_json),
                            spec.speed_rating,
                            spec.quality_tier,
                            json.dumps(spec.recommended_tasks),
                            description,
                            r_id,
                        ),
                    )
                    recatalogued += 1
            if recatalogued:
                logger.info("Migration 044 : capacités recalees sur le catalogue exact pour %d moteur(s).", recatalogued)
        except Exception as err:
            # La réparation est un confort, jamais un prérequis : bloquer le démarrage de
            # l'application pour une valeur de capacité serait bien plus coûteux que l'écart résiduel.
            logger.error("Réparation des capacités LLM (044) interrompue : %s", err, exc_info=True)


def rollback(migrator: Migrator, database: pw.Database, *, fake: bool = False) -> None:
    """Rollback 044 : sans opération.

    La 044 ne crée ni ne supprime de colonne, et la valeur d'origine d'une capacité ne peut pas être
    reconstruite : la seule restoration possible consiste à relancer le backfill approximatif de la
    029 — ce que la 044 corrige de nouveau au passage. Annuler la 044 n'aurait donc aucun effet utile.
    """
    return
