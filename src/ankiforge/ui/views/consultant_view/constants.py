import markdown
from PySide6.QtWidgets import QLabel

from ankiforge.ui.theme import DesignTokens


def apply_pill_style(badge: QLabel, color_hex: str) -> None:
    """Applique un style de capsule/pill parfaitement arrondie avec fond translucide et bordure assortie."""
    hex_c = color_hex.lstrip("#")
    r, g, b = int(hex_c[0:2], 16), int(hex_c[2:4], 16), int(hex_c[4:6], 16)
    badge.setStyleSheet(f"""
        QLabel {{
            background-color: rgba({r}, {g}, {b}, 0.15) !important;
            color: {color_hex};
            border: 1px solid rgba({r}, {g}, {b}, 0.35);
            border-radius: 9999px;
            padding: 3px 12px;
            font-size: 10px;
            font-weight: bold;
            letter-spacing: 0.5px;
        }}
    """)


def render_markdown_message(text: str) -> str:
    """Convertit du texte Markdown en HTML avec typographie et styles élégants."""
    html_content = markdown.markdown(text, extensions=["tables", "fenced_code", "nl2br", "sane_lists"])
    styled_html = f"""
    <div style="font-family: {DesignTokens.FONT_MAIN}; font-size: 13px; line-height: 1.5; color: {DesignTokens.TEXT_PRIMARY};">
        <style>
            h1, h2, h3, h4, h5, h6 {{
                color: {DesignTokens.TEXT_PRIMARY};
                margin-top: 8px;
                margin-bottom: 4px;
                font-weight: bold;
            }}
            h3 {{ font-size: 13px; color: {DesignTokens.ACCENT_PRIMARY}; }}
            h4 {{ font-size: 12px; color: {DesignTokens.COLOR_YELLOW}; }}
            p {{ margin: 3px 0; color: {DesignTokens.TEXT_PRIMARY}; }}
            ul, ol {{ margin: 3px 0; padding-left: 16px; color: {DesignTokens.TEXT_PRIMARY}; }}
            li {{ margin-bottom: 2px; }}
            strong {{ color: {DesignTokens.TEXT_PRIMARY}; font-weight: bold; }}
            em {{ color: {DesignTokens.TEXT_SECONDARY}; font-style: italic; }}
            code {{
                background-color: {DesignTokens.BG_MAIN};
                color: {DesignTokens.COLOR_BLUE};
                font-family: '{DesignTokens.FONT_CODE}';
                font-size: 11px;
                padding: 1px 4px;
                border-radius: 3px;
                border: 1px solid {DesignTokens.BORDER_COLOR};
            }}
            pre {{
                background-color: {DesignTokens.BG_MAIN};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 6px;
                padding: 8px 10px;
                margin: 6px 0;
            }}
            pre code {{
                background-color: transparent;
                border: none;
                padding: 0;
                color: #38bdf8;
            }}
        </style>
        {html_content}
    </div>
    """
    return styled_html
