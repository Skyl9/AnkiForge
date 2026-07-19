import zipfile
from pathlib import Path

import zstandard as zstd


def extract_anki_db(apkg_path: str | Path, output_dir: str | Path) -> Path:
    """
    Extrait la base de données SQLite (collection.anki2 ou collection.anki21)
    depuis un fichier archive .apkg Anki.

    :param apkg_path: Chemin vers le fichier .apkg
    :param output_dir: Dossier de destination pour l'extraction
    :return: Le chemin complet vers le fichier SQLite extrait
    """
    apkg_file = Path(apkg_path)
    out_dir = Path(output_dir)

    # 1. Vérifications de sécurité
    if not apkg_file.exists() or not apkg_file.is_file():
        raise FileNotFoundError(f"Le fichier {apkg_file} est introuvable.")

    if not zipfile.is_zipfile(apkg_file):
        raise ValueError(f"Le fichier {apkg_file} n'est pas une archive ZIP valide.")

    out_dir.mkdir(parents=True, exist_ok=True)

    # 2. Cibles : Anki utilise deux formats selon la version
    db_names = ["collection.anki21", "collection.anki2"]
    extracted_db_path = None

    # 3. Ouverture et extraction chirurgicale
    with zipfile.ZipFile(apkg_file, "r") as archive:
        file_list = archive.namelist()

        for db_name in db_names:
            if db_name in file_list:
                # On extrait UNIQUEMENT la base de données, pas les médias lourds
                extracted_path = archive.extract(db_name, path=out_dir)
                extracted_db_path = Path(extracted_path)
                break

        if not extracted_db_path:
            raise FileNotFoundError("Aucune base de données SQLite Anki trouvée dans cette archive.")

    return extracted_db_path


def extract_modern_anki_db(apkg_path: str | Path, output_dir: str | Path) -> Path:
    apkg_file = Path(apkg_path)
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(apkg_file, "r") as archive:
        file_list = archive.namelist()

        # 1. Gestion du format moderne compressé (>2.1.50)
        if "collection.anki21b" in file_list:
            raw_path = archive.extract("collection.anki21b", path=out_dir)
            extracted_db_path = out_dir / "collection.anki21"

            # Décompression Zstandard
            dctx = zstd.ZstdDecompressor()
            with open(raw_path, "rb") as f_in, open(extracted_db_path, "wb") as f_out:
                dctx.copy_stream(f_in, f_out)

            Path(raw_path).unlink()  # Nettoyage du fichier brut
            return extracted_db_path

        # 2. Gestion de l'ancien format (Non compressé)
        elif "collection.anki21" in file_list or "collection.anki2" in file_list:
            target = "collection.anki21" if "collection.anki21" in file_list else "collection.anki2"
            raw_path = archive.extract(target, path=out_dir)
            return Path(raw_path)

        else:
            raise FileNotFoundError("Aucune base de données Anki trouvée.")


# ==========================================
# TEST D'EXÉCUTION
# ==========================================
if __name__ == "__main__":
    # Nom du fichier que vous aviez fourni dans votre contexte précédent
    fichier_cible = "Default.apkg"
    dossier_temporaire = "./anki_temp_db"

    try:
        print(f"⏳ Extraction de la base de données depuis '{fichier_cible}'...")
        db_path = extract_modern_anki_db(fichier_cible, dossier_temporaire)

        print(f"✨ Succès ! La base de données est extraite : {db_path}")
        print("Vous pouvez maintenant la brancher à PyCharm (Database) ou Peewee pour l'auditer.")

    except Exception as e:
        print(f"❌ Erreur critique : {e}")
