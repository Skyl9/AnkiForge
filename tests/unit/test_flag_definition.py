# tests/unit/test_flag_definition.py
"""Tests unitaires pour FlagDefinitionModel, ProfileFlagLabelModel et FlagService."""

import pytest
from peewee import IntegrityError

from ankiforge.database.models import FlagDefinitionModel, ProfileFlagLabelModel
from ankiforge.database.seeds.initial_seed import seed_initial_data
from ankiforge.services.cards.flag_service import FlagService
from ankiforge.utils.paths import set_active_profile


@pytest.fixture(autouse=True)
def seeded_db(mock_db):
    """Seed la base de données avec les données initiales (inclut les drapeaux)."""
    seed_initial_data()
    return


@pytest.fixture
def active_profile():
    """Fixture qui définit un profil actif pour les tests."""
    set_active_profile("test_profile")
    yield "test_profile"
    set_active_profile("default")


@pytest.mark.unit
class TestFlagDefinitionModel:
    """Tests pour le modèle FlagDefinitionModel."""

    def test_canonical_flags_exist(self, mock_db):
        """Les 8 drapeaux canoniques (0-7) doivent exister en base."""
        flags = list(FlagDefinitionModel.select().order_by(FlagDefinitionModel.value))
        assert len(flags) == 8
        for i, flag in enumerate(flags):
            assert flag.value == i

    def test_flag_definition_fields(self, mock_db):
        """Vérifie les champs de chaque définition de drapeau."""
        flag = FlagDefinitionModel.get(FlagDefinitionModel.value == 1)
        assert flag.name == "Rouge"
        assert flag.color_hex == "#ef4444"
        assert flag.is_customizable is True
        assert flag.sort_order == 1

    def test_flag_0_not_customizable(self, mock_db):
        """Le drapeau 0 (Aucun) n'est pas personnalisable."""
        flag = FlagDefinitionModel.get(FlagDefinitionModel.value == 0)
        assert flag.name == "Aucun"
        assert flag.color_hex == "transparent"
        assert flag.is_customizable is False
        assert flag.sort_order == 0

    def test_unique_constraint_on_value(self, mock_db):
        """La contrainte d'unicité sur value doit être respectée."""
        with pytest.raises(IntegrityError):
            FlagDefinitionModel.create(value=1, name="Test", color_hex="#000000")


@pytest.mark.unit
class TestProfileFlagLabelModel:
    """Tests pour le modèle ProfileFlagLabelModel."""

    def test_create_custom_label(self, mock_db, active_profile):
        """Création d'un libellé personnalisé pour un profil."""
        flag_def = FlagDefinitionModel.get(FlagDefinitionModel.value == 1)
        label = ProfileFlagLabelModel.create(
            profile_name=active_profile,
            flag_definition=flag_def,
            custom_label="Urgent",
        )
        assert label.custom_label == "Urgent"
        assert label.profile_name == active_profile
        assert label.flag_definition == flag_def

    def test_unique_composite_constraint(self, mock_db, active_profile):
        """Contrainte d'unicité composite (profile_name, flag_definition)."""
        flag_def = FlagDefinitionModel.get(FlagDefinitionModel.value == 1)
        ProfileFlagLabelModel.create(profile_name=active_profile, flag_definition=flag_def, custom_label="Label 1")
        with pytest.raises(IntegrityError):
            ProfileFlagLabelModel.create(profile_name=active_profile, flag_definition=flag_def, custom_label="Label 2")

    def test_null_custom_label_means_native(self, mock_db, active_profile):
        """custom_label NULL signifie utiliser le nom natif."""
        flag_def = FlagDefinitionModel.get(FlagDefinitionModel.value == 2)
        label = ProfileFlagLabelModel.create(
            profile_name=active_profile,
            flag_definition=flag_def,
            custom_label=None,
        )
        assert label.custom_label is None

    def test_same_label_different_profiles(self, mock_db):
        """Le même drapeau peut avoir des libellés différents selon le profil."""
        flag_def = FlagDefinitionModel.get(FlagDefinitionModel.value == 1)
        ProfileFlagLabelModel.create(profile_name="profile_a", flag_definition=flag_def, custom_label="Urgent")
        ProfileFlagLabelModel.create(profile_name="profile_b", flag_definition=flag_def, custom_label="Important")
        assert ProfileFlagLabelModel.select().count() == 2


