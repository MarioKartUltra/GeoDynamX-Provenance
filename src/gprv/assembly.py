"""Assemblies (spec §8): a product's record and its ancestors as JSON Lines, sorted by member hash."""
from collections import namedtuple
from dataclasses import dataclass, field
from pathlib import Path

from .canon import sha256
from .record import check, parse

Gap = namedtuple("Gap", "member source cited")      # a parent citation that resolves to no member


@dataclass
class Verification:
    members: dict = field(default_factory=dict)      # member hash -> parsed record
    sink: str | None = None
    gaps: list = field(default_factory=list)
    problems: list = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems


def citations(rec):
    """(source id, dataset sha256 read, parent record sha256) for every parent citation in ``rec``."""
    for s in rec.get("source", []):
        for m in s.get("sourceMetadata", []):
            if "sha256" in m:
                yield s.get("id"), s.get("sourceCitation", {}).get("sha256"), m["sha256"]


def producers(rec) -> dict:
    """Dataset sha256 -> id of the step in ``rec`` that output it."""
    return {o["sourceCitation"]["sha256"]: st["id"]
            for st in rec.get("processStep", []) for o in st.get("output", [])
            if "sha256" in o.get("sourceCitation", {})}


def assemble(records) -> bytes:
    """The assembly of the given record byte strings: each once, sorted by hash, one per line."""
    unique = {sha256(r): r for r in records}
    return b"".join(unique[h] + b"\n" for h in sorted(unique))


def collect(sink: bytes, store) -> tuple:
    """The product record ``sink`` and every ancestor it cites that ``store`` (hash -> bytes) holds,
    plus the citations it could not resolve."""
    members, gaps, seen, todo = [sink], [], {sha256(sink)}, [sink]
    while todo:
        data = todo.pop()
        for src, _dataset, cited in citations(parse(data)):
            if cited in seen:
                continue
            if cited in store:
                seen.add(cited)
                members.append(store[cited])
                todo.append(store[cited])
            else:
                gaps.append(Gap(sha256(data), src, cited))
    return members, gaps


def load_store(dirs) -> dict:
    """Every ``*.gprv`` record in ``dirs``, keyed by its hash."""
    store = {}
    for d in dirs:
        for p in sorted(Path(d).glob("*.gprv")):
            data = p.read_bytes()
            store[sha256(data)] = data
    return store


def verify(blob: bytes) -> Verification:
    v = Verification()
    if not blob.endswith(b"\n"):
        v.problems.append("the last line lacks its LF")
    lines = blob.split(b"\n")
    if lines[-1] == b"":
        lines.pop()
    if not lines:
        v.problems.append("no members")
        return v
    hashes = [sha256(line) for line in lines]
    if hashes != sorted(set(hashes)):
        v.problems.append("lines are not sorted by sha256, or a member repeats")
    for h, line in zip(hashes, lines):
        v.problems += [f"member {h[:12]}: {p}" for p in check(line)]
        try:
            v.members[h] = parse(line)
        except ValueError:
            pass
    cited = set()
    for h, rec in v.members.items():
        for src, dataset, parent in citations(rec):
            cited.add(parent)
            if parent not in v.members:
                v.gaps.append(Gap(h, src, parent))
            elif dataset not in producers(v.members[parent]):
                v.problems.append(f"member {h[:12]} source {src!r} reads {str(dataset)[:12]}, "
                                  f"which record {parent[:12]} did not output")
    sinks = [h for h in v.members if h not in cited]
    if len(sinks) == 1:
        v.sink = sinks[0]
    else:
        v.problems.append(f"{len(sinks)} sinks: exactly one member must be cited by no other")
    return v
