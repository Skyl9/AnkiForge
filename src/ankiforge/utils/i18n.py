"""
Amorçage de l'internationalisation d'AnkiForge (mécanique Qt Linguist).

Ce module est **l'unique couture** de la traduction runtime :

- il résout le dossier des catalogues (`.ts` sources versionnées, `.qm` compilés) via
  :func:`ankiforge.utils.paths.get_resource_path`, jamais via ``Path(__file__)`` ;
- il installe le :class:`QTranslator` correspondant à la langue demandée ;
- il expose :func:`tr`, l'équivalent de ``self.tr()`` pour le code qui n'est pas
  une sous-classe de ``QObject`` (fonctions de module, helpers, classes de service).

Langue source : **français**. C'est le texte écrit dans le code ; l'anglais est une
cible de traduction. Conséquence directe : quand aucun catalogue n'est disponible
(environnement « non traduit », catalogue absent, fichier illisible), l'interface
retombe **silencieusement** sur le français — jamais sur une chaîne vide et jamais
sur une exception au démarrage.

Vocabulaire (ADR 0013) :

- « catalogue » : fichier ``ankiforge_<langue>.ts`` versionné, produit par
  ``pyside6-lupdate`` (voir ``script/extract_translations.py``) ;
- « source » : la langue du texte écrit dans le code (``SOURCE_LANGUAGE``) ;
- « contexte » : la clé de regroupement des messages dans un catalogue, produite
  automatiquement par Qt Linguist (``self.tr()`` ⇒ nom de la classe, ``tr()`` ⇒
  contexte vide) ;
- « langue » : toujours un code ISO 639-1, jamais un libellé d'affichage ;
- « marqueur de position » : un jeton ``%1``, ``%2``… ou ``%n`` dans un littéral
  traduit, convention Qt Linguist, résolu par :func:`tr` après traduction.

Deux conventions d'écriture s'imposent donc dans le code source :

- **littéral** → ``self.tr("Enregistrer")`` dans une sous-classe de ``QObject``,
  ``tr("Enregistrer")`` ailleurs (fonctions de module, helpers, services) ;
- **littéral interpolé** → ``tr("Enregistré : %1/%2", faits, total)`` et **jamais**
  ``tr(f"...")``. Une f-chaîne est évaluée *avant* l'appel à ``tr()`` : le catalogue ne
  verrait alors qu'une suite de messages uniques, tous introuvables à l'exécution, et le
  traducteur gaspillerait son temps sur des entrées mortes.

Ces deux formes sont les seules que ``pylupdate`` extraie : il reconnaît ``self.tr()``
et ``tr()``, et rien d'autre — un helper d'interpolation nommé autrement serait
invisible au catalogue sans aucune erreur pour le signaler.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QCoreApplication, QTranslator

from ankiforge.utils.paths import get_resource_path

if TYPE_CHECKING:
    from PySide6.QtWidgets import QApplication

logger = logging.getLogger(__name__)

# ── Constantes de contrat ────────────────────────────────────────────────────
#: Langue du texte écrit dans le code. Un catalogue identique à celui-ci est inutile
#: à l'exécution : le repli natif de Qt restitue déjà le texte source.
SOURCE_LANGUAGE = "fr"

#: Langue servie quand la langue demandée n'a pas de catalogue exploitable.
FALLBACK_LANGUAGE = "fr"

#: Préfixe commun à tous les catalogues (``ankiforge_fr.ts``, ``ankiforge_en.qm``...).
CATALOG_STEM = "ankiforge"

#: Chemin du dossier de catalogues, relatif à la racine du dépôt/bundle.
#: Doit rester cohérent avec ``nuitka_config.json`` et ``build_standalone.py``.
TRANSLATIONS_RELPATH = ("src", "ankiforge", "resources", "translations")

#: Endonymes des langues proposées dans les réglages : un nom de langue ne se
#: traduit pas (norme de rédaction), il est donc hors catalogue.
LANGUAGE_LABELS: dict[str, str] = {
    "fr": "Français",
    "en": "English",
}

#: Langues proposées quand aucune liste n'est fournie (ordre d'affichage stable).
DEFAULT_LANGUAGES: tuple[str, ...] = ("fr", "en")

_LANGUAGE_CODE_RE = re.compile(r"[A-Za-z]{2,3}")

#: Marqueurs de position Qt Linguist : ``%1``..``%99``, ``%n`` (position libre) et ``%%``
#: (pourcentage littéral, convention ``QString::arg``).
_PLACEHOLDER_RE = re.compile(r"%(\d{1,2}|n|%)")


def normalize_language(value: object, default: str = SOURCE_LANGUAGE) -> str:
    """Ramène une valeur de réglage quelconque à un code ISO 639-1.

    Accepte indifféremment un code (``"fr"``, ``"en_US"``, ``"en-US"``) ou un
    endonyme stocké par les réglages (``"Français"``, ``"English"``), ce qui rend la
    migration des réglages historiques inutile.

    Args:
        value: Valeur brute lue dans les réglages (``None``, ``str`` ou autre).
        default: Code renvoyé quand ``value`` ne contient aucune lettre.

    Returns:
        str: Code de langue en minuscules, ``default`` si rien n'est exploitable.
    """
    if value is None:
        return default
    text = str(value).strip()
    if not text:
        return default

    for code, label in LANGUAGE_LABELS.items():
        if text.casefold() == label.casefold():
            return code

    match = _LANGUAGE_CODE_RE.search(text)
    if not match:
        return default
    return match.group(0).lower()


def language_label(code: str) -> str:
    """Renvoie l'endonyme d'une langue (jamais traduit, par construction)."""
    normalized = normalize_language(code)
    return LANGUAGE_LABELS.get(normalized, code)


def translations_dir() -> Path:
    """Renvoie le dossier des catalogues, résolu par ``utils.paths``.

    La résolution passe exclusivement par :func:`get_resource_path` : un ``Path(__file__)``
    casserait la lecture des catalogues dans un bundle Nuitka ou PyInstaller, exactement
    comme la divergence de nommage ``src/ressources`` / ``src/ankiforge/ressources`` a
    cassé ``database/seeds/initial_seed.py``.

    Returns:
        Path: Le dossier cible, existant ou non (le dossier peut être absent d'un bundle
        minimal : l'appelant doit tolérer l'absence, jamais la casser).
    """
    return get_resource_path(*TRANSLATIONS_RELPATH)


def catalog_path(language: str, *, suffix: str = ".qm", directory: Path | None = None) -> Path:
    """Renvoie le chemin d'un catalogue pour la langue donnée.

    Args:
        language: Code ou endonyme de langue, toléré en entrée.
        suffix: ``".qm"`` pour le catalogue compilé, ``".ts"`` pour la source.
        directory: Dossier des catalogues ; par défaut : :func:`translations_dir`.

    Returns:
        Path: Le chemin du catalogue (existant ou non).
    """
    base = directory if directory is not None else translations_dir()
    return base / f"{CATALOG_STEM}_{normalize_language(language)}{suffix}"


def available_languages(directory: Path | None = None) -> tuple[str, ...]:
    """Liste les langues proposables dans les réglages, dans un ordre d'affichage stable.

    La langue source figure **toujours** en tête : elle est écrite dans le code et
    fonctionne donc sans aucun catalogue sur disque. L'omettre rendrait la liste vide
    sur un poste où rien n'a encore été compilé — et un sélecteur de langue vide est
    illegal. Les autres langues n'apparaissent qu'avec un ``.qm`` présent : proposer une
    langue sans catalogue reviendrait à promettre une traduction inexistante.

    Args:
        directory: Dossier des catalogues ; par défaut : :func:`translations_dir`.

    Returns:
        tuple[str, ...]: Codes de langue, dédupliqués, la source en premier puis
        :data:`DEFAULT_LANGUAGES`, puis le reste alphabétiquement.
    """
    found: list[str] = [SOURCE_LANGUAGE]
    base = directory if directory is not None else translations_dir()
    if base.is_dir():
        for catalog in base.glob(f"{CATALOG_STEM}_*.qm"):
            code = normalize_language(catalog.stem[len(CATALOG_STEM) + 1 :], default="")
            if code and code not in found:
                found.append(code)

    ordered = [code for code in DEFAULT_LANGUAGES if code in found]
    ordered.extend(code for code in sorted(found) if code not in ordered)
    return tuple(ordered)


def install_translator(app: QApplication, language: object = None, *, directory: Path | None = None) -> QTranslator | None:
    """Installe le catalogue de la langue demandée. Ne lève jamais.

    Politique de repli, du plus favorable au moins favorable :

    1. langue == :data:`SOURCE_LANGUAGE` : rien à installer, le code contient déjà
       la langue source (instancier un traducteur identité ne ferait que ralentir
       chaque appel ``tr()`` sans jamais rien traduire) ;
    2. catalogue ``.qm`` présent et chargeable : le catalogue est installé ;
    3. catalogue absent, illisible ou vide : aucun traducteur n'est installé et l'interface
       reste en français — un environnement non traduit ne doit pas empêcher le démarrage.

    Args:
        app: Instance ``QApplication`` destinataire de l'installateur.
        language: Langue demandée ; ``None`` délègue à :func:`preferred_language`.
        directory: Dossier des catalogues ; par défaut : :func:`translations_dir`.

    Returns:
        QTranslator | None: Le traducteur installé, ou ``None`` si le repli français
        s'applique. L'appelant doit conserver la référence : Qt ne propage pas la
        propriété Python du ``QTranslator`` installé.
    """
    if language is None:
        try:
            requested = preferred_language()
        except Exception as err:  # l'amorçage ne doit jamais échouer sur une préférence illisible
            logger.debug("Lecture de la langue préférée impossible (%s) : repli sur « %s ».", err, SOURCE_LANGUAGE)
            requested = SOURCE_LANGUAGE
    else:
        requested = normalize_language(language)

    if requested == SOURCE_LANGUAGE:
        logger.debug("Langue source (français) demandée : aucun catalogue à installer.")
        return None

    qm_file = catalog_path(requested, directory=directory)
    if not qm_file.is_file():
        logger.info("Aucun catalogue pour la langue « %s » (%s) : l'interface reste en « %s ».", requested, qm_file, FALLBACK_LANGUAGE)
        return None

    translator = QTranslator()
    if not translator.load(str(qm_file)):
        logger.warning("Catalogue « %s » illisible (%s) : l'interface reste en « %s ».", requested, qm_file, FALLBACK_LANGUAGE)
        return None

    if not app.installTranslator(translator):
        logger.warning("Qt a refusé l'installation du catalogue « %s » : l'interface reste en « %s ».", requested, FALLBACK_LANGUAGE)
        return None

    logger.info("Catalogue i18n installé : « %s » ← %s", requested, qm_file.name)
    return translator


def preferred_language() -> str:
    """Renvoie la langue demandée par les réglages, normalisée.

    L'absence de réglages (boot minimal, tests, bundle sans base) n'est pas une erreur :
    la langue source est alors servie.

    Returns:
        str: Code de langue normalisé.
    """
    try:
        from ankiforge.services.settings_service import SettingsService

        stored = SettingsService.get("ui/language", None)
    except Exception as err:  # le démarrage ne doit jamais dépendre des réglages
        logger.debug("Lecture du réglage de langue impossible (%s) : repli sur « %s ».", err, SOURCE_LANGUAGE)
        return SOURCE_LANGUAGE

    return normalize_language(stored)


def tr(text: str, *values: object) -> str:
    """Traduit une chaîne pour le code hors ``QObject`` (contexte vide).

    Équivalent de ``self.tr()`` pour une fonction de module, un helper libre ou une
    classe qui n'hérite pas de ``QObject``. Qt Linguist range ces messages dans le
    contexte vide du catalogue ; ``self.tr()``, lui, range les siens sous le nom de
    la classe. Les deux conventions sont supportées nativement par ``pylupdate``.

    **Forme interpolée.** Quand des valeurs sont fournies, ``text`` doit contenir des
    marqueurs de position Qt Linguist (``%1``, ``%2``, ``%n``) et ceux-ci sont résolus
    après traduction. Cette variante est obligatoire, et non une commodité :
    ``tr(f"... {x} ...")`` serait évalué *avant* l'appel, produisant un message différent
    à chaque valeur — donc jamais présent dans le catalogue, donc intraduisible.

    Elle ne peut pas s'appuyer sur ``QString::arg()`` : PySide6 expose
    ``QCoreApplication.translate()`` comme un ``str`` Python, sans la méthode C++.

    Args:
        text: Texte source (en français), écrit en littéral pour rester extractible.
        *values: Valeurs à substituer aux marqueurs, dans l'ordre des marqueurs
            numérotés. Absents, ``text`` est renvoyé traduit tel quel.

    Returns:
        str: Le texte traduit (et substitué si besoin), ou ``text`` lui-même si aucun
        catalogue ne l'a traduit — jamais une chaîne vide.
    """
    translated = QCoreApplication.translate("", text)
    if not values:
        return translated

    consumed: set[int] = set()

    def resolve(match: re.Match[str]) -> str:
        marker = match.group(1)
        if marker == "%":
            return "%"

        # ``%n`` = plus petite position encore libre ; ``%k`` = position k (base 1).
        free = next((i for i in range(len(values)) if i not in consumed), None)
        index = free if marker == "n" else int(marker) - 1
        if index is None or not 0 <= index < len(values):
            # Marqueur orphelin : on le rend tel quel plutôt que de le perdre, pour que
            # la faute reste visible dans l'interface au lieu de disparaître.
            return match.group(0)
        consumed.add(index)
        return str(values[index])

    return _PLACEHOLDER_RE.sub(resolve, translated)
