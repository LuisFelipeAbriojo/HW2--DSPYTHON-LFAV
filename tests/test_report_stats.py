import pytest

from src.report_stats import _dept_key, _fmt, _fmt_int, _macro, _ordinal, _title_es


def test_dept_key_strips_accents_and_spaces_for_a_valid_latex_macro_name():
    assert _dept_key("Lambayeque") == "Lambayeque"
    assert _dept_key("San Martín") == "SanMartin"


def test_fmt_int_uses_latex_braced_thousands_separator():
    assert _fmt_int(3631) == "3{,}631"
    assert _fmt_int(999) == "999"


def test_fmt_rounds_to_requested_decimals():
    assert _fmt(15.401619687767605) == "15.4"
    assert _fmt(0.669476, 3) == "0.669"


def test_ordinal_spells_out_digits_latex_macro_names_cannot_contain():
    assert _ordinal(1) == "First"
    assert _ordinal(3) == "Third"
    assert not any(c.isdigit() for c in _ordinal(3))


def test_ordinal_raises_instead_of_emitting_a_digit_bearing_name():
    with pytest.raises(ValueError):
        _ordinal(99)


def test_title_es_keeps_spanish_connector_words_lowercase():
    assert _title_es("CALIDAD Y SALUD") == "Calidad y Salud"
    assert _title_es("PAUCARTAMBO") == "Paucartambo"


def test_macro_emits_a_valid_newcommand_line():
    assert _macro("statGini", "0.669") == "\\newcommand{\\statGini}{0.669}\n"
