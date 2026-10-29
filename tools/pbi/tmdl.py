"""Minimal TMDL reader for linting: tables, columns, measures, hierarchies, partitions, calculation groups,
shared expressions, relationships and roles. It reads the dialect TmdlSerializer writes (tabs, `///`
descriptions, child objects after properties) and is not a full parser: tests/pbi/test_tmdl_tom.py parses
with Microsoft's own."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

PROPERTY = re.compile(
    r"^\s*(formatStringDefinition|formatString|description|lineageTag|displayFolder|annotation|isHidden|changedProperty"
    r"|extendedProperty|ordinal|detailRowsDefinition)\b"
)
DECLARATION = re.compile(
    r"(?:measure|column|table|calculationItem|expression|role|hierarchy)\s+('(?:[^']|'')+'|[^\s=]+)"
)


@dataclass
class Column:
    name: str
    data_type: str | None = None
    is_hidden: bool = False
    is_key: bool = False
    format_string: str | None = None
    summarize_by: str | None = None
    sort_by_column: str | None = None
    expression: str | None = None  # DAX of a calculated column; None for a column read from the source
    description: str | None = None  # the /// lines above the declaration
    source_column: str | None = None
    annotations: dict[str, str] = field(default_factory=dict)


@dataclass
class Measure:
    name: str
    expression: str
    format_string: str | None = None
    description: str | None = None
    display_folder: str | None = None
    format_string_definition: str | None = None  # DAX of a dynamic format string
    is_hidden: bool = False


@dataclass
class CalculationItem:
    name: str
    expression: str
    format_string_definition: str | None = None
    description: str | None = None


@dataclass
class CalculationGroup:
    precedence: int | None
    items: list[CalculationItem] = field(default_factory=list)


@dataclass
class Table:
    name: str
    columns: dict[str, Column] = field(default_factory=dict)
    measures: dict[str, Measure] = field(default_factory=dict)
    data_category: str | None = None
    is_hidden: bool = False
    description: str | None = None
    partition_kind: str | None = None  # m, calculated, or None (a calculation group has no partition in TMDL)
    partition_source: str | None = None
    hierarchies: dict[str, list[str]] = field(default_factory=dict)  # hierarchy name -> level column names
    calculation_group: CalculationGroup | None = None
    raw: str | None = None


@dataclass
class Expression:
    name: str
    expression: str
    description: str | None = None
    annotations: dict[str, str] = field(default_factory=dict)


@dataclass
class Relationship:
    name: str
    from_column: str  # "Table.Column", both parts unquoted
    to_column: str
    cross_filtering_behavior: str | None = None
    is_active: bool = True


@dataclass
class Role:
    name: str
    model_permission: str | None = None
    table_permissions: dict[str, str] = field(default_factory=dict)
    description: str | None = None


@dataclass
class Model:
    tables: dict[str, Table]
    relationships: list[Relationship]
    roles: list[Role]
    culture: str | None = None
    discourage_implicit_measures: bool = False
    expressions: dict[str, Expression] = field(default_factory=dict)
    annotations: dict[str, str] = field(default_factory=dict)
    compatibility_level: int | None = None


def unquote(name: str) -> str:
    name = name.strip()
    return name[1:-1].replace("''", "'") if name.startswith("'") and name.endswith("'") else name


def _qualified(ref: str | None) -> str:
    """`Table.'Column name'` or `'Table name'.'Column name'` -> `Table.Column name` (names unquoted)."""
    m = re.fullmatch(r"\s*('(?:[^']|'')+'|[^.\s']+)\.('(?:[^']|'')+'|[^.\s']+)\s*", ref or "")
    return f"{unquote(m.group(1))}.{unquote(m.group(2))}" if m else (ref or "")


def _descriptions(text: str) -> dict[tuple[str, str], str]:
    """Map (kind, name) to the /// description on the lines directly above the declaration."""
    out: dict[tuple[str, str], str] = {}
    pending: list[str] = []
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("///"):
            pending.append(s[3:].strip())
            continue
        if pending:
            m = DECLARATION.match(s)
            if m:
                out[(s.split()[0], unquote(m.group(1)))] = " ".join(pending)
        pending = []
    return out


