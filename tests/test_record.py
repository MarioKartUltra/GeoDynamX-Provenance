import json
import math

import pytest

from conftest import EXAMPLES, example
from gprv.canon import canonical, sha256
from gprv.record import RecordError, check, check_obj, write


def problems_mention(problems, text):
    return any(text in p for p in problems)


@pytest.mark.parametrize("name", ["fbm_roi.npz.gprv", "fbm_recon.tif.gprv", "fbm_recon.png.gprv", "boem_roi.npz.gprv"])
def test_example_records_pass(name):
    assert check((EXAMPLES / name).read_bytes()) == []


def test_pretty_printed_bytes_are_not_canonical(child):
    assert problems_mention(check(json.dumps(child, indent=1).encode()), "not canonical")


def test_bytes_that_are_not_json_are_reported():
    assert problems_mention(check(b"{nope"), "not JSON")


def test_unknown_version_is_reported(child):
    child["gprv"] = "9.9"
    assert problems_mention(check_obj(child), "version")


def test_missing_statement_is_reported(child):
    del child["statement"]
    assert problems_mention(check_obj(child), "statement")


def test_a_record_needs_at_least_one_step(child):
    child["processStep"] = []
    assert problems_mention(check_obj(child), "processStep")


def test_step_without_description_is_reported(child):
    del child["processStep"][1]["description"]
    assert problems_mention(check_obj(child), "description")


def test_unknown_key_is_reported(child):
    child["processStep"][2]["view"] = {"dpi": 300}
    assert problems_mention(check_obj(child), "view")


def test_duplicate_id_is_reported(child):
    child["processStep"][0]["output"][0]["id"] = "s1"
    assert problems_mention(check_obj(child), "duplicate id 's1'")


def test_id_must_be_an_xml_name(child):
    child["processStep"][0]["id"] = "1p"
    assert problems_mention(check_obj(child), "'1p'")


def test_unresolved_component_reference_is_reported(child):
    child["processStep"][1]["processingInformation"]["algorithm"][0] = "nope"
    assert problems_mention(check_obj(child), "'nope'")


def test_component_referenced_before_its_definition_is_reported(child):
    algs = child["processStep"][1]["processingInformation"]["algorithm"]   # ["lw_bank", {lw_proj}, {w2}, {stop}]
    algs[0] = "lw_proj"                                                    # referenced before its definition
    assert problems_mention(check_obj(child), "'lw_proj'")


def test_unresolved_software_reference_is_reported(child):
    child["processStep"][1]["processingInformation"]["softwareReference"] = "nope"
    assert problems_mention(check_obj(child), "'nope'")


def test_step_reading_a_later_output_is_reported(child):
    child["processStep"][1]["source"] = ["d2"]          # d2 is p2's own output
    assert problems_mention(check_obj(child), "'d2'")


def test_last_step_needs_step_date_time(child):
    del child["processStep"][-1]["stepDateTime"]
    assert problems_mention(check_obj(child), "stepDateTime")


def test_only_the_print_step_carries_step_date_time(child):
    child["processStep"][0]["stepDateTime"] = "2026-10-01T16:00:00Z"
    assert problems_mention(check_obj(child), "stepDateTime")


def test_step_date_time_is_a_utc_instant(child):
    child["processStep"][-1]["stepDateTime"] = "2026-10-01 16:41"
    assert problems_mention(check_obj(child), "stepDateTime")


def test_print_outputs_need_sha256(child):
    del child["processStep"][-1]["output"][0]["sourceCitation"]["sha256"]
    assert problems_mention(check_obj(child), "sha256")


def test_sha256_is_64_lowercase_hex(child):
    child["source"][0]["sourceCitation"]["sha256"] = "ABC"
    assert problems_mention(check_obj(child), "sha256")


def test_parent_citation_needs_sha256(child):
    del child["source"][0]["sourceMetadata"][0]["sha256"]
    assert problems_mention(check_obj(child), "sha256")


def test_scope_other_than_software_is_reported(child):
    child["source"][0]["scope"] = {"level": "dataset"}
    assert problems_mention(check_obj(child), "scope")


def test_component_needs_a_citation(child):
    del child["processStep"][0]["processingInformation"]["algorithm"][1]["citation"]
    assert problems_mention(check_obj(child), "citation")


def test_processing_needs_an_identifier(child):
    del child["processStep"][0]["processingInformation"]["identifier"]
    assert problems_mention(check_obj(child), "identifier")


def test_report_needs_a_name(child):
    del child["processStep"][1]["report"][0]["name"]
    assert problems_mention(check_obj(child), "name")


def test_write_mints_canonical_bytes_and_returns_their_hash(tmp_path, parent):
    path = tmp_path / "fbm_roi.npz.gprv"
    h = write(path, parent)
    assert path.read_bytes() == canonical(parent)
    assert h == sha256(path.read_bytes()) == sha256((EXAMPLES / "fbm_roi.npz.gprv").read_bytes())


def test_write_never_overwrites(tmp_path, parent):
    path = tmp_path / "fbm_roi.npz.gprv"
    write(path, parent)
    with pytest.raises(FileExistsError):
        write(path, parent)


def test_write_applies_the_value_rules(tmp_path, child):
    child["processStep"][1]["report"][0]["description"]["snr_db"] = math.inf
    path = tmp_path / "r.gprv"
    write(path, child)
    assert json.loads(path.read_bytes())["processStep"][1]["report"][0]["description"]["snr_db"] == "Infinity"


