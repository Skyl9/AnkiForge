from PySide6.QtCore import QSettings, QCoreApplication


def reset_wizard():
    # On s'assure de cibler exactement la même organisation que ton application
    QCoreApplication.setOrganizationName("AnkiForgeOrg")
    QCoreApplication.setApplicationName("ankiforge_obsidian")

    settings = QSettings("AnkiForgeOrg", "ankiforge_obsidian")

    # On supprime la clé spécifique
    settings.remove("app/tour_completed")
    settings.sync()  # Force l'écriture immédiate sur le disque

    print("✅ Clé supprimée avec succès !")
    print("Tu peux maintenant lancer ankiforge_obsidian, l'assistant de bienvenue devrait s'afficher.")


if __name__ == "__main__":
    reset_wizard()
