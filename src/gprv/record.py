"""Records: write-once minting and the record checks of spec §9."""
import json
import re
from importlib.resources import files
from pathlib import Path

from .canon import CanonicalError, canonical, normalize, sha256

VERSIONS = {"0.1"}

RECORD = {"gprv", "statement", "source", "processStep"}
SOURCE = {"id", "description", "sourceCitation", "sourceMetadata", "processedLevel", "scope"}
STEP = {"id", "description", "stepDateTime", "reference", "source", "processingInformation", "report", "output"}
PROCESSING = {"algorithm", "identifier", "softwareReference", "runTimeParameters"}
COMPONENT = {"id", "description", "citation"}
CITATION = {"id", "title", "edition", "identifier", "otherCitationDetails", "onlineResource", "sha256"}
IDENTIFIER = {"code", "codeSpace"}
ONLINE = {"linkage"}
REPORT = {"name", "description"}
OUTPUT = {"id", "sourceCitation"}
SCOPE = {"level"}

XML_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]*$")       # xs:ID (an NCName), ASCII subset
HEX64 = re.compile(r"^[0-9a-f]{64}$")
UTC_INSTANT = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$")


def schema() -> dict:
    """The record's JSON Schema (structure only; :func:`check` is the full test)."""
    return json.loads((files("gprv") / "schema" / "gprv-0.1.schema.json").read_text())


class RecordError(ValueError):
    def __init__(self, problems):
        super().__init__("; ".join(problems))
        self.problems = problems


def write(path, record) -> str:
    """Mint ``record`` at ``path``: value rules, checks, canonical bytes, written once. Returns the record hash."""
    record = normalize(record)
    problems = check_obj(record)
    if problems:
        raise RecordError(problems)
    data = canonical(record)
    with open(Path(path), "xb") as f:                         # "x": a minted record is never overwritten
        f.write(data)
    return sha256(data)


def parse(data: bytes):
    """The record object in ``data``, refusing duplicate keys and the NaN/Infinity literals."""
    def pairs(items):
        keys = [k for k, _ in items]
        dup = {k for k in keys if keys.count(k) > 1}
        if dup:
            raise ValueError(f"duplicate key {sorted(dup)[0]!r}")
        return dict(items)

    def constant(name):
        raise ValueError(f"literal {name} is not JSON")

    return json.loads(data, object_pairs_hook=pairs, parse_constant=constant)


def check(data: bytes) -> list:
    """Problems with a record's bytes; an empty list means the record verifies."""
    try:
        rec = parse(data)
    except ValueError as e:
        return [f"not JSON: {e}"]
    try:
        if canonical(rec) != data:
            return ["bytes are not canonical (RFC 8785)"] + check_obj(rec)
    except CanonicalError as e:
        return [f"not canonical: {e}"]
    return check_obj(rec)


def check_obj(rec) -> list:
    """Problems with a parsed record (structure, ids, references, the print step)."""
    return _Checker().record(rec)


