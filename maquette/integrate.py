import re

with open("concept_macos/index.html", "r") as f:
    macos_html = f.read()

with open("concept_ide/index.html", "r") as f:
    ide_html = f.read()

# Extract sidebar
sidebar_match = re.search(r'(<nav class="sidebar".*?</nav>)', ide_html, re.DOTALL)
sidebar = sidebar_match.group(1) if sidebar_match else ""

# Extract main content
main_match = re.search(r'(<main class="main-content".*?</main>)', ide_html, re.DOTALL)
main_content = main_match.group(1) if main_match else ""

# Extract modals
modals = re.findall(r'(<div class="modal-overlay".*?</div>\s*</div>\s*</div>|<!-- Modals.*?<div class="modal-overlay".*?</div>\s*</div>\s*</div>)', ide_html, re.DOTALL)
# The regex for modals might be tricky. Let's just find the first modal and grab everything till the script tag.
modals_match = re.search(r'(<div class="modal-overlay hidden" id="cmd-palette-modal">.*)    <script src="app.js"></script>', ide_html, re.DOTALL)
modals_html = modals_match.group(1) if modals_match else ""

# Now inject into macos_html
# find mac-content
mac_content_start = macos_html.find('<div class="mac-content">')
mac_content_end = macos_html.find("</div>\n    </div>\n\n    <!-- Modals -->")
if mac_content_end == -1:
    mac_content_end = macos_html.find('</div>\n    </div>\n\n    <script src="app.js"></script>')

if mac_content_start != -1 and mac_content_end != -1:
    mac_content_start += len('<div class="mac-content">')
    # replace
    new_html = macos_html[:mac_content_start] + "\n" + sidebar + "\n" + main_content + "\n        " + macos_html[mac_content_end:]

    # replace modals
    modal_start = new_html.find("<!-- Modals -->")
    if modal_start != -1:
        script_start = new_html.find('<script src="app.js"></script>')
        new_html = new_html[:modal_start] + modals_html + "\n    " + new_html[script_start:]

    with open("concept_macos/index.html", "w") as f:
        f.write(new_html)
    print("Done")
else:
    print("Could not find mac-content boundaries")
