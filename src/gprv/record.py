"""Records: write-once minting and the record checks of spec §9."""
import json
import re
from importlib.resources import files
from pathlib import Path

from .canon import CanonicalError, canonical, normalize, sha256

VERSIONS = {"0.1", "0.2"}

RECORD = {"gprv", "statement", "source", "processStep"}
SOURCE = {"id", "description", "sourceCitation", "sourceMetadata", "processedLevel", "scope"}
STEP = {"id", "description", "stepDateTime", "reference", "source", "processingInformation", "report", "output"}
PROCESSING = {"algorithm", "identifier", "softwareReference", "runTimeParameters"}
COMPONENT = {"id", "description", "citation"}
#: 0.2: a step and a component may say where their code came from (spec §6.1).
CODE_ORIGIN = {"kind", "source", "name", "version", "contentHash", "license", "citation", "editable"}
CONTENT_HASH = {"algorithm", "value", "covers"}
KINDS = {"repository", "package", "file", "archive", "service", "other"}
#: 0.2: how a step ran (spec §6.2).
EXECUTION_CONTEXT = {"precision", "backend", "fallback", "libraries", "platform", "thirdParty"}
BACKEND = {"name", "version", "planner", "binding"}
PRECISIONS = {"float32", "float64"}
BACKENDS = {"fftw", "mlx", "cuda", "numpy"}
THIRD_PARTY = {"component"}
COVERS = {"file", "directory", "distribution", "none"}
ALGORITHMS = {"sha256": 64, "sha1": 40}                   # name -> hex length of the value
CITATION = {"id", "title", "edition", "identifier", "otherCitationDetails", "onlineResource", "sha256"}
IDENTIFIER = {"code", "codeSpace"}
ONLINE = {"linkage"}
REPORT = {"name", "description"}
OUTPUT = {"id", "sourceCitation"}
SCOPE = {"level"}

XML_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]*$")       # xs:ID (an NCName), ASCII subset
HEX64 = re.compile(r"^[0-9a-f]{64}$")
UTC_INSTANT = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$")
URI = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:\S+$")         # a scheme and a non-empty rest
SPDX_ID = re.compile(r"^[A-Za-z0-9.+-]+$")


def spdx_ok(expr: str) -> bool:
    """Whether ``expr`` reads as an SPDX licence expression: ids joined by AND / OR / WITH, parentheses
    balanced, or the word NOASSERTION. The grammar, not the licence list, is what is checked."""
    if expr == "NOASSERTION":
        return True
    tokens = expr.replace("(", " ( ").replace(")", " ) ").split()
    if not tokens:
        return False
    depth, expect_id = 0, True
    for tok in tokens:
        if tok == "(":
            if not expect_id:
                return False
            depth += 1
        elif tok == ")":
            if expect_id or depth == 0:
                return False
            depth -= 1
        elif tok in ("AND", "OR", "WITH"):
            if expect_id:
                return False
            expect_id = True
        else:
            if not expect_id or not SPDX_ID.match(tok):
                return False
            expect_id = False
    return depth == 0 and not expect_id


def schema(version: str = "0.2") -> dict:
    """The record's JSON Schema for ``version`` (structure only; :func:`check` is the full test)."""
    if version not in VERSIONS:
        raise ValueError(f"unknown version {version!r}; known: {sorted(VERSIONS)}")
    return json.loads((files("gprv") / "schema" / f"gprv-{version}.schema.json").read_text())


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


COMMIT = re.compile(r"^[0-9a-f]{40}$")


