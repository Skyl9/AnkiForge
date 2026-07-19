import re

with open("concept_macos/styles.css", "r") as f:
    macos_css = f.read()

with open("concept_ide/styles.css", "r") as f:
    ide_css = f.read()

# Replace variables in ide_css to match macOS look
ide_css = re.sub(r"--bg-main:.*?;", "--bg-main: transparent;", ide_css)
ide_css = re.sub(r"--bg-sidebar:.*?;", "--bg-sidebar: rgba(245, 245, 247, 0.6);", ide_css)
ide_css = re.sub(r"--bg-panel:.*?;", "--bg-panel: rgba(255, 255, 255, 0.6);", ide_css)
ide_css = re.sub(r"--bg-input:.*?;", "--bg-input: rgba(255, 255, 255, 0.8);", ide_css)
ide_css = re.sub(r"--bg-hover:.*?;", "--bg-hover: rgba(0, 0, 0, 0.05);", ide_css)
ide_css = re.sub(r"--bg-active:.*?;", "--bg-active: rgba(0, 122, 255, 0.1);", ide_css)
ide_css = re.sub(r"--accent-primary:.*?;", "--accent-primary: #007AFF;", ide_css)
ide_css = re.sub(r"--accent-hover:.*?;", "--accent-hover: #005bb5;", ide_css)
ide_css = re.sub(r"--text-primary:.*?;", "--text-primary: #1D1D1F;", ide_css)
ide_css = re.sub(r"--text-secondary:.*?;", "--text-secondary: #515154;", ide_css)
ide_css = re.sub(r"--text-muted:.*?;", "--text-muted: #86868B;", ide_css)
ide_css = re.sub(r"--border-color:.*?;", "--border-color: rgba(0, 0, 0, 0.1);", ide_css)
ide_css = re.sub(r"--border-light:.*?;", "--border-light: rgba(0, 0, 0, 0.05);", ide_css)
ide_css = re.sub(r"--shadow-sm:.*?;", "--shadow-sm: 0 1px 2px rgba(0, 0, 0, 0.05);", ide_css)
ide_css = re.sub(r"--shadow-md:.*?;", "--shadow-md: 0 4px 12px rgba(0, 0, 0, 0.1);", ide_css)
ide_css = re.sub(r"--shadow-glass:.*?;", "--shadow-glass: 0 8px 32px rgba(0, 0, 0, 0.15);", ide_css)

# Remove :root, *, body, .hidden from ide_css since we already have them or will handle them.
# We keep :root for variables, but merge it.
# Actually, just append ide_css below macos_css, but remove `body { ... }` from ide_css to prevent overriding background.
ide_css = re.sub(r"body\s*{[^}]+}", "", ide_css)
ide_css = re.sub(r"\*\s*{[^}]+}", "", ide_css)

# Update ide-panel and others to have backdrop-filter
ide_css = ide_css.replace(".ide-panel {", ".ide-panel {\n  backdrop-filter: blur(20px);")
ide_css = ide_css.replace(".sidebar {", ".sidebar {\n  backdrop-filter: blur(20px);")

with open("concept_macos/styles.css", "w") as f:
    f.write(macos_css + "\n/* --- IDE CSS --- */\n" + ide_css)