def _blocks(text: str, keyword: str):
    """Yield (name, expression_on_first_line, body_lines) for `keyword name` blocks; body lines lose the
    block's indent plus one tab, so the block's own properties start at column 0."""
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.lstrip("\t")
        indent = len(line) - len(stripped)
        if stripped == keyword or stripped.startswith(keyword + " ") or stripped.startswith(keyword + "\t"):
            head = stripped[len(keyword) :].strip()
            # `name = expr`, or `name =` with the expression on the next lines
            m = re.match(r"(.*?)\s=(?:\s(.*)|$)", head)
            name, expr_first = (m.group(1), m.group(2)) if m else (head, None)
            body = []
            j = i + 1
            while j < len(lines) and (lines[j].strip() == "" or (len(lines[j]) - len(lines[j].lstrip("\t"))) > indent):
                body.append(lines[j][indent + 1 :] if lines[j].strip() else "")
                j += 1
            yield unquote(name), expr_first, body
            i = j
        else:
            i += 1


def _prop(body: list[str], key: str) -> str | None:
    """A property of the object itself: only lines at the body's first indent level (nested objects
    are skipped)."""
    for line in body:
        if line.startswith("\t"):
            continue
        s = line.strip()
        if s.startswith(key + ":"):
            return s.split(":", 1)[1].strip()
        if s == key:
            return "true"
    return None


def _expression_prop(body: list[str], key: str) -> str | None:
    """An expression property (`key = <expression>`), on its line or on the deeper-indented lines below it."""
    for n, line in enumerate(body):
        if line.startswith("\t") or not line.strip().startswith(key + " ="):
            continue
        rest = line.split("=", 1)[1].strip()
        if rest:
            return rest
        out = []
        for following in body[n + 1 :]:
            if following.strip() and not following.startswith("\t"):
                break
            if following.strip():
                out.append(following.strip())
        return "\n".join(out)
    return None


def _annotations(body: list[str]) -> dict[str, str]:
    """The object's own annotations (first indent level only), value as written."""
    found = (re.match(r"annotation (\S+?) = (.*)$", line.strip()) for line in body if not line.startswith("\t"))
    return {m.group(1): m.group(2).strip() for m in found if m}


def _leading_expression(first: str | None, body: list[str]) -> str:
    """The expression of a measure or calculation item: on the declaration line or on the lines below it up to
    the first property."""
    if first is not None and first.strip():
        return first.strip()
    out = []
    for line in body:
        if line.strip() == "":
            continue
        if PROPERTY.match(line) and not line.startswith("\t"):
            break
        out.append(line.strip())
    return "\n".join(out)


def _column_expression(first: str | None, body: list[str]) -> str | None:
    """DAX of a calculated column, on its declaration line or the deeper lines below it; None for a source
    column."""
    if first is not None and first.strip():
        return first.strip()
    out = []
    for line in body:
        if line.strip() and not line.startswith("\t"):
            break
        if line.strip():
            out.append(line.strip())
    return "\n".join(out) or None


