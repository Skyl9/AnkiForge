"""Modèles Peewee pour les définitions de drapeaux Anki et leur personnalisation par profil."""

from peewee import (
    BooleanField,
    CharField,
    Check,
    ForeignKeyField,
    IntegerField,
)

from ankiforge.database.base import BaseModel


class FlagDefinitionModel(BaseModel):
    """Définition canonique des 8 drapeaux Anki (0-7). Table de référence immuable."""

    value = IntegerField(unique=True, constraints=[Check("value BETWEEN 0 AND 7")])
    name = CharField()  # "Aucun", "Rouge", "Orange", "Vert", "Bleu", "Rose", "Turquoise", "Violet"
    color_hex = CharField()  # "#ef4444", "#f97316", "#10b981", "#3b82f6", "#ec4899", "#06b6d4", "#a855f7", "transparent"
    is_customizable = BooleanField(default=True)  # False pour value=0, True pour 1-7
    sort_order = IntegerField(default=0)  # Pour ordre d'affichage stable

    class Meta:
        table_name = "flag_definition"
        indexes = ((("value",), True),)  # Unique index sur value


class ProfileFlagLabelModel(BaseModel):
    """Libellé personnalisé d'un drapeau pour un profil utilisateur donné."""

    profile_name = CharField()  # Nom du profil (ex: "default")
    flag_definition = ForeignKeyField(FlagDefinitionModel, backref="profile_labels", on_delete="CASCADE")
    custom_label = CharField(null=True)  # NULL = utilise le nom natif

    class Meta:
        table_name = "profile_flag_label"
        indexes = ((("profile_name", "flag_definition"), True),)  # Unique composite
