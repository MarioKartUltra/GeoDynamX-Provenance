import pytest

import iso_schemas
from conftest import EXAMPLES, example
from gprv.assembly import assemble
from gprv.canon import canonical, sha256
from gprv.iso import export

PRODUCTS = ["fbm_recon.tif", "fbm_recon.png", "boem_roi.npz"]


def exported(name):
    blob = (EXAMPLES / f"{name}.gprv.jsonl").read_bytes()
    return export(blob, f"{name}.gprv.jsonl")


@pytest.mark.parametrize("name", PRODUCTS)
def test_export_matches_the_published_example(name):
    assert exported(name) + "\n" == (EXAMPLES / f"{name}.iso.xml").read_text()


def test_ids_are_prefixed_by_member_hash():
    xml = exported("fbm_recon.tif")
    parent = sha256((EXAMPLES / "fbm_roi.npz.gprv").read_bytes())[:12]
    assert f'id="r{parent}.p2"' in xml and 'id="p2"' not in xml


def test_resolved_parent_citation_becomes_a_source_step_link():
    parent = sha256((EXAMPLES / "fbm_roi.npz.gprv").read_bytes())[:12]
    assert f'<mrl:sourceStep xlink:href="#r{parent}.p2"/>' in exported("fbm_recon.tif")


def test_statement_is_the_sinks():
    xml = exported("fbm_recon.tif")
    assert "LastWave reconstruction of the forked fBm window" in xml
    assert "A 512x512 window of a synthetic fBm field" not in xml


def test_export_refuses_an_assembly_that_does_not_verify():
    blob = assemble([(EXAMPLES / n).read_bytes() for n in ("fbm_roi.npz.gprv", "fbm_recon.tif.gprv", "fbm_recon.png.gprv")])
    with pytest.raises(ValueError):
        export(blob, "x.gprv.jsonl")


def vendor_level_record():
    rec = example("fbm_roi.npz.gprv")
    rec["source"][0]["processedLevel"] = {"code": "L2A", "codeSpace": "example"}
    return rec


def test_processed_level_makes_the_source_an_le_source():
    xml = export(assemble([canonical(vendor_level_record())]), "x.gprv.jsonl")
    assert "<mrl:LE_Source id=" in xml and "<mrl:processedLevel>" in xml


needs_schemas = pytest.mark.skipif(not iso_schemas.available(), reason="ISO schema bundle not in .cache/iso-schemas")


def validate_or_skip(xml, version):
    try:
        return iso_schemas.errors(xml, version)
    except OSError as e:                     # GML/XLink not cached and no network
        pytest.skip(f"remote schemas unavailable: {e}")


@needs_schemas
@pytest.mark.parametrize("version", ["2.0", "1.0"])
@pytest.mark.parametrize("name", PRODUCTS)
def test_example_exports_are_schema_valid(name, version):
    assert validate_or_skip(exported(name), version) == []


@needs_schemas
@pytest.mark.parametrize("version", ["2.0", "1.0"])
def test_processed_level_export_is_schema_valid(version):
    xml = export(assemble([canonical(vendor_level_record())]), "x.gprv.jsonl")
    assert validate_or_skip(xml, version) == []


@needs_schemas
def test_the_validator_catches_a_misplaced_element():
    xml = exported("boem_roi.npz")
    bad = xml.replace("<mrl:description>", "<mrl:descriptio>", 1).replace("</mrl:description>", "</mrl:descriptio>", 1)
    assert validate_or_skip(bad, "2.0") != []


def test_a_single_record_export_cites_the_record_and_its_own_hash():
    data = (EXAMPLES / "boem_roi.npz.gprv").read_bytes()
    xml = export(data + b"\n", "boem_roi.npz.gprv", documented=sha256(data))
    assert f"<gco:CharacterString>{sha256(data)}</gco:CharacterString>" in xml
