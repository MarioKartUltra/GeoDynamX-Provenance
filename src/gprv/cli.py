"""The gprv command: verify, show, assemble and export .gprv records."""
import argparse
import json
import sys
from pathlib import Path

from .assembly import assemble, collect, load_store, verify
from .canon import sha256
from .iso import export
from .record import check, parse


def plural(n, word):
    return f"{n} {word}" + ("" if n == 1 else "s")


def is_assembly(path: Path) -> bool:
    return path.name.endswith(".jsonl")


def file_checks(members, folder: Path):
    """Compare every cited file found in ``folder`` with its sha256: (files checked, problems)."""
    checked, problems = 0, []
    for rec in members.values():
        cites = []
        for s in rec.get("source", []):
            cites += [s.get("sourceCitation", {})] + s.get("sourceMetadata", [])
        for st in rec.get("processStep", []):
            cites += [o.get("sourceCitation", {}) for o in st.get("output", [])]
        for c in cites:
            if "sha256" not in c or "title" not in c or Path(c["title"]).name != c["title"]:
                continue
            f = folder / c["title"]
            if f.is_file():
                checked += 1
                if sha256(f.read_bytes()) != c["sha256"]:
                    problems.append(f"{c['title']}: sha256 differs from the cited {c['sha256'][:12]}")
    return checked, problems


def cmd_verify(args):
    failed = False
    for path in map(Path, args.files):
        data = path.read_bytes()
        if is_assembly(path):
            v = verify(data)
        else:
            problems = check(data)
            if problems:
                v = verify(data + b"\n")
            else:                                     # resolve ancestors kept beside the record
                members, _gaps = collect(data, load_store([path.parent]))
                v = verify(assemble(members))
        checked, mismatches = file_checks(v.members, path.parent)
        problems = v.problems + mismatches
        if problems:
            failed = True
            print(f"{path}: FAILED")
            for p in problems:
                print(f"  {p}")
            continue
        print(f"{path}: VERIFIED ({plural(len(v.members), 'member')}, {plural(len(v.gaps), 'gap')}, "
              f"{plural(checked, 'file')} checked)")
        for g in v.gaps:
            print(f"  gap: member {g.member[:12]} source {g.source!r} cites {g.cited[:12]}, not at hand")
    return 1 if failed else 0


def cmd_show(args):
    path = Path(args.file)
    data = path.read_bytes()
    lines = data.split(b"\n")[:-1] if is_assembly(path) else [data]
    for line in lines:
        if is_assembly(path):
            print(f"# member {sha256(line)}")
        print(json.dumps(parse(line), indent=2, ensure_ascii=False))
    return 0


def cmd_assemble(args):
    product = Path(args.product)
    data = product.read_bytes()
    problems = check(data)
    if problems:
        print(f"{product}: FAILED")
        for p in problems:
            print(f"  {p}")
        return 1
    store = load_store([product.parent] + [Path(d) for d in args.search])
    members, gaps = collect(data, store)
    blob = assemble(members)
    v = verify(blob)
    if not v.ok:
        print(f"{product}: the assembly does not verify")
        for p in v.problems:
            print(f"  {p}")
        return 1
    out = Path(args.output) if args.output else product.with_name(product.name + ".jsonl")
    out.write_bytes(blob)
    print(f"{out}: {plural(len(members), 'member')}, {plural(len(gaps), 'gap')}, sha256 {sha256(blob)}")
    for g in gaps:
        print(f"  gap: member {g.member[:12]} source {g.source!r} cites {g.cited[:12]}, not found")
    return 0


def cmd_export(args):
    path = Path(args.file)
    data = path.read_bytes()
    try:
        if is_assembly(path):
            xml = export(data, path.name)
        else:
            xml = export(data + b"\n", path.name, documented=sha256(data))
    except ValueError as e:
        print(f"{path}: {e}", file=sys.stderr)
        return 1
    if args.output:
        Path(args.output).write_text(xml + "\n")
    else:
        print(xml)
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="gprv", description="Verify, show, assemble and export .gprv records.")
    sub = ap.add_subparsers(dest="command", required=True)
    p = sub.add_parser("verify", help="check records (.gprv) or assemblies (.gprv.jsonl)")
    p.add_argument("files", nargs="+")
    p.set_defaults(func=cmd_verify)
    p = sub.add_parser("show", help="pretty-print a record or an assembly")
    p.add_argument("file")
    p.set_defaults(func=cmd_show)
    p = sub.add_parser("assemble", help="write a product's assembly from the records beside it")
    p.add_argument("product")
    p.add_argument("--search", action="append", default=[], metavar="DIR", help="another folder of records")
    p.add_argument("-o", "--output")
    p.set_defaults(func=cmd_assemble)
    p = sub.add_parser("export", help="ISO 19115-3 lineage XML of a record or an assembly")
    p.add_argument("file")
    p.add_argument("-o", "--output")
    p.set_defaults(func=cmd_export)
    args = ap.parse_args(argv)
    try:
        return args.func(args)
    except OSError as e:
        print(f"gprv: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