def test_write_refuses_an_invalid_record(tmp_path, child):
    del child["statement"]
    with pytest.raises(RecordError):
        write(tmp_path / "r.gprv", child)
    assert not (tmp_path / "r.gprv").exists()


def test_report_description_is_text_or_an_object(child):
    child["processStep"][1]["report"][0]["description"] = 3
    assert problems_mention(check_obj(child), "report[0].description")


# --------------------------------------------------------------------------- 0.2: codeOrigin


def origin(**changes) -> dict:
    o = {"kind": "file", "source": "file:devices/ridge_filter.py", "name": "ridge_filter", "version": "1.2.0",
         "contentHash": {"algorithm": "sha256", "value": "a" * 64, "covers": "file"},
         "license": "MIT", "editable": False}
    for k, v in changes.items():
        if v is None:
            o.pop(k, None)
        else:
            o[k] = v
    return o


def with_origins(child, step=None, component=None) -> dict:
    """The child example as a 0.2 record, a codeOrigin on step p1 and on its first component."""
    child["gprv"] = "0.2"
    p1 = child["processStep"][0]
    p1["codeOrigin"] = step if step is not None else origin()
    p1["processingInformation"]["algorithm"][0]["codeOrigin"] = component if component is not None else origin(
        kind="package", source="pypi:ridge-tools==1.2.0",
        contentHash={"algorithm": "sha256", "value": "b" * 64, "covers": "distribution"})
    return child


def test_a_0_2_record_with_code_origins_on_a_step_and_a_component_verifies(child):
    assert check_obj(with_origins(child)) == []


def test_code_origin_is_unknown_in_a_0_1_record(child):
    child["processStep"][0]["codeOrigin"] = origin()
    assert any("unknown key 'codeOrigin'" in p for p in check_obj(child))


@pytest.mark.parametrize("bad, word", [
    (dict(kind="plugin"), "kind"),
    (dict(source="devices/ridge_filter.py"), "source"),
    (dict(contentHash={"algorithm": "sha256", "value": "a" * 40, "covers": "file"}), "64"),
    (dict(contentHash={"algorithm": "md5", "value": "a" * 32, "covers": "file"}), "algorithm"),
    (dict(contentHash={"algorithm": "sha256", "value": "a" * 64, "covers": "tree"}), "covers"),
    (dict(contentHash={"algorithm": "sha256", "covers": "file"}), "value"),
    (dict(license="MIT OR"), "license"),
    (dict(license="Proprietary!"), "license"),
    (dict(editable="no"), "editable"),
    (dict(name=None), "name"),
    (dict(glow="x"), "glow"),
])
def test_a_bad_code_origin_is_reported_by_its_field(child, bad, word):
    problems = check_obj(with_origins(child, step=origin(**bad)))
    assert problems and all("codeOrigin" in p for p in problems) and any(word in p for p in problems)


def test_a_service_origin_may_carry_no_hash_value(child):
    svc = origin(kind="service", source="https://api.example.org/v2/ridge", version=None,
                 contentHash={"algorithm": "sha256", "covers": "none"}, license="NOASSERTION")
    assert check_obj(with_origins(child, step=svc)) == []


def test_spdx_expressions_with_operators_and_exceptions_pass(child):
    for expr in ("MIT OR Apache-2.0", "GPL-2.0-or-later WITH Classpath-exception-2.0", "(MIT AND BSD-3-Clause) OR GPL-3.0-only"):
        assert check_obj(with_origins(child, step=origin(license=expr))) == [], expr


# --------------------------------------------------------------------------- 0.2: migrate


def test_migrate_turns_a_repository_software_reference_into_a_code_origin(child):
    from gprv.record import migrate

    out = migrate(child)
    assert child["gprv"] == "0.1"                              # the input is left alone
    assert out["gprv"] == "0.2" and check_obj(out) == []
    o = out["processStep"][0]["codeOrigin"]
    assert o == {"kind": "repository",
                 "source": "git+https://github.com/MarioKartUltra/GeoDynamX@6194b86e5859cf5a4a0d68f8425b8ac8d86d2df8",
                 "name": "GeoDynamix", "version": "6194b86e5859cf5a4a0d68f8425b8ac8d86d2df8",
                 "contentHash": {"algorithm": "sha256", "covers": "none"}, "license": "NOASSERTION",
                 "editable": False}
    # a step citing the software by id gets the same origin; one without a software reference gets none
    assert out["processStep"][1]["codeOrigin"] == o
    assert "codeOrigin" not in out["processStep"][2] or out["processStep"][2]["codeOrigin"] == o
    assert out["processStep"][0]["processingInformation"]["softwareReference"] == child["processStep"][0]["processingInformation"]["softwareReference"]


def test_migrate_adds_nothing_it_cannot_derive(child):
    from gprv.record import migrate

    sw = child["processStep"][0]["processingInformation"]["softwareReference"]
    sw["edition"] = "v1.2"                                    # a release, not a commit: nothing to derive
    out = migrate(child)
    assert out["gprv"] == "0.2" and all("codeOrigin" not in st for st in out["processStep"])
    assert migrate(out) == out                                # idempotent on a 0.2 record
