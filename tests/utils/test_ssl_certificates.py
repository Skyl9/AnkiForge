import os
import sys
import types
from unittest.mock import patch

import pytest

from ankiforge.utils.ssl_certificates import find_valid_ca_bundle, pin_ca_bundle_to_requests, setup_ssl_certificates

pytestmark = pytest.mark.unit


BUNDLE_CONTENT = b"dummy-ca-bundle-content"


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
    with (
        patch("ankiforge.utils.ssl_certificates.find_valid_ca_bundle", return_value=None),
        patch.dict(os.environ, {"SSL_CERT_FILE": "/missing/cacert.pem"}, clear=False),
    ):
        res = setup_ssl_certificates()
        assert res is None
        assert "SSL_CERT_FILE" not in os.environ


def _make_fake_requests_modules(certifi_path: str) -> dict[str, types.ModuleType]:
    """Construit des modules factices certifi/requests pour tester le patch sans effet de bord."""
    certifi_fake = types.ModuleType("certifi")
    certifi_fake.where = lambda: certifi_path
    utils_fake = types.ModuleType("requests.utils")
    utils_fake.DEFAULT_CA_BUNDLE_PATH = "frozen/Contents/MacOS/certifi/cacert.pem"
    adapters_fake = types.ModuleType("requests.adapters")
    adapters_fake.DEFAULT_CA_BUNDLE_PATH = "frozen/Contents/MacOS/certifi/cacert.pem"
    certs_fake = types.ModuleType("requests.certs")
    certs_fake.DEFAULT_CA_BUNDLE_PATH = "frozen/Contents/MacOS/certifi/cacert.pem"
    requests_fake = types.ModuleType("requests")
    return {
        "certifi": certifi_fake,
        "requests": requests_fake,
        "requests.utils": utils_fake,
        "requests.adapters": adapters_fake,
        "requests.certs": certs_fake,
    }


def test_pin_ca_bundle_to_requests_repoints_certifi_and_requests(tmp_path):
    """Vérifie que le bundle résolu est épinglé dans certifi.where() et requests.DEFAULT_CA_BUNDLE_PATH.

    Reproduit le défaut des builds Nuitka : certifi.where() pointe vers un chemin gelé
    inexistant (Contents/MacOS/certifi/cacert.pem) alors que le bundle vit dans Contents/Resources.
    """
    bundle = tmp_path / "cacert.pem"
    bundle.write_bytes(BUNDLE_CONTENT)
    fakes = _make_fake_requests_modules("frozen/Contents/MacOS/certifi/cacert.pem")

    with patch.dict(sys.modules, fakes):
        pin_ca_bundle_to_requests(bundle)

    assert fakes["certifi"].where() == str(bundle)
    assert str(bundle) == fakes["requests.utils"].DEFAULT_CA_BUNDLE_PATH
    assert str(bundle) == fakes["requests.adapters"].DEFAULT_CA_BUNDLE_PATH
    assert str(bundle) == fakes["requests.certs"].DEFAULT_CA_BUNDLE_PATH


def test_pin_ca_bundle_to_requests_missing_bundle(tmp_path):
    """Vérifie qu'un bundle inexistant est quand même épinglé (le path est valide selon cert_verify)."""
    missing = tmp_path / "missing" / "cacert.pem"
    fakes = _make_fake_requests_modules("whatever")
    with patch.dict(sys.modules, fakes):
        pin_ca_bundle_to_requests(missing)
    assert fakes["certifi"].where() == str(missing)


def test_setup_ssl_certificates_pins_requests_bundle(tmp_path):
    """Vérifie que setup_ssl_certificates propage le bundle trouvé aux constantes requests."""
    bundle = tmp_path / "cacert.pem"
    bundle.write_bytes(BUNDLE_CONTENT)
    fakes = _make_fake_requests_modules("frozen/Contents/MacOS/certifi/cacert.pem")

    with (
        patch("ankiforge.utils.ssl_certificates.find_valid_ca_bundle", return_value=bundle),
        patch.dict(sys.modules, fakes),
        patch.dict(os.environ, {}, clear=False),
    ):
        os.environ.pop("SSL_CERT_FILE", None)
        res = setup_ssl_certificates()

    assert res == str(bundle)
    assert str(bundle) == fakes["requests.utils"].DEFAULT_CA_BUNDLE_PATH
    assert str(bundle) == fakes["requests.adapters"].DEFAULT_CA_BUNDLE_PATH
