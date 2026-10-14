import shutil

import pytest

from conftest import EXAMPLES
from gprv.cli import main


def stage(tmp_path, *names):
    for n in names:
        shutil.copy(EXAMPLES / n, tmp_path / n)
    return tmp_path


def run(capsys, *argv):
    code = main([str(a) for a in argv])
    return code, capsys.readouterr().out


def test_verify_a_record_with_its_parent_beside_it(tmp_path, capsys):
    d = stage(tmp_path, "fbm_roi.npz.gprv", "fbm_recon.tif.gprv")
    code, out = run(capsys, "verify", d / "fbm_recon.tif.gprv")
    assert code == 0 and "VERIFIED" in out


def test_verify_a_record_alone_lists_its_parent_as_a_gap(tmp_path, capsys):
    d = stage(tmp_path, "fbm_recon.tif.gprv")
    code, out = run(capsys, "verify", d / "fbm_recon.tif.gprv")
    assert code == 0 and "VERIFIED" in out and "1 gap" in out


def test_verify_an_edited_record_fails(tmp_path, capsys):
    p = tmp_path / "x.gprv"
    p.write_bytes((EXAMPLES / "fbm_roi.npz.gprv").read_bytes().replace(b'"gprv":"0.1"', b'"gprv": "0.1"'))
    code, out = run(capsys, "verify", p)
    assert code == 1 and "FAILED" in out and "not canonical" in out


def test_verify_an_assembly(capsys):
    code, out = run(capsys, "verify", EXAMPLES / "fbm_recon.tif.gprv.jsonl")
    assert code == 0 and "VERIFIED" in out


def test_verify_checks_cited_files_found_beside_the_record(tmp_path, capsys):
    d = stage(tmp_path, "fbm_roi.npz.gprv")
    (d / "fbm_roi.npz").write_bytes(b"stand-in fbm_roi.npz")          # the stand-in hash of the example
    code, out = run(capsys, "verify", d / "fbm_roi.npz.gprv")
    assert code == 0 and "1 file checked" in out
    (d / "fbm_roi.npz").write_bytes(b"something else")
    code, out = run(capsys, "verify", d / "fbm_roi.npz.gprv")
    assert code == 1 and "fbm_roi.npz" in out and "sha256" in out


def test_assemble_collects_the_product_branch(tmp_path, capsys):
    d = stage(tmp_path, "fbm_roi.npz.gprv", "fbm_recon.tif.gprv", "fbm_recon.png.gprv")
    code, out = run(capsys, "assemble", d / "fbm_recon.tif.gprv")
    assert code == 0 and "2 members" in out
    assert (d / "fbm_recon.tif.gprv.jsonl").read_bytes() == (EXAMPLES / "fbm_recon.tif.gprv.jsonl").read_bytes()


def test_assemble_searches_other_directories(tmp_path, capsys):
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir(), b.mkdir()
    stage(a, "fbm_recon.tif.gprv"), stage(b, "fbm_roi.npz.gprv")
    code, out = run(capsys, "assemble", a / "fbm_recon.tif.gprv", "--search", b, "-o", tmp_path / "out.jsonl")
    assert code == 0 and (tmp_path / "out.jsonl").read_bytes() == (EXAMPLES / "fbm_recon.tif.gprv.jsonl").read_bytes()


def test_assemble_reports_a_missing_ancestor(tmp_path, capsys):
    d = stage(tmp_path, "fbm_recon.tif.gprv")
    code, out = run(capsys, "assemble", d / "fbm_recon.tif.gprv")
    assert code == 0 and "1 gap" in out


def test_export_an_assembly_to_a_file(tmp_path, capsys):
    out_file = tmp_path / "x.xml"
    code, _ = run(capsys, "export", EXAMPLES / "fbm_recon.tif.gprv.jsonl", "-o", out_file)
    assert code == 0 and out_file.read_text() == (EXAMPLES / "fbm_recon.tif.iso.xml").read_text()


def test_export_a_record_to_stdout(capsys):
    code, out = run(capsys, "export", EXAMPLES / "boem_roi.npz.gprv")
    assert code == 0 and out.startswith("<mrl:LI_Lineage") and "Advocate and Hood" in out


def test_export_refuses_what_does_not_verify(tmp_path, capsys):
    p = tmp_path / "x.gprv"
    p.write_bytes(b"{}")
    code, _ = run(capsys, "export", p)
    assert code == 1


def test_show_pretty_prints(capsys):
    code, out = run(capsys, "show", EXAMPLES / "fbm_roi.npz.gprv")
    assert code == 0 and '"statement": "A 512x512 window' in out
