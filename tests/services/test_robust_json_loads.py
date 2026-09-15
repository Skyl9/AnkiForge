r"""
Tests unitaires pour robust_json_loads afin de garantir le support parfait
des formules LaTeX (anti-slashs simples non échappés \Sigma, \delta, \frac, \beta, \text, \[, \], etc.).
"""

from __future__ import annotations

from ankiforge.services.ai.consultant_engine import robust_json_loads


def test_robust_json_loads_standard_json():
    raw = '{"Front": "Question simple", "Back": "Réponse simple"}'
    res = robust_json_loads(raw)
    assert res["Front"] == "Question simple"
    assert res["Back"] == "Réponse simple"


def test_robust_json_loads_latex_single_backslashes():
    # Chaîne brute avec anti-slashs simples (\Sigma, \delta, \frac)
    raw = r'{"Front": "Formule : \Sigma_{i=1}^n x_i", "Back": "$\delta = \frac{a}{b}$"}'
    res = robust_json_loads(raw)
    assert r"\Sigma" in res["Front"]
    assert r"\delta" in res["Back"]
    assert r"\frac" in res["Back"]


def test_robust_json_loads_latex_math_delimiters():
    # Délimiteurs LaTeX \[ ... \] et \( ... \)
    raw = r'{"Front": "Équation : \[ E = mc^2 \]", "Back": "On a \( a + b = c \)"}'
    res = robust_json_loads(raw)
    assert r"\[" in res["Front"]
    assert r"\(" in res["Back"]


def test_robust_json_loads_latex_greek_and_formatting():
    raw = r'{"Front": "\textbf{Théorème} : \alpha + \beta = \gamma", "Back": "\text{Résultat : } \theta \cdot \rho"}'
    res = robust_json_loads(raw)
    assert r"\textbf" in res["Front"]
    assert r"\alpha" in res["Front"]
    assert r"\text" in res["Back"]


def test_robust_json_loads_split_cards_list():
    raw = r'[{"Front": "\Sigma_1", "Back": "\delta_1"}, {"Front": "\frac{1}{2}", "Back": "\sqrt{2}"}]'
    res = robust_json_loads(raw)
    assert isinstance(res, list)
    assert len(res) == 2
    assert res[0]["Front"] == r"\Sigma_1"
    assert res[1]["Back"] == r"\sqrt{2}"
