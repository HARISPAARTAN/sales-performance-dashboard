"""Every generated page carries the project's annotation, so build_report keeps replacing it on the next run."""

import json
from pathlib import Path

import pytest

from pbir import PROJECT

pytestmark = pytest.mark.pbi

PAGES = Path(__file__).resolve().parents[2] / PROJECT["folder"] / f"{PROJECT['name']}.Report" / "definition" / "pages"


@pytest.mark.parametrize("page", sorted(p.name for p in PAGES.iterdir() if p.is_dir()))
def test_page_is_marked_as_generated(page):
    data = json.loads((PAGES / page / "page.json").read_text(encoding="utf-8"))
    names = [a["name"] for a in data.get("annotations", [])]
    assert PROJECT["generated"] in names