def _table(name: str, body: list[str], text: str, descs: dict[tuple[str, str], str]) -> Table:
    t = Table(
        name,
        raw=text,
        data_category=_prop(body, "dataCategory"),
        is_hidden=_prop(body, "isHidden") == "true",
        description=descs.get(("table", name)),
    )
    inner = "\n".join(body)
    for cname, cfirst, cbody in _blocks(inner, "column"):
        t.columns[cname] = Column(
            cname,
            _prop(cbody, "dataType"),
            _prop(cbody, "isHidden") == "true",
            _prop(cbody, "isKey") == "true",
            _prop(cbody, "formatString"),
            _prop(cbody, "summarizeBy"),
            unquote(_prop(cbody, "sortByColumn") or "") or None,
            _column_expression(cfirst, cbody),
            descs.get(("column", cname)),
            _prop(cbody, "sourceColumn"),
            _annotations(cbody),
        )
    for hname, _hfirst, hbody in _blocks(inner, "hierarchy"):
        t.hierarchies[hname] = [
            unquote(_prop(lbody, "column") or "") for _n, _f, lbody in _blocks("\n".join(hbody), "level")
        ]
    for mname, mfirst, mbody in _blocks(inner, "measure"):
        t.measures[mname] = Measure(
            mname,
            _leading_expression(mfirst, mbody),
            _prop(mbody, "formatString"),
            descs.get(("measure", mname)),
            _prop(mbody, "displayFolder"),
            _expression_prop(mbody, "formatStringDefinition"),
            _prop(mbody, "isHidden") == "true",
        )
    for gname, _gfirst, gbody in _blocks(inner, "calculationGroup"):
        del gname
        precedence = _prop(gbody, "precedence")
        group = CalculationGroup(int(precedence) if precedence else None)
        for iname, ifirst, ibody in _blocks("\n".join(gbody), "calculationItem"):
            group.items.append(
                CalculationItem(
                    iname,
                    _leading_expression(ifirst, ibody),
                    _expression_prop(ibody, "formatStringDefinition"),
                    descs.get(("calculationItem", iname)),
                )
            )
        t.calculation_group = group
    for _pname, pfirst, pbody in _blocks(inner, "partition"):
        t.partition_kind = (pfirst or "").strip() or None
        t.partition_source = _expression_prop(pbody, "source")
    return t


def load_model(definition_dir: Path) -> Model:
    root = Path(definition_dir)
    tables = {}
    for path in sorted((root / "tables").glob("*.tmdl")):
        text = path.read_text(encoding="utf-8")
        descs = _descriptions(text)
        for tname, _first, tbody in _blocks(text, "table"):
            tables[tname] = _table(tname, tbody, text, descs)
    rels = []
    rel_path = root / "relationships.tmdl"
    if rel_path.exists():
        for rname, _first, rbody in _blocks(rel_path.read_text(encoding="utf-8"), "relationship"):
            rels.append(
                Relationship(
                    rname,
                    _qualified(_prop(rbody, "fromColumn")),
                    _qualified(_prop(rbody, "toColumn")),
                    _prop(rbody, "crossFilteringBehavior"),
                    _prop(rbody, "isActive") != "false",
                )
            )
    roles = []
    for path in sorted((root / "roles").glob("*.tmdl")) if (root / "roles").exists() else []:
        text = path.read_text(encoding="utf-8")
        descs = _descriptions(text)
        for rname, _first, rbody in _blocks(text, "role"):
            role = Role(rname, _prop(rbody, "modelPermission"), description=descs.get(("role", rname)))
            for line in rbody:
                m = re.match(r"\s*tablePermission\s+('(?:[^']|'')+'|[^\s=]+)\s*=\s*(.+)$", line)
                if m:
                    role.table_permissions[unquote(m.group(1))] = m.group(2).strip()
            roles.append(role)
    expressions = {}
    expr_path = root / "expressions.tmdl"
    if expr_path.exists():
        text = expr_path.read_text(encoding="utf-8")
        descs = _descriptions(text)
        for ename, efirst, ebody in _blocks(text, "expression"):
            expressions[ename] = Expression(
                ename,
                _leading_expression(efirst, ebody),
                descs.get(("expression", ename)),
                _annotations(ebody),
            )
    model_path = root / "model.tmdl"
    model_text = model_path.read_text(encoding="utf-8") if model_path.exists() else ""
    model_body = next((body for _n, _e, body in _blocks(model_text, "model")), [])
    annotations = {
        m.group(1): m.group(2).strip() for m in re.finditer(r"^annotation (\S+?) = (.*)$", model_text, flags=re.M)
    }
    database = (root / "database.tmdl").read_text(encoding="utf-8") if (root / "database.tmdl").exists() else ""
    level = re.search(r"compatibilityLevel:\s*(\d+)", database)
    return Model(
        tables,
        rels,
        roles,
        _prop(model_body, "culture"),
        _prop(model_body, "discourageImplicitMeasures") == "true",
        expressions,
        annotations,
        int(level.group(1)) if level else None,
    )
