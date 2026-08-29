import json
import xml.etree.ElementTree as ET  # nosec B405
from pathlib import Path

# Chemins
root = Path(__file__).parent.parent
json_path = root / "src/ankiforge/ressources/translations/fr_backup.json"
ts_path = root / "src/ankiforge/ressources/translations/fr_FR.ts"

# Charger le dico français
with open(json_path, encoding="utf-8") as f:
    fr_dict = json.load(f)

# Parser le fichier XML de Qt
tree = ET.parse(ts_path)  # nosec B314
xml_root = tree.getroot()

filled_count = 0

for context in xml_root.findall("context"):
    for message in context.findall("message"):
        source_el = message.find("source")
        translation_el = message.find("translation")
        if source_el is not None and translation_el is not None:
            source = source_el.text
            # Si on a la traduction dans notre JSON, on l'injecte !
            if source and source in fr_dict:
                translation_el.text = fr_dict[source]
                translation_el.attrib.pop("type", None)  # Retire le tag "unfinished"
                filled_count += 1

# Sauvegarder le XML
tree.write(ts_path, encoding="utf-8", xml_declaration=True)
print(f"✅ Succès : {filled_count} traductions injectées automatiquement dans fr_FR.ts !")
