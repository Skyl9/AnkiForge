import json
import logging
import time
from PySide6.QtCore import QThread, Signal
from ankiforge.database.models import JobModel, db, DocumentModel, FolderModel
from ankiforge.services.parsing.document_parser import DocumentParser

logger = logging.getLogger(__name__)


class BackgroundDaemon(QThread):
    """
    Le moteur inarrêtable. Scanne la BDD et exécute les tâches de fond.
    """

    job_updated = Signal()  # Signal pour rafraîchir l'UI

    def __init__(self):
        super().__init__()
        self._is_running = True

    def stop(self):
        self._is_running = False

    def run(self):
        logger.info(" Forge Immortelle : Démon de fond démarré.")

        # Routine de récupération post-crash
        self._recover_interrupted_jobs()

        while self._is_running:
            # On cherche la prochaine tâche en attente
            job = JobModel.get_or_none(JobModel.status == "pending")

            if job:
                self._process_job(job)
            else:
                # On dort un peu pour ne pas saturer le CPU
                time.sleep(5)

    def _recover_interrupted_jobs(self):
        """Remet en 'pending' les jobs qui étaient en cours lors d'un crash."""
        with db.atomic():
            query = JobModel.update(status="pending").where(JobModel.status == "processing")
            count = query.execute()
            if count > 0:
                logger.info(f"♻️ Récupération : {count} tâches interrompues remises en file d'attente.")

    def _process_job(self, job):
        try:
            job.status = "processing"
            job.save()
            self.job_updated.emit()

            if job.job_type == "parse_pdf":
                self._execute_parse_pdf(job)

            job.status = "completed"
            job.progress = 100
            job.save()
            logger.info(f"✅ Job {job.id} ({job.job_type}) terminé avec succès.")

        except Exception as e:
            logger.exception(f"❌ Échec du Job {job.id} :")
            job.status = "failed"
            job.error_log = str(e)
            job.save()

        self.job_updated.emit()

    def _execute_parse_pdf(self, job):
        """Logique de parsing PDF déportée dans le démon."""
        parser = DocumentParser()

        # On simule la progression (Marker ne donne pas de % précis mais on peut logguer)
        def log_progress(msg):
            logger.info(f"[Job {job.id}] {msg}")
            # On peut parser le log de Marker pour estimer un % si besoin

        content = parser.parse_document(job.target, progress_callback=log_progress)

        # Sauvegarde du document final
        params = json.loads(job.params) if job.params else {}
        folder_id = params.get("folder_id")
        folder = FolderModel.get_or_none(FolderModel.id == folder_id) if folder_id else None

        import pathlib

        title = pathlib.Path(job.target).stem

        with db.atomic():
            DocumentModel.create(title=title, content=content, folder=folder)