@pytest.mark.unit
class TestFlagService:
    """Tests pour le service FlagService."""

    def test_get_flag_labels_default(self, mock_db, active_profile):
        """get_flag_labels retourne les noms natifs par défaut."""
        FlagService._invalidate_cache()
        labels = FlagService.get_flag_labels()

        assert len(labels) == 8
        assert labels[0] == "Aucun"
        assert labels[1] == "Rouge"
        assert labels[2] == "Orange"
        assert labels[3] == "Vert"
        assert labels[4] == "Bleu"
        assert labels[5] == "Rose"
        assert labels[6] == "Turquoise"
        assert labels[7] == "Violet"

    def test_get_flag_labels_with_custom_override(self, mock_db, active_profile):
        """get_flag_labels respecte les overrides personnalisés."""
        # Créer un override
        flag_def = FlagDefinitionModel.get(FlagDefinitionModel.value == 1)
        ProfileFlagLabelModel.create(profile_name=active_profile, flag_definition=flag_def, custom_label="Urgent")

        FlagService._invalidate_cache()
        labels = FlagService.get_flag_labels()

        assert labels[1] == "Urgent"
        assert labels[2] == "Orange"  # inchangé

    def test_get_flag_name(self, mock_db, active_profile):
        """get_flag_name retourne le bon libellé."""
        FlagService._invalidate_cache()
        assert FlagService.get_flag_name(0) == "Aucun"
        assert FlagService.get_flag_name(1) == "Rouge"
        assert FlagService.get_flag_name(7) == "Violet"
        assert FlagService.get_flag_name(99) == "Aucun"  # invalide

    def test_get_flag_color(self, mock_db, active_profile):
        """get_flag_color retourne la bonne couleur."""
        FlagService._invalidate_cache()
        assert FlagService.get_flag_color(0) == "transparent"
        assert FlagService.get_flag_color(1) == "#ef4444"
        assert FlagService.get_flag_color(3) == "#10b981"

    def test_get_flag_definition(self, mock_db, active_profile):
        """get_flag_definition retourne la définition complète."""
        FlagService._invalidate_cache()
        defn = FlagService.get_flag_definition(1)
        assert defn is not None
        assert defn["name"] == "Rouge"
        assert defn["color_hex"] == "#ef4444"
        assert defn["is_customizable"] is True
        assert "id" in defn

    def test_set_flag_labels(self, mock_db, active_profile):
        """set_flag_labels crée/met à jour les overrides."""
        FlagService._invalidate_cache()
        FlagService.set_flag_labels({1: "Urgent", 2: "Important"})

        # Vérifier en base
        flag_def_1 = FlagDefinitionModel.get(FlagDefinitionModel.value == 1)
        flag_def_2 = FlagDefinitionModel.get(FlagDefinitionModel.value == 2)
        label_1 = ProfileFlagLabelModel.get((ProfileFlagLabelModel.profile_name == active_profile) & (ProfileFlagLabelModel.flag_definition == flag_def_1))
        label_2 = ProfileFlagLabelModel.get((ProfileFlagLabelModel.profile_name == active_profile) & (ProfileFlagLabelModel.flag_definition == flag_def_2))
        assert label_1.custom_label == "Urgent"
        assert label_2.custom_label == "Important"

    def test_set_flag_labels_empty_resets(self, mock_db, active_profile):
        """set_flag_labels avec chaîne vide supprime l'override."""
        # Créer d'abord un override
        flag_def = FlagDefinitionModel.get(FlagDefinitionModel.value == 1)
        ProfileFlagLabelModel.create(profile_name=active_profile, flag_definition=flag_def, custom_label="Ancien")

        FlagService._invalidate_cache()
        FlagService.set_flag_labels({1: ""})  # Chaîne vide = reset

        # L'override doit avoir été supprimé
        assert ProfileFlagLabelModel.select().where((ProfileFlagLabelModel.profile_name == active_profile) & (ProfileFlagLabelModel.flag_definition == flag_def)).count() == 0

    def test_set_flag_labels_same_as_native_resets(self, mock_db, active_profile):
        """set_flag_labels avec le nom natif supprime l'override."""
        flag_def = FlagDefinitionModel.get(FlagDefinitionModel.value == 1)
        ProfileFlagLabelModel.create(profile_name=active_profile, flag_definition=flag_def, custom_label="Rouge")

        FlagService._invalidate_cache()
        FlagService.set_flag_labels({1: "Rouge"})  # Identique au natif = reset

        assert ProfileFlagLabelModel.select().where((ProfileFlagLabelModel.profile_name == active_profile) & (ProfileFlagLabelModel.flag_definition == flag_def)).count() == 0

    def test_reset_to_defaults(self, mock_db, active_profile):
        """reset_to_defaults supprime tous les overrides du profil."""
        flag_def_1 = FlagDefinitionModel.get(FlagDefinitionModel.value == 1)
        flag_def_2 = FlagDefinitionModel.get(FlagDefinitionModel.value == 2)
        ProfileFlagLabelModel.create(profile_name=active_profile, flag_definition=flag_def_1, custom_label="Test 1")
        ProfileFlagLabelModel.create(profile_name=active_profile, flag_definition=flag_def_2, custom_label="Test 2")

        FlagService._invalidate_cache()
        FlagService.reset_to_defaults()

        assert ProfileFlagLabelModel.select().where(ProfileFlagLabelModel.profile_name == active_profile).count() == 0

    def test_get_flag_search_map_includes_custom(self, mock_db, active_profile):
        """get_flag_search_map inclut les libellés personnalisés."""
        flag_def = FlagDefinitionModel.get(FlagDefinitionModel.value == 1)
        ProfileFlagLabelModel.create(profile_name=active_profile, flag_definition=flag_def, custom_label="Urgent")

        FlagService._invalidate_cache()
        search_map = FlagService.get_flag_search_map()

        assert "urgent" in search_map
        assert search_map["urgent"] == 1
        assert "rouge" in search_map  # alias natif toujours présent

    def test_migrate_legacy_settings(self, mock_db, active_profile):
        """migrate_legacy_settings migre depuis SettingsService."""
        from ankiforge.services.settings_service import SettingsService

        # Simuler un paramètre legacy
        SettingsService.set("anki/flag_labels", {"1": "Urgent", "2": "Important"}, category="anki")

        FlagService._invalidate_cache()
        migrated = FlagService.migrate_legacy_settings()

        assert migrated == 2

        # Vérifier que les overrides existent en base
        flag_def_1 = FlagDefinitionModel.get(FlagDefinitionModel.value == 1)
        flag_def_2 = FlagDefinitionModel.get(FlagDefinitionModel.value == 2)
        assert ProfileFlagLabelModel.get((ProfileFlagLabelModel.profile_name == active_profile) & (ProfileFlagLabelModel.flag_definition == flag_def_1)).custom_label == "Urgent"
        assert ProfileFlagLabelModel.get((ProfileFlagLabelModel.profile_name == active_profile) & (ProfileFlagLabelModel.flag_definition == flag_def_2)).custom_label == "Important"

        # L'ancien paramètre doit avoir été nettoyé
        raw = SettingsService.get("anki/flag_labels", default={})
        assert raw == {}

    def test_migrate_legacy_settings_skips_native(self, mock_db, active_profile):
        """migrate_legacy_settings ignore les valeurs identiques aux natives."""
        from ankiforge.services.settings_service import SettingsService

        # Valeur identique au natif
        SettingsService.set("anki/flag_labels", {"1": "Rouge"}, category="anki")

        FlagService._invalidate_cache()
        migrated = FlagService.migrate_legacy_settings()

        assert migrated == 0
        assert ProfileFlagLabelModel.select().where(ProfileFlagLabelModel.profile_name == active_profile).count() == 0
