import os

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["ANKIFORGE_ENV"] = "testing"

from PySide6.QtWidgets import QApplication

from ankiforge.database.models import DocumentModel
from ankiforge.ui.style_engine import get_style_engine
from ankiforge.ui.views.documents_view.dialogs.delimitation_dialog import DocumentDelimitationDialog
from ankiforge.utils.paths import get_project_root


def main() -> None:
    from ankiforge.services.profile_manager import ProfileManager

    pm = ProfileManager()
    pm.switch_profile("default")

    app = QApplication.instance() or QApplication([])
    engine = get_style_engine()
    engine.apply_theme("ide")

    doc, _ = DocumentModel.get_or_create(
        title="Physiologie Humaine - Système Cardiovasculaire.pdf",
        defaults={
            "content": (
                "<!-- PAGE: 1 -->\n# Sommaire\nTable des matières générale.\n\n"
                "<!-- PAGE: 2 -->\n# Préface & Remerciements\nCe cours a été rédigé avec l'aide des étudiants.\n\n"
                "<!-- PAGE: 3 -->\n# 1. Anatomie Cardiaque\nLe cœur est constitué de quatre cavités : deux oreillettes et deux ventricules.\n\n"
                "<!-- PAGE: 4 -->\n# 2. Cycle Cardiaque\nLa révolution cardiaque comprend la systole auriculaire, la systole ventriculaire et la diastole générale.\n\n"
                "<!-- PAGE: 5 -->\n# 3. Électrophysiologie & ECG\nL'onde P correspond à la dépolarisation auriculaire. Le complexe QRS traduit la dépolarisation ventriculaire.\n\n"
                "<!-- PAGE: 6 -->\n# 4. Régulation Hémodynamique\nLe débit cardiaque est le produit de la fréquence cardiaque par le volume d'éjection systolique.\n\n"
                "<!-- PAGE: 7 -->\n# Bibliographie & Annexes\nOuvrages de référence et tables de constantes physiologiques.\n"
            ),
            "file_type": "pdf",
            "total_pages": 7,
            "start_page": 3,
            "end_page": 6,
        },
    )

    dlg = DocumentDelimitationDialog(doc)
    dlg.resize(720, 660)
    dlg.show()
    for _ in range(10):
        app.processEvents()

    out_dir = get_project_root() / "temp" / "screens"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "delimitation_modal.png"
    dlg.grab().save(str(out_file))
    print(f"Capture réussie : {out_file}")


if __name__ == "__main__":
    main()