def migrate(record: dict) -> dict:
    """A 0.2 copy of ``record`` (§6.1): each step whose ``softwareReference`` cites a repository URL and
    a full commit gains a ``codeOrigin`` of kind ``repository``; nothing else changes, nothing is
    derived that the citation does not carry, and a step that already has an origin keeps it."""
    import copy

    out = copy.deepcopy(record)
    citations = {}
    for st in out.get("processStep", []):
        for c in st.get("reference", []):
            if isinstance(c, dict) and "id" in c:
                citations[c["id"]] = c
        p = st.get("processingInformation") or {}
        sw = p.get("softwareReference")
        if isinstance(sw, dict) and "id" in sw:
            citations[sw["id"]] = sw
        if isinstance(sw, str):
            sw = citations.get(sw)
        if "codeOrigin" in st or not isinstance(sw, dict):
            continue
        commit = sw.get("edition", "")
        links = [r.get("linkage") for r in sw.get("onlineResource", []) if isinstance(r, dict)]
        if not (isinstance(commit, str) and COMMIT.match(commit) and links and isinstance(links[0], str)):
            continue
        st["codeOrigin"] = {"kind": "repository", "source": f"git+{links[0]}@{commit}",
                            "name": sw.get("title", links[0]), "version": commit,
                            "contentHash": {"algorithm": "sha256", "covers": "none"},
                            "license": "NOASSERTION", "editable": False}
    out["gprv"] = "0.2"
    return out


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
        self.origin_components = set()                    # components that carry a codeOrigin
        self.version = "0.1"

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
        elif "gprv" in rec:
            self.version = rec["gprv"]
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

    def keys_of(self, base: set) -> set:
        """The keys an object may carry in this record's version: ``codeOrigin`` from 0.2 on."""
        return base | {"codeOrigin"} if self.version != "0.1" else base

    def code_origin(self, o, where):
        """§6.1: where the code behind a step or a component came from."""
        if not self.obj(o, where, CODE_ORIGIN, ("kind", "source", "name", "contentHash", "license")):
            return
        if "kind" in o and o["kind"] not in KINDS:
            self.bad(f"{where}.kind", f"unknown kind {o['kind']!r}; known: {sorted(KINDS)}")
        if "source" in o and not (isinstance(o["source"], str) and URI.match(o["source"])):
            self.bad(f"{where}.source", "not a URI (a scheme, a colon and a location)")
        if "name" in o:
            self.string(o["name"], f"{where}.name")
        if "version" in o and o["version"] is not None and not isinstance(o["version"], str):
            self.bad(f"{where}.version", "expected a string or null")
        if "citation" in o:
            self.string(o["citation"], f"{where}.citation")
        if "editable" in o and not isinstance(o["editable"], bool):
            self.bad(f"{where}.editable", "expected true or false")
        if "license" in o and not (isinstance(o["license"], str) and spdx_ok(o["license"])):
            self.bad(f"{where}.license", "not an SPDX licence expression (or NOASSERTION)")
        if "contentHash" in o:
            self.content_hash(o["contentHash"], f"{where}.contentHash", o.get("kind"))

    def content_hash(self, h, where, kind):
        if not self.obj(h, where, CONTENT_HASH, ("algorithm", "covers")):
            return
        algorithm, covers = h.get("algorithm"), h.get("covers")
        if algorithm not in ALGORITHMS:
            self.bad(f"{where}.algorithm", f"unknown algorithm {algorithm!r}; known: {sorted(ALGORITHMS)}")
        if covers not in COVERS:
            self.bad(f"{where}.covers", f"unknown covers {covers!r}; known: {sorted(COVERS)}")
        if covers == "none":
            if "value" in h:
                self.bad(f"{where}.value", "a hash that covers nothing has no value")
            if kind not in ("service", "repository"):
                self.bad(f"{where}.covers", "only a service or a repository origin may cover nothing")
            return
        if "value" not in h:
            self.bad(where, "missing 'value'")
        elif algorithm in ALGORITHMS and not (isinstance(h["value"], str)
                                               and re.fullmatch(r"[0-9a-f]{%d}" % ALGORITHMS[algorithm], h["value"])):
            self.bad(f"{where}.value", f"not {ALGORITHMS[algorithm]} lowercase hex characters")

    def step(self, st, where, data, last):
        allowed = self.keys_of(STEP) | ({"executionContext"} if self.version != "0.1" else set())
        if not self.obj(st, where, allowed, ("id", "description")):
            return
        if "codeOrigin" in st:
            self.code_origin(st["codeOrigin"], f"{where}.codeOrigin")
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
        in_step = set()
        if "processingInformation" in st:
            in_step = self.processing(st["processingInformation"], f"{where}.processingInformation")
        if "executionContext" in st:
            self.execution_context(st["executionContext"], f"{where}.executionContext", in_step)
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

    def processing(self, p, where) -> set:
        """Checks ``p``; returns the ids of the components this step uses (defined or referenced)."""
        used = set()
        if not self.obj(p, where, PROCESSING, ("identifier",)):
            return used
        for i, a in enumerate(self.array(p.get("algorithm", []), f"{where}.algorithm")):
            aw = f"{where}.algorithm[{i}]"
            if isinstance(a, str):
                if a not in self.components:
                    self.bad(aw, f"reference {a!r} names no component defined earlier")
                used.add(a)
            elif self.obj(a, aw, self.keys_of(COMPONENT), ("id", "description", "citation")):
                self.define(a.get("id"), aw)
                if "codeOrigin" in a:
                    self.code_origin(a["codeOrigin"], f"{aw}.codeOrigin")
                    if isinstance(a.get("id"), str):
                        self.origin_components.add(a["id"])
                if isinstance(a.get("id"), str):
                    used.add(a["id"])
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
        return used

    def execution_context(self, c, where, in_step: set):
        """§6.2: the precision, backend, libraries and platform a step ran with, and the third-party
        components it ran (each a component of this step that carries a ``codeOrigin``)."""
        if not self.obj(c, where, EXECUTION_CONTEXT):
            return
        if not c:
            self.bad(where, "an empty execution context says nothing")
        if "precision" in c and c["precision"] not in PRECISIONS:
            self.bad(f"{where}.precision", f"unknown precision {c['precision']!r}; known: {sorted(PRECISIONS)}")
        if "backend" in c:
            b, bw = c["backend"], f"{where}.backend"
            if self.obj(b, bw, BACKEND, ("name",)):
                if "name" in b and b["name"] not in BACKENDS:
                    self.bad(f"{bw}.name", f"unknown backend {b['name']!r}; known: {sorted(BACKENDS)}")
                for k in ("version", "planner", "binding"):
                    if k in b and b[k] is not None and not isinstance(b[k], str):
                        self.bad(f"{bw}.{k}", "expected a string or null")
        for k in ("fallback", "platform"):
            if k in c:
                self.string(c[k], f"{where}.{k}")
        if "libraries" in c:
            libs = c["libraries"]
            if not isinstance(libs, dict):
                self.bad(f"{where}.libraries", "expected an object")
            else:
                for name in sorted(libs):
                    if libs[name] is not None and not isinstance(libs[name], str):
                        self.bad(f"{where}.libraries.{name}", "expected a version string or null")
        for i, t in enumerate(self.array(c.get("thirdParty", []), f"{where}.thirdParty")):
            tw = f"{where}.thirdParty[{i}]"
            if not self.obj(t, tw, THIRD_PARTY, ("component",)):
                continue
            ref = t.get("component")
            if ref not in in_step:
                self.bad(f"{tw}.component", f"{ref!r} names no component of this step")
            elif ref not in self.origin_components:
                self.bad(f"{tw}.component", f"component {ref!r} carries no codeOrigin")
