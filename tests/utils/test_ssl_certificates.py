import os
import sys
from unittest.mock import patch

from ankiforge.utils.ssl_certificates import find_valid_ca_bundle, setup_ssl_certificates


def test_find_valid_ca_bundle_real():
    """Vérifie que find_valid_ca_bundle trouve un bundle valide dans l'environnement courant."""
    bundle = find_valid_ca_bundle()
    assert bundle is not None
    assert bundle.is_file()
    assert bundle.stat().st_size > 0


def test_setup_ssl_certificates_sets_env():
    """Vérifie que setup_ssl_certificates configure correctement SSL_CERT_FILE."""
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("SSL_CERT_FILE", None)
        path_str = setup_ssl_certificates()
        assert path_str is not None
        assert os.environ.get("SSL_CERT_FILE") == path_str
        assert os.path.isfile(path_str)


def test_find_valid_ca_bundle_fallback_when_none(tmp_path):
    """Vérifie le comportement quand aucun fichier candidat n'est trouvé."""
    with (
        patch.dict(sys.modules, {"certifi": None}),
        patch.dict(os.environ, {}, clear=True),
        patch("sys.executable", str(tmp_path / "dummy_bin")),
        patch("pathlib.Path.is_file", return_value=False),
    ):
        res = find_valid_ca_bundle()
        assert res is None


def test_setup_ssl_certificates_no_crash_on_empty():
    """Vérifie que setup_ssl_certificates ne plante pas même si aucun bundle n'est localisé."""
    with patch("ankiforge.utils.ssl_certificates.find_valid_ca_bundle", return_value=None), patch.dict(os.environ, {}, clear=False):
        os.environ.pop("SSL_CERT_FILE", None)
        res = setup_ssl_certificates()
        assert res is None