class _Checker:
    def __init__(self):
        self.problems, self.ids = [], set()
        self.components, self.citations = set(), set()

    def bad(self, where, msg):
        self.problems.append(f"{where}: {msg}" if where else msg)

    # ---- shapes ----
    def obj(self, x, where, allowed, required=()):
        if not isinstance(x, dict):
            self.bad(where, "expected an object")
            return False
        for k in sorted(set(x) - allowed):
            self.bad(where, f"unknown key {k!r}")
        for k in required:
            if k not in x:
                self.bad(where, f"missing {k!r}")
        return True

    def string(self, x, where):
        if not isinstance(x, str):
            self.bad(where, "expected a string")

    def array(self, x, where):
        if not isinstance(x, list):
            self.bad(where, "expected an array")
            return []
        return x

    def define(self, ident, where):
        if not isinstance(ident, str) or not XML_NAME.match(ident):
            self.bad(where, f"id {ident!r} is not an XML name")
        elif ident in self.ids:
            self.bad(where, f"duplicate id {ident!r}")
        else:
            self.ids.add(ident)

    def identifier(self, x, where):
        if self.obj(x, where, IDENTIFIER, ("code",)):
            for k in ("code", "codeSpace"):
                if k in x:
                    self.string(x[k], f"{where}.{k}")

    def citation(self, c, where, need_sha=False):
        if not self.obj(c, where, CITATION, ("title",)):
            return
        if "id" in c:
            self.define(c["id"], where)
            self.citations.add(c["id"])
        for k in ("title", "edition"):
            if k in c:
                self.string(c[k], f"{where}.{k}")
        for i, ident in enumerate(self.array(c.get("identifier", []), f"{where}.identifier")):
            self.identifier(ident, f"{where}.identifier[{i}]")
        for i, d in enumerate(self.array(c.get("otherCitationDetails", []), f"{where}.otherCitationDetails")):
            self.string(d, f"{where}.otherCitationDetails[{i}]")
        for i, r in enumerate(self.array(c.get("onlineResource", []), f"{where}.onlineResource")):
            if self.obj(r, f"{where}.onlineResource[{i}]", ONLINE, ("linkage",)):
                self.string(r["linkage"], f"{where}.onlineResource[{i}].linkage")
        if "sha256" in c:
            if not isinstance(c["sha256"], str) or not HEX64.match(c["sha256"]):
                self.bad(f"{where}.sha256", "not 64 lowercase hex characters")
        elif need_sha:
            self.bad(where, "missing 'sha256'")

    # ---- the record ----
    def record(self, rec):
        if not self.obj(rec, "", RECORD, ("gprv", "statement", "processStep")):
            return self.problems
        if "gprv" in rec and rec["gprv"] not in VERSIONS:
            self.bad("gprv", f"unknown version {rec['gprv']!r}")
        if "statement" in rec:
            self.string(rec["statement"], "statement")
        data = set()                                          # ids a step may read
        for i, s in enumerate(self.array(rec.get("source", []), "source")):
            self.source(s, f"source[{i}]")
            if isinstance(s, dict) and "id" in s:
                data.add(s["id"])
        steps = self.array(rec.get("processStep", []), "processStep")
        if not steps:
            self.bad("processStep", "a record needs at least one step (the print step)")
        for i, st in enumerate(steps):
            self.step(st, f"processStep[{i}]", data, last=(i == len(steps) - 1))
        return self.problems

    def source(self, s, where):
        if not self.obj(s, where, SOURCE, ("id", "description")):
            return
        self.define(s.get("id"), where)
        if "description" in s:
            self.string(s["description"], f"{where}.description")
        if "sourceCitation" in s:
            self.citation(s["sourceCitation"], f"{where}.sourceCitation")
        for i, m in enumerate(self.array(s.get("sourceMetadata", []), f"{where}.sourceMetadata")):
            self.citation(m, f"{where}.sourceMetadata[{i}]", need_sha=True)
        if "processedLevel" in s:
            self.identifier(s["processedLevel"], f"{where}.processedLevel")
        if "scope" in s and s["scope"] != {"level": "software"}:
            self.bad(f"{where}.scope", 'only {"level": "software"} is defined in 0.1')

    def step(self, st, where, data, last):
        if not self.obj(st, where, STEP, ("id", "description")):
            return
        self.define(st.get("id"), where)
        if "description" in st:
            self.string(st["description"], f"{where}.description")
        if last:
            if "stepDateTime" not in st:
                self.bad(where, "the print step (the last step) needs 'stepDateTime'")
        elif "stepDateTime" in st:
            self.bad(where, "only the print step (the last step) carries 'stepDateTime'")
        if "stepDateTime" in st and not (isinstance(st["stepDateTime"], str) and UTC_INSTANT.match(st["stepDateTime"])):
            self.bad(f"{where}.stepDateTime", "not an RFC 3339 UTC instant (YYYY-MM-DDThh:mm:ssZ)")
        for i, c in enumerate(self.array(st.get("reference", []), f"{where}.reference")):
            self.citation(c, f"{where}.reference[{i}]")
        for i, ref in enumerate(self.array(st.get("source", []), f"{where}.source")):
            if ref not in data:
                self.bad(f"{where}.source[{i}]", f"{ref!r} names no source and no output of an earlier step")
        if "processingInformation" in st:
            self.processing(st["processingInformation"], f"{where}.processingInformation")
        for i, r in enumerate(self.array(st.get("report", []), f"{where}.report")):
            if self.obj(r, f"{where}.report[{i}]", REPORT, ("name",)):
                if "name" in r:
                    self.string(r["name"], f"{where}.report[{i}].name")
                if "description" in r and not isinstance(r["description"], (str, dict)):
                    self.bad(f"{where}.report[{i}].description", "expected text or an object")
        outputs = self.array(st.get("output", []), f"{where}.output")
        if last and not outputs:
            self.bad(where, "the print step needs an output")
        for i, o in enumerate(outputs):
            ow = f"{where}.output[{i}]"
            if not self.obj(o, ow, OUTPUT, ("id",)):
                continue
            self.define(o.get("id"), ow)
            if "sourceCitation" in o:
                self.citation(o["sourceCitation"], f"{ow}.sourceCitation", need_sha=last)
            elif last:
                self.bad(ow, "the print step's output needs sourceCitation with 'sha256'")
        for o in outputs:                                     # readable by later steps only
            if isinstance(o, dict) and "id" in o:
                data.add(o["id"])

    def processing(self, p, where):
        if not self.obj(p, where, PROCESSING, ("identifier",)):
            return
        for i, a in enumerate(self.array(p.get("algorithm", []), f"{where}.algorithm")):
            aw = f"{where}.algorithm[{i}]"
            if isinstance(a, str):
                if a not in self.components:
                    self.bad(aw, f"reference {a!r} names no component defined earlier")
            elif self.obj(a, aw, COMPONENT, ("id", "description", "citation")):
                self.define(a.get("id"), aw)
                if "description" in a:
                    self.string(a["description"], f"{aw}.description")
                if "citation" in a:
                    self.citation(a["citation"], f"{aw}.citation")
                if "id" in a:
                    self.components.add(a["id"])
        if "identifier" in p:
            self.identifier(p["identifier"], f"{where}.identifier")
        sw = p.get("softwareReference")
        if isinstance(sw, str):
            if sw not in self.citations:
                self.bad(f"{where}.softwareReference", f"reference {sw!r} names no citation defined earlier")
        elif sw is not None:
            self.citation(sw, f"{where}.softwareReference")
        if "runTimeParameters" in p and not isinstance(p["runTimeParameters"], dict):
            self.bad(f"{where}.runTimeParameters", "expected an object")
