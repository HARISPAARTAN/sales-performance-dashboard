"""The report theme is built from the kit's dark tokens (tools/pbi/build_theme.py) and keeps WCAG contrast on the
report surface: text at least 4.5:1, chart colours and status colours at least 3:1."""

import json

import pytest

import build_theme

pytestmark = pytest.mark.pbi


def luminance(hex_colour: str) -> float:
    channels = [int(hex_colour[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast(a: str, b: str) -> float:
    hi, lo = sorted((luminance(a), luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


@pytest.fixture(scope="module")
def theme() -> dict:
    return json.loads(build_theme.theme_path().read_text(encoding="utf-8-sig"))


@pytest.fixture(scope="module")
def tokens() -> dict[str, str]:
    return build_theme.dark_tokens((build_theme.ROOT / "web" / "kit" / "tokens.css").read_text(encoding="utf-8"))


def test_committed_theme_equals_a_fresh_build(theme, tokens):
    # content, not bytes: Desktop rewrites the file in its own layout when it saves the project
    assert theme == json.loads(build_theme.render(build_theme.build(tokens)))
    assert theme["name"] == build_theme.PROJECT["theme"]["name"]


def test_colours_come_from_the_kit_tokens(theme, tokens):
    assert theme["dataColors"] == [tokens[f"chart-{n}"] for n in range(1, 9)]
    assert (theme["background"], theme["secondaryBackground"]) == (tokens["surface"], tokens["surface-2"])
    assert (theme["good"], theme["neutral"], theme["bad"]) == (tokens["ok"], tokens["warn"], tokens["danger"])
    assert theme["foreground"] == tokens["text"] and theme["tableAccent"] == tokens["accent"]


@pytest.mark.parametrize("surface", ["background", "secondaryBackground"])
def test_text_contrast(theme, surface):
    for name, text_class in theme["textClasses"].items():
        assert contrast(text_class["color"], theme[surface]) >= 4.5, name
    assert contrast(theme["foreground"], theme[surface]) >= 4.5


def test_chart_and_status_colours_contrast(theme):
    for colour in [*theme["dataColors"], theme["good"], theme["neutral"], theme["bad"]]:
        assert contrast(colour, theme["background"]) >= 3, colour


def test_dark_tokens_reject_a_missing_token():
    with pytest.raises(ValueError, match="surface-2"):
        build_theme.dark_tokens(":root { --bg: #0B0F14; --surface: #121820; }")


def test_contrast_helper_matches_known_values():
    assert contrast("#FFFFFF", "#000000") == pytest.approx(21.0)
    assert contrast("#777777", "#FFFFFF") == pytest.approx(4.48, abs=0.01)
