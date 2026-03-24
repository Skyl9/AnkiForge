import os
import fitz  # PyMuPDF

# Utilise le même PDF que pour les tests précédents
PDF_PATH = "data/test.pdf"


def extract_text_fast(pdf_path: str, page_number: int = 0) -> str:
    """Extrait le texte brut encodé dans le PDF de manière instantanée."""
    print(f"📄 Ouverture du PDF : {pdf_path}")

    # 1. Ouverture du document
    doc = fitz.open(pdf_path)

    # 2. Chargement de la page
    page = doc.load_page(page_number)

    # 3. Extraction du texte brut
    # get_text() récupère le texte tel qu'il a été encodé lors de la création du PDF
    text = page.get_text()

    return text


if __name__ == "__main__":
    if not os.path.exists(PDF_PATH):
        print(f"❌ Erreur : Fichier introuvable à l'emplacement '{PDF_PATH}'")
    else:
        try:
            print("⚡ Extraction en cours via PyMuPDF...")

            # Extraction
            raw_text = extract_text_fast(PDF_PATH, page_number=0)

            # Affichage
            print("\n" + "=" * 50)
            print("📜 RÉSULTAT DE L'EXTRACTION CLASSIQUE :")
            print("=" * 50 + "\n")
            print(raw_text)
            print("\n" + "=" * 50)
            print("✅ Terminé en un éclair !")

        except Exception as e:
            print(f"❌ Une erreur s'est produite : {e}")