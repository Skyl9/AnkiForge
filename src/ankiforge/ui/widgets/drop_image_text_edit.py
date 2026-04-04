# src/ankiforge/ui/widgets/drop_image_text_edit.py
import os
import shutil
import uuid

from PySide6.QtCore import QMimeData
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QTextEdit

from ankiforge.utils.paths import get_app_data_dir


class DropImageTextEdit(QTextEdit):
    """
    Un éditeur de texte brut qui intercepte les images (Drag&Drop et Ctrl+V)
    et écrit automatiquement la balise HTML correspondante.
    """

    def insertFromMimeData(self, source: QMimeData) -> None:
        media_dir = get_app_data_dir() / "media"
        media_dir.mkdir(parents=True, exist_ok=True)

        inserted_image = False

        # 1. Cas : Fichier image glissé-déposé
        if source.hasUrls():
            for url in source.urls():
                if url.isLocalFile():
                    file_path = url.toLocalFile()
                    ext = os.path.splitext(file_path)[1].lower()

                    if ext in ['.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp']:
                        new_name = f"img_{uuid.uuid4().hex[:8]}{ext}"
                        dest_path = media_dir / new_name
                        shutil.copy2(file_path, dest_path)

                        # On insère le TEXTE de la balise, pas le HTML rendu
                        self.textCursor().insertText(f'<img src="{new_name}">\n')
                        inserted_image = True

            if inserted_image:
                return

        # 2. Cas : Ctrl+V d'une image (Presse-papier / Capture d'écran)
        if source.hasImage():
            image = source.imageData()
            if isinstance(image, QImage):
                new_name = f"img_{uuid.uuid4().hex[:8]}.png"
                dest_path = media_dir / new_name
                image.save(str(dest_path))

                # On insère le TEXTE de la balise
                self.textCursor().insertText(f'<img src="{new_name}">\n')
                return

        # 3. Fallback : Comportement normal si c'est juste du texte
        super().insertFromMimeData(source)