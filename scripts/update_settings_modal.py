path = "/Users/tristanrigaud-humbert/PycharmProjects/AnkiForge/src/ankiforge/ui/widgets/settings_modal.py"
with open(path, "r", encoding="utf-8") as f:
    content = f.read()

# 1. Update the table headers
target1 = 'self.table_engines = StyledTableWidget(["Nom", "Fournisseur", "Identifiant Modèle"])'
replace1 = 'self.table_engines = StyledTableWidget(["Nom", "Fournisseur", "Identifiant Modèle", "Gratuit"])'
content = content.replace(target1, replace1)

# 2. Update refresh_data
target2 = """                self.table_engines.setItem(i, 0, item_name)
                self.table_engines.setItem(i, 1, QTableWidgetItem(getattr(eg, "provider", "inconnu").upper()))
                self.table_engines.setItem(i, 2, QTableWidgetItem(getattr(eg, "model_id", "default")))"""
replace2 = """                self.table_engines.setItem(i, 0, item_name)
                self.table_engines.setItem(i, 1, QTableWidgetItem(getattr(eg, "provider", "inconnu").upper()))
                self.table_engines.setItem(i, 2, QTableWidgetItem(getattr(eg, "model_id", "default")))
                
                item_free = QTableWidgetItem()
                item_free.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
                item_free.setCheckState(Qt.CheckState.Checked if getattr(eg, "is_free", False) else Qt.CheckState.Unchecked)
                self.table_engines.setItem(i, 3, item_free)"""
content = content.replace(target2, replace2)

# 3. Update _on_table_item_changed
target3 = """            if item.column() == 0:
                config.display_name = item.text().strip()
            elif item.column() == 1:
                config.provider = item.text().strip().lower()
            elif item.column() == 2:
                config.model_id = item.text().strip()
            config.save()"""
replace3 = """            if item.column() == 0:
                config.display_name = item.text().strip()
            elif item.column() == 1:
                config.provider = item.text().strip().lower()
            elif item.column() == 2:
                config.model_id = item.text().strip()
            elif item.column() == 3:
                config.is_free = (item.checkState() == Qt.CheckState.Checked)
            config.save()"""
content = content.replace(target3, replace3)

# Add is_free=True to Ollama
target4 = 'LLMConfigModel.create(display_name="Ollama Local", provider="ollama", model_id="llama3", context_limit=8192, api_key="")'
replace4 = 'LLMConfigModel.create(display_name="Ollama Local", provider="ollama", model_id="llama3", context_limit=8192, api_key="", is_free=True)'
content = content.replace(target4, replace4)

with open(path, "w", encoding="utf-8") as f:
    f.write(content)

print("Updated settings_modal.py successfully.")
