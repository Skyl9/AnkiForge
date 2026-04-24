# src/ankiforge/ui/widgets/donut_chart.py
from PySide6.QtCharts import QChart, QChartView, QPieSeries, QPieSlice
from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QPainter, QColor, QFont, QPen
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel


class DonutChartWidget(QWidget):
    """
    Un graphique en anneau (Donut) réutilisable, interactif et 100% natif.
    """

    def __init__(self, title_center="TOTAL", parent=None):
        super().__init__(parent)
        self.title_center = title_center
        self.total = 0

        # Palette de couleurs générique (Thème moderne)
        self.theme_colors = ["#FF6384", "#36A2EB", "#FFCE56", "#4BC0C0", "#9966FF", "#FF9F40", "#E7E9ED", "#8D6E63"]

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)

        # 1. La Série
        self.series = QPieSeries()
        self.series.setHoleSize(0.55)
        self.series.setPieSize(0.8)
        self.series.hovered.connect(self.on_slice_hovered)

        # 2. Le Graphique
        self.chart = QChart()
        self.chart.addSeries(self.series)
        self.chart.setAnimationOptions(QChart.AnimationOption.SeriesAnimations)
        self.chart.setBackgroundBrush(Qt.GlobalColor.transparent)  # Fond transparent
        self.chart.layout().setContentsMargins(0, 0, 0, 0)
        self.chart.legend().setAlignment(Qt.AlignmentFlag.AlignBottom)
        self.chart.legend().setLabelColor(QColor("palette(text)"))
        self.chart.legend().setFont(QFont("sans-serif", 10, QFont.Weight.Bold))

        # 3. La Vue
        self.chart_view = QChartView(self.chart)
        self.chart_view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.chart_view.setStyleSheet("background: transparent;")

        # 4. Le Label Central (Infobulle)
        self.center_label = QLabel(self.chart_view)
        self.center_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.center_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        self.main_layout.addWidget(self.chart_view)

    def update_data(self, data_dict: dict[str, int]):
        """
        Met à jour le graphique avec de nouvelles données.
        Format attendu : {"Maths": 120, "Anglais": 50}
        """
        self.series.clear()
        self.total = sum(data_dict.values())

        if self.total == 0:
            self.update_center_label_default()
            return

        color_index = 0
        for label, value in data_dict.items():
            if value <= 0:
                continue  # On ignore les parts vides

            slice_ = self.series.append(label, value)
            slice_.setBrush(QColor(self.theme_colors[color_index % len(self.theme_colors)]))
            slice_.setPen(QPen(QColor("palette(base)"), 3))  # Bordure de la couleur des panneaux
            slice_.setLabelVisible(False)
            color_index += 1

        self.update_center_label_default()

    def resizeEvent(self, event):
        """Maintient le texte parfaitement au centre du trou du donut."""
        super().resizeEvent(event)
        rect = self.chart_view.geometry()
        # Ajustement manuel pour compenser la légende en bas
        self.center_label.setGeometry(rect.width() // 2 - 100, (rect.height() // 2 - 50) - 15, 200, 100)

    @Slot(QPieSlice, bool)
    def on_slice_hovered(self, slice_, is_hovered):
        """Animation d'explosion et mise à jour du texte central."""
        if is_hovered:
            slice_.setExploded(True)
            slice_.setExplodeDistanceFactor(0.05)

            pct = int((slice_.value() / self.total) * 100) if self.total > 0 else 0
            color = slice_.brush().color().name()

            # HTML propre pour le centre
            html = f"""
            <div style='font-family: sans-serif; text-align: center;'>
                <div style='font-size: 12px; color: palette(placeholder-text); font-weight: bold;'>{slice_.label().upper()}</div>
                <div style='font-size: 28px; color: {color}; font-weight: bold; margin-top: 2px;'>{int(slice_.value())}</div>
                <div style='font-size: 11px; color: palette(placeholder-text);'>({pct}%)</div>
            </div>
            """
            self.center_label.setText(html)
        else:
            slice_.setExploded(False)
            self.update_center_label_default()

    def update_center_label_default(self):
        html = f"""
        <div style='font-family: sans-serif; text-align: center;'>
            <div style='font-size: 12px; color: palette(placeholder-text); font-weight: bold;'>{self.title_center}</div>
            <div style='font-size: 28px; color: palette(text); font-weight: bold; margin-top: 2px;'>{self.total}</div>
        </div>
        """
        self.center_label.setText(html)
