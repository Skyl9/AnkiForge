import logging
import pathlib
from urllib.parse import urlparse

from PySide6.QtCore import QThread, Signal

from ankiforge.services.parsing.document_parser import DocumentParser

logger = logging.getLogger(__name__)


class DocumentWorker(QThread):
    finished_signal = Signal(str, str)
    error_signal = Signal(str)
    log_signal = Signal(str)
    cancelled_signal = Signal()

    def __init__(self, file_path: str):
        super().__init__()
        self.file_path = file_path
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def is_cancelled(self) -> bool:
        return self._is_cancelled

    def run(self):
        try:
            parser = DocumentParser()
            if self.file_path.startswith("http"):
                parsed_url = urlparse(self.file_path)
                # On essaie de prendre le dernier mot de l'URL, sinon le nom de domaine
                raw_title = parsed_url.path.strip("/").split("/")[-1]
                if not raw_title:
                    raw_title = parsed_url.netloc
                title = f"Web - {raw_title}"
            else:
                title = pathlib.Path(self.file_path).stem
            title = title[:50]
            content = parser.parse_document(self.file_path, progress_callback=self.log_signal.emit, check_cancel=self.is_cancelled)
            if not self._is_cancelled:
                self.finished_signal.emit(title, content)
        except InterruptedError as e:
            logger.info(f"Analyse annulée par l'utilisateur : {str(e)}")
            self.log_signal.emit(f"\n {str(e)}")
            self.cancelled_signal.emit()
        except Exception as e:
            logger.exception("Erreur lors de l'analyse du document :")
            self.error_signal.emit(str(e))
