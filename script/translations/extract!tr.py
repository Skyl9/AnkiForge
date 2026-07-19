import ast
import json
import xml.etree.ElementTree as ET  # nosec B405
from xml.dom import minidom  # nosec B408
from pathlib import Path


def extract_translations():
    root_dir = Path(__file__).parent.parent
    src_dir = root_dir / "src" / "ankiforge"
    json_path = root_dir / "src" / "ankiforge" / "ressources" / "translations" / "fr_backup.json"
    ts_path = root_dir / "src" / "ankiforge" / "ressources" / "translations" / "fr_FR.ts"

    # Charger le dictionnaire français généré précédemment
    fr_dict = {}
    if json_path.exists():
        with open(json_path, "r", encoding="utf-8") as f:
            fr_dict = json.load(f)

    ts = ET.Element("TS", version="2.1", language="fr_FR")

    # Parcourir tous les fichiers Python du projet
    for py_file in src_dir.rglob("*.py"):
        with open(py_file, "r", encoding="utf-8") as f:
            try:
                tree = ast.parse(f.read(), filename=str(py_file))
            except SyntaxError:
                continue

        # Trouver les classes et les appels self.tr()
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                class_name = node.name
                strings_found = set()

                for child in ast.walk(node):
                    if isinstance(child, ast.Call):
                        # Chercher la fonction 'tr'
                        if isinstance(child.func, ast.Attribute) and child.func.attr == "tr":
                            if child.args and isinstance(child.args[0], ast.Constant):
                                strings_found.add(child.args[0].value)

                # Si on a trouvé des textes, on crée le contexte Qt
                if strings_found:
                    context = ET.SubElement(ts, "context")
                    name = ET.SubElement(context, "name")
                    name.text = class_name

                    for text in strings_found:
                        message = ET.SubElement(context, "message")
                        source = ET.SubElement(message, "source")
                        source.text = text
                        translation = ET.SubElement(message, "translation")

                        # Pré-remplir avec notre JSON si disponible
                        if text in fr_dict:
                            translation.text = fr_dict[text]
                        else:
                            translation.attrib["type"] = "unfinished"

    # Sauvegarder le fichier XML proprement
    ts_path.parent.mkdir(parents=True, exist_ok=True)
    xml_str = minidom.parseString(ET.tostring(ts, encoding="utf-8")).toprettyxml(indent="    ")  # nosec B318
    # Retirer les lignes vides superflues de minidom
    xml_str = "\n".join(line for line in xml_str.split("\n") if line.strip())

    with open(ts_path, "w", encoding="utf-8") as f:
        f.write(xml_str)
    print(f"✅ Fichier {ts_path.name} généré avec succès avec le bon contexte !")


if __name__ == "__main__":
    extract_translations()
