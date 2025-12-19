# src/services/prompt_manager.py
import os
from jinja2 import Environment, FileSystemLoader


class PromptManager:
    def __init__(self, template_dir="src/prompts"):
        # On pointe vers le dossier où sont stockés tes fichiers .jinja2
        if not os.path.exists(template_dir):
            template_dir = "prompts"  # Fallback au cas où on lance depuis un autre dossier

        self.env = Environment(loader=FileSystemLoader(template_dir))

    def get_prompt(self, template_name: str, **kwargs) -> str:
        """
        Charge un template Jinja2 et remplace les variables.
        Ex: get_prompt("card_gen.jinja2", fields_str="Front, Back")
        """
        template = self.env.get_template(template_name)
        return template.render(**kwargs)