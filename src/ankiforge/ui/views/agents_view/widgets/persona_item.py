from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QWidget

from ankiforge.database.models import PersonaModel
from ankiforge.ui.components import Badge
from ankiforge.ui.theme import DesignTokens
from ankiforge.ui.views.agents_view.constants import PERSONA_TYPE_SPECS
from ankiforge.utils.icon_loader import load_phosphor_icon


class PersonaItemWidget(QWidget):
    """Widget personnalisé pour chaque feuille Persona de l'arbre."""

    def __init__(self, persona: PersonaModel, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.persona = persona
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("background: transparent;")
        self.setFixedHeight(34)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 3, 6, 3)
        layout.setSpacing(6)

        p_type = getattr(persona, "persona_type", "pipeline") or "pipeline"
        type_spec = PERSONA_TYPE_SPECS.get(p_type, PERSONA_TYPE_SPECS["pipeline"])

        icon_lbl = QLabel()
        icon_lbl.setFixedSize(18, 18)
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        if p_type == "mcp":
            icon_name = "ph.handshake"
            icon_color = "#10b981"
        elif p_type == "universal":
            icon_name = "ph.globe"
            icon_color = "#f59e0b"
        else:  # pipeline
            icon_name = "ph.lightning"
            icon_color = "#818cf8"

        icon_lbl.setPixmap(load_phosphor_icon(icon_name, color=icon_color).pixmap(15, 15))
        layout.addWidget(icon_lbl, alignment=Qt.AlignmentFlag.AlignVCenter)

        self.lbl_name = QLabel(str(persona.name))
        self.lbl_name.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-weight: 600; font-size: 11.5px; background: transparent;")
        self.lbl_name.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.lbl_name.setToolTip(f"{persona.name} ({type_spec['badge_text']})")
        layout.addWidget(self.lbl_name, 1)

        fmt_raw = (getattr(persona, "output_format", "JSON") or "JSON").upper()
        if fmt_raw == "JSON":
            fmt_variant = "warning"
        elif fmt_raw in ("CLOZE", "CODE"):
            fmt_variant = "primary"
        elif fmt_raw in ("MARKDOWN", "MD"):
            fmt_variant = "info"
        else:
            fmt_variant = "neutral"

        self.badge_fmt = Badge(fmt_raw, variant=fmt_variant)
        self.badge_fmt.setFixedHeight(18)
        layout.addWidget(self.badge_fmt, alignment=Qt.AlignmentFlag.AlignVCenter)
