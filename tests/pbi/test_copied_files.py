"""tools/pbi/ keeps the files it copied unchanged from energiewende-monitor (commit c05c1fe) and the four schemas that
tools/pbi/vendor_schemas.py trims, byte for byte, as listed in tests/pbi/copied_files.sha256. The list has the format
of `sha256sum`, so `cd tools/pbi && sha256sum -c ../../tests/pbi/copied_files.sha256` checks the same thing. Updating a
template or a schema means updating its line in the same commit."""

import hashlib
from pathlib import Path

import pytest

pytestmark = pytest.mark.pbi
HERE = Path(__file__).resolve().parent
PBI = HERE.parents[1] / "tools" / "pbi"
LIST = HERE / "copied_files.sha256"
OWN = {"schemas/README.md", "templates/README.md", "templates/lineClusteredColumnComboChart.json"}


def entries() -> list[tuple[str, str]]:
    pairs = [line.split(maxsplit=1) for line in LIST.read_text(encoding="utf-8").splitlines() if line.strip()]
    return [(path.lstrip("*"), digest) for digest, path in pairs]


def test_the_list_covers_every_copied_file() -> None:
    listed = {path for path, _ in entries()}
    on_disk = {
        p.relative_to(PBI).as_posix()
        for folder in ("schemas", "templates")
        for p in (PBI / folder).rglob("*")
        if p.is_file()
    }
    assert len(listed) == 33
    assert on_disk - listed == OWN
    assert listed <= on_disk


@pytest.mark.parametrize(("path", "digest"), entries())
def test_copied_file_is_unchanged(path: str, digest: str) -> None:
    assert hashlib.sha256((PBI / path).read_bytes()).hexdigest() == digest
