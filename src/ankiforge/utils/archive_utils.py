"""Extraction d'archives (zip/tar) sécurisée contre les attaques Zip-Slip et les symlinks.

Python 3.12 ne propose pas encore de paramètre ``filter`` pour ``zipfile.extractall``
(ajouté en 3.14). Cette couche fournit donc une extraction manuelle qui :
1. Refuse les chemins absolus et toute remontée ``..`` (Zip-Slip / Path Traversal).
2. Écrit les membres via des fichiers réguliers (jamais de ``os.symlink``) pour
   empêcher la création de lien symbolique vers l'extérieur du répertoire cible.
3. Applique un plafond de taille totale décompressée pour éviter les "zip bombs".
"""

from __future__ import annotations

import logging
import shutil
import tarfile
import zipfile
from pathlib import Path, PurePosixPath

logger = logging.getLogger(__name__)


def safe_extract_zip(
    zip_path: str | Path,
    target_dir: str | Path,
    *,
    max_total_size: int | None = None,
) -> int:
    """Extrait une archive zip dans ``target_dir`` en rejetant les membres dangereux.

    Args:
        zip_path: Chemin de l'archive .zip.
        target_dir: Répertoire de destination (créé si absent).
        max_total_size: Plafond en octets de la taille totale décompressée (None = illimité).

    Returns:
        Le nombre de fichiers extraits.

    Raises:
        ValueError: si un membre s'échappe du répertoire cible (Zip-Slip) ou
            dépasse le plafond de taille annoncé.
        zipfile.BadZipFile: si l'archive est invalide.
    """
    target = Path(target_dir).expanduser().resolve()
    target.mkdir(parents=True, exist_ok=True)

    extracted = 0
    total_size = 0

    with zipfile.ZipFile(Path(zip_path)) as archive:
        for info in archive.infolist():
            member_path = PurePosixPath(info.filename)
            if info.is_dir():
                continue

            # 1. Rejet Zip-Slip : chemins absolus ou remontées de répertoire
            if member_path.is_absolute() or ".." in member_path.parts:
                raise ValueError(f"Entrée d'archive rejetée pour sécurité : chemin non sûr '{info.filename}'.")

            # 2. Confinement dans le répertoire cible
            dest = target.joinpath(*member_path.parts).resolve()
            if dest != target and target not in dest.parents:
                raise ValueError(f"Entrée d'archive rejetée pour sécurité : hors cible '{info.filename}'.")

            # 3. Plafond de taille totale décompressée (anti zip-bomb)
            total_size += info.file_size
            if max_total_size is not None and total_size > max_total_size:
                raise ValueError(f"Archive rejetée pour sécurité : taille décompressée totale ({total_size} octets) dépasse le plafond de {max_total_size} octets.")

            dest.parent.mkdir(parents=True, exist_ok=True)
            # 4. Écriture en fichier régulier : jamais de création de symlink
            with archive.open(info) as src, open(dest, "wb") as out_file:
                shutil.copyfileobj(src, out_file)
            extracted += 1

    logger.debug("Extraction zip terminée : %d fichiers vers %s", extracted, target)
    return extracted


def safe_extract_tar(
    tar_path: str | Path,
    target_dir: str | Path,
    *,
    max_total_size: int | None = None,
) -> int:
    """Extrait une archive tar (généralement .tar.gz) de manière sûre.

    Délègue au mécanisme natif ``filter="data"`` de ``tarfile`` (Python 3.12+) et
    applique en complément un plafond de taille décompressée.

    Args:
        tar_path: Chemin de l'archive tar.
        target_dir: Répertoire de destination.
        max_total_size: Plafond en octets de la taille totale décompressée.

    Returns:
        Le nombre d'extraits inscrits dans l'archive.
    """
    target = Path(target_dir).expanduser().resolve()
    target.mkdir(parents=True, exist_ok=True)

    member_count = 0
    with tarfile.open(Path(tar_path), "r:*") as archive:
        member_count = len(archive.getmembers())
        if max_total_size is not None:
            total_size = sum(m.size for m in archive.getmembers() if m.isfile())
            if total_size > max_total_size:
                raise ValueError(f"Archive rejetée pour sécurité : taille décompressée totale ({total_size} octets) dépasse le plafond de {max_total_size} octets.")
        # nosec B202 : extraction tar avec filtre natif "data" (refuse chemins
        # absolus, '..', devices et crée uniquement fichiers/répertoires sûrs).
        archive.extractall(path=target, filter="data")

    return member_count
