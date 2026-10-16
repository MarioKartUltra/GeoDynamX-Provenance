"""Build the example records, assemblies and ISO exports from src/*.json with the gprv library.

Usage: python build.py OUT_DIR   (records are minted once, so OUT_DIR must not already hold them)"""
import json
import sys
from pathlib import Path

import gprv

HERE = Path(__file__).resolve().parent
RECORDS = {"fbm_roi.npz": None, "fbm_recon.tif": "fbm_roi.npz", "fbm_recon.png": "fbm_roi.npz", "boem_roi.npz": None,
           "code_origin.npz": None, "exec_context.tif": "fbm_roi.npz"}
PRODUCTS = ["fbm_recon.tif", "fbm_recon.png", "boem_roi.npz", "code_origin.npz", "exec_context.tif"]


def build(out: Path):
    hashes = {}
    for name, parent in RECORDS.items():                  # parents first: children cite their hash
        text = (HERE / "src" / f"{name}.json").read_text()
        if parent:
            text = text.replace("PARENT_HASH", hashes[parent])
        hashes[name] = gprv.write(out / f"{name}.gprv", json.loads(text))
    for name in PRODUCTS:
        members, _gaps = gprv.collect((out / f"{name}.gprv").read_bytes(), gprv.load_store([out]))
        blob = gprv.assemble(members)
        (out / f"{name}.gprv.jsonl").write_bytes(blob)
        (out / f"{name}.iso.xml").write_text(gprv.export(blob, f"{name}.gprv.jsonl") + "\n")
    return hashes


if __name__ == "__main__":
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    for name, h in build(out).items():
        print(f"{name}.gprv {h}")
