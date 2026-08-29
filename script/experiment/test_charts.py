import sys

from PySide6.QtCharts import QChart, QChartView, QPieSeries, QPieSlice
from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QApplication, QLabel, QMainWindow, QVBoxLayout, QWidget


class EnhancedQtChart(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("QtCharts poussé au maximum")
        self.resize(800, 600)
        self.setStyleSheet("background-color: #1E1E1E;")

        # Données
        self.labels = ["Mathématiques", "Physique", "Informatique", "Anglais"]
        self.values = [120, 80, 200, 50]
        self.colors = ["#FF6384", "#36A2EB", "#FFCE56", "#4BC0C0"]
        self.total = sum(self.values)

        # 1. Configuration de la Série (Le Camembert troué)
        self.series = QPieSeries()
        self.series.setHoleSize(0.55)  # Trou plus large pour le texte central
        self.series.setPieSize(0.8)

        for i in range(len(self.labels)):
            slice_ = self.series.append(self.labels[i], self.values[i])
            slice_.setBrush(QColor(self.colors[i]))

            # Bordures de la couleur du fond pour faire des "gaps" propres
            pen = QPen(QColor("#1E1E1E"), 4)
            slice_.setPen(pen)

            slice_.setLabelVisible(False)  # On cache les étiquettes natives moches

        # Connexion du signal de survol
        self.series.hovered.connect(self.on_slice_hovered)

        # 2. Configuration du Graphique
        self.chart = QChart()
        self.chart.addSeries(self.series)
        self.chart.setAnimationOptions(QChart.AnimationOption.SeriesAnimations)
        self.chart.setBackgroundBrush(QColor("#1E1E1E"))
        self.chart.layout().setContentsMargins(0, 0, 0, 0)
        self.chart.legend().setAlignment(Qt.AlignmentFlag.AlignBottom)
        self.chart.legend().setLabelColor(QColor("#E0E0E0"))
        self.chart.legend().setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))

        # 3. La Vue (Anti-aliasing activé pour lisser les bords)
        self.chart_view = QChartView(self.chart)
        self.chart_view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.chart_view.setStyleSheet("border: none; background: transparent;")

        # 4. LE SECRET : Un Label superposé au centre du trou
        self.center_label = QLabel(self.chart_view)
        self.center_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.center_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)  # Laisse passer la souris
        self.update_center_label_default()

        # Layout
        layout = QVBoxLayout()
        layout.addWidget(self.chart_view)
        widget = QWidget()
        widget.setLayout(layout)
        self.setCentralWidget(widget)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # On recentre dynamiquement le label à chaque redimensionnement
        rect = self.chart_view.geometry()
        # Ajustement manuel pour centrer au milieu du doughnut (dépend de la légende)
        y_offset = -20
        self.center_label.setGeometry(rect.width() // 2 - 100, (rect.height() // 2 - 50) + y_offset, 200, 100)

    @Slot(QPieSlice, bool)
    def on_slice_hovered(self, slice_, is_hovered):
        """Animation et mise à jour du texte au survol de la souris."""
        if is_hovered:
            # Effet "Pop"
            slice_.setExploded(True)
            slice_.setExplodeDistanceFactor(0.05)

            # Mise à jour du texte central avec du HTML
            pct = int((slice_.value() / self.total) * 100)
            color = slice_.brush().color().name()
            html = f"""
            <div style='font-family: sans-serif; text-align: center;'>
                <div style='font-size: 14px; color: #888; font-weight: bold;'>{slice_.label().upper()}</div>
                <div style='font-size: 32px; color: {color}; font-weight: bold; margin-top: 5px;'>{int(slice_.value())}</div>
                <div style='font-size: 12px; color: #666;'>({pct}%)</div>
            </div>
            """
            self.center_label.setText(html)
        else:
            # Retour à la normale
            slice_.setExploded(False)
            self.update_center_label_default()

    def update_center_label_default(self):
        """L'affichage par défaut (Total)."""
        html = f"""
        <div style='font-family: sans-serif; text-align: center;'>
            <div style='font-size: 14px; color: #888; font-weight: bold;'>TOTAL CARTES</div>
            <div style='font-size: 32px; color: white; font-weight: bold; margin-top: 5px;'>{self.total}</div>
        </div>
        """
        self.center_label.setText(html)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = EnhancedQtChart()
    window.show()
    sys.exit(app.exec())
