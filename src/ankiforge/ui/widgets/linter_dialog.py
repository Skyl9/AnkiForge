import json
from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea, QWidget, QFrame, QMessageBox
import qtawesome as qta

from ankiforge.services.workers.linter_worker import LinterWorker
from ankiforge.services.cards.store_manager import StoreManager
from ankiforge.ui.components.components import PrimaryButton, ActionButton, HeaderLabel
from ankiforge.ui.widgets.toast import show_toast


class LinterDialog(QDialog):
    def __init__(self, note_ids: list[int], parent=None):
        super().__init__(parent)
        self.note_ids = note_ids
        self.store = StoreManager()
        self.setWindowTitle("IA Linter - Audit des Cartes")
        self.setMinimumSize(800, 600)
        self.setModal(True)

        self.worker: LinterWorker | None = None
        self._setup_ui()
        self._start_audit()

    def _setup_ui(self):
        self.main_layout = QVBoxLayout(self)

        # Header
        self.header = HeaderLabel("Audit basé sur les 20 règles de Piotr Wozniak")
        self.main_layout.addWidget(self.header)

        self.status_label = QLabel("Initialisation...")
        self.main_layout.addWidget(self.status_label)

        # Scroll area for results
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_content = QWidget()
        self.scroll_layout = QVBoxLayout(self.scroll_content)
        self.scroll_area.setWidget(self.scroll_content)

        self.main_layout.addWidget(self.scroll_area)

        # Footer
        self.btn_close = ActionButton("fa5s.times", "Fermer")
        self.btn_close.clicked.connect(self.close)

        footer = QHBoxLayout()
        footer.addStretch()
        footer.addWidget(self.btn_close)
        self.main_layout.addLayout(footer)

    def _start_audit(self):
        self.status_label.setText("L'IA analyse les cartes, veuillez patienter...")
        self.worker = LinterWorker(self.note_ids)
        self.worker.progress_update.connect(self.status_label.setText)
        self.worker.finished_processing.connect(self._on_audit_finished)
        self.worker.error_occurred.connect(self._on_error)
        self.worker.start()

    def _on_error(self, err: str):
        self.status_label.setText("Erreur lors de l'audit.")
        QMessageBox.critical(self, "Erreur", f"L'audit a échoué: {err}")

    def _on_audit_finished(self, results: list[dict]):
        self.status_label.setText(f"Audit terminé. {len(results)} cartes analysées.")

        for res in results:
            note_id = res.get("note_id")
            # Handling both pass and pass_ gracefully, though AI generates 'pass'
            passed = res.get("pass", res.get("pass_", True))
            rule = res.get("rule_broken", "N/A")
            reason = res.get("reason", "N/A")
            suggestion = res.get("suggestion", {})

            panel = QFrame()
            panel.setFrameShape(QFrame.Shape.StyledPanel)
            p_layout = QVBoxLayout(panel)

            if passed:
                lbl = QLabel(f"✅ Carte #{note_id} : Parfait !")
                lbl.setStyleSheet("color: #4CAF50; font-weight: bold;")
                p_layout.addWidget(lbl)
            else:
                lbl = QLabel(f"⚠️ Carte #{note_id} : {rule}")
                lbl.setStyleSheet("color: #F44336; font-weight: bold;")
                p_layout.addWidget(lbl)

                desc = QLabel(f"Raison : {reason}")
                desc.setWordWrap(True)
                p_layout.addWidget(desc)

                if suggestion:
                    sugg_lbl = QLabel(f"Suggestion : {json.dumps(suggestion, ensure_ascii=False, indent=2)}")
                    sugg_lbl.setStyleSheet("background: palette(alternate-base); padding: 5px; border-radius: 4px; font-family: monospace;")
                    sugg_lbl.setWordWrap(True)
                    p_layout.addWidget(sugg_lbl)

                    btn_apply = PrimaryButton(qta.icon("fa5s.check", color="white"), "Appliquer la suggestion")
                    # Capture variable in closure safely
                    btn_apply.clicked.connect(lambda _, nid=note_id, sug=suggestion, pnl=panel: self._apply_suggestion(nid, sug, pnl))
                    p_layout.addWidget(btn_apply)

            self.scroll_layout.addWidget(panel)

        self.scroll_layout.addStretch()

    def _apply_suggestion(self, note_id: int, suggestion: dict, panel: QFrame):
        try:
            self.store.apply_linter_suggestion(note_id, suggestion)
            panel.hide()
            show_toast(self, f"Suggestion appliquée pour la carte #{note_id}", is_error=False)
        except Exception as e:
            QMessageBox.warning(self, "Erreur", f"Impossible d'appliquer la suggestion: {e}")
