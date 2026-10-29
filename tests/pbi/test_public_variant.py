import json
from pathlib import Path

import pytest

import make_public_variant
from pbir import PROJECT

pytestmark = pytest.mark.pbi
SRC = Path(__file__).resolve().parents[2] / PROJECT["folder"] / f"{PROJECT['name']}.pbip"
BASE = PROJECT["name"]
NAME = BASE + PROJECT["public_variant"]["suffix"]


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    out = tmp_path_factory.mktemp("public")
    return out, make_public_variant.build(SRC, out)


def test_artefacts_are_renamed(built):
    out, pbip = built
    assert pbip == out / f"{NAME}.pbip"
    assert (out / f"{NAME}.SemanticModel" / "definition.pbism").is_file()
    assert (out / f"{NAME}.Report" / "definition.pbir").is_file()
    assert not (out / f"{BASE}.pbip").exists()
    assert "no row-level security" in (out / "README.txt").read_text(encoding="utf-8")


def test_no_role_and_no_security_table_left(built):
    out, _ = built
    model = out / f"{NAME}.SemanticModel" / "definition"
    assert not (model / "roles").exists()
    assert not (model / "tables" / "Security.tmdl").exists()
    text = (model / "model.tmdl").read_text(encoding="utf-8")
    assert "ref role" not in text and "ref table Security" not in text and '"Security"' not in text
    assert not any("USERPRINCIPALNAME" in p.read_text(encoding="utf-8") for p in model.rglob("*.tmdl"))


def test_pbip_and_pbir_point_at_the_renamed_folders(built):
    out, pbip = built
    artifacts = json.loads(pbip.read_text(encoding="utf-8"))["artifacts"]
    assert artifacts == [{"report": {"path": f"{NAME}.Report"}}]
    pbir = json.loads((out / f"{NAME}.Report" / "definition.pbir").read_text(encoding="utf-8"))
    target = pbir["datasetReference"]["byPath"]["path"]
    assert target == f"../{NAME}.SemanticModel"
    assert ((out / f"{NAME}.Report") / target).resolve().is_dir()


def test_other_tables_and_the_report_are_byte_identical(built):
    out, _ = built
    src_model = SRC.parent / f"{BASE}.SemanticModel" / "definition"
    dst_model = out / f"{NAME}.SemanticModel" / "definition"
    kept = sorted(p.name for p in (src_model / "tables").glob("*.tmdl") if p.stem != "Security")
    assert sorted(p.name for p in (dst_model / "tables").glob("*.tmdl")) == kept
    for name in kept:
        assert (dst_model / "tables" / name).read_bytes() == (src_model / "tables" / name).read_bytes(), name
    for name in ("relationships.tmdl", "database.tmdl", "expressions.tmdl"):
        assert (dst_model / name).read_bytes() == (src_model / name).read_bytes(), name
    src_report = SRC.parent / f"{BASE}.Report" / "definition"
    for src in src_report.rglob("*.json"):
        dst = out / f"{NAME}.Report" / "definition" / src.relative_to(src_report)
        assert dst.read_bytes() == src.read_bytes(), src.name


def test_model_tmdl_differs_only_by_role_security_and_query_order(built):
    out, _ = built
    src = (SRC.parent / f"{BASE}.SemanticModel" / "definition" / "model.tmdl").read_text(encoding="utf-8")
    dst = (out / f"{NAME}.SemanticModel" / "definition" / "model.tmdl").read_text(encoding="utf-8")
    expected = [
        ln.replace('"Security",', "")
        for ln in src.splitlines()
        if not ln.startswith("ref role") and ln != "ref table Security"
    ]
    assert dst.splitlines() == expected


def test_build_twice_into_the_same_folder(built):
    out, _ = built
    again = make_public_variant.build(SRC, out)
    assert again.is_file()
