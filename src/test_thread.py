import sys
from PySide6.QtCore import QCoreApplication
from ankiforge.database.models import db
from ankiforge.services.workers.document_worker import DocumentWorker

app = QCoreApplication(sys.argv)
db.connect()


path_or_url = "test.txt"


def on_finished(title, content):
    print("FINISHED:", title, len(content))
    app.quit()


def on_error(err):
    print("ERROR:", err)
    app.quit()


worker = DocumentWorker(path_or_url)
worker.finished_signal.connect(on_finished)
worker.error_signal.connect(on_error)
worker.start()

app.exec()
