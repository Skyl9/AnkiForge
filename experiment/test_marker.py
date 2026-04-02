import subprocess
import os
import time

# 1. PARAMÈTRES (Mets le bon chemin vers ton PDF)
PDF_PATH = "../data/test.pdf"
OUTPUT_DIR = "../marker_output_test"


def run_marker_test():
    if not os.path.exists(PDF_PATH):
        print(f"❌ Erreur : Le fichier {PDF_PATH} est introuvable.")
        return

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print(f"🧠 Lancement de Marker sur : {PDF_PATH}")
    print("⏳ Attention : Le premier lancement va télécharger plusieurs Go de modèles d'IA (PyTorch).")
    print("La ventilation de ton Mac risque de s'activer, c'est normal !")
    print("-" * 50)

    start_time = time.time()

    try:
        # On appelle le script CLI de Marker
        command = ["marker_single", PDF_PATH, "--output_dir", OUTPUT_DIR]

        # On lance le processus et on attend (capture_output=False pour voir la barre de progression en direct !)
        subprocess.run(command, check=True)

        elapsed_time = time.time() - start_time
        print("-" * 50)
        print(f"✅ Extraction terminée en {elapsed_time:.2f} secondes !")
        print(f"📁 Va vérifier le résultat dans le dossier : {OUTPUT_DIR}")

    except subprocess.CalledProcessError as e:
        print(f"❌ Marker a planté avec le code erreur : {e.returncode}")
    except FileNotFoundError:
        print("❌ La commande 'marker_single' est introuvable. L'installation a-t-elle réussi ?")


if __name__ == "__main__":
    run_marker_test()