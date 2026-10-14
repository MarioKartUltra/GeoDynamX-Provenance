import pytest
from jsonschema import Draft202012Validator

from conftest import EXAMPLES, example
from gprv.record import check_obj, schema

VALIDATOR = Draft202012Validator(schema())


def test_schema_is_a_valid_draft_2020_12_schema():
    Draft202012Validator.check_schema(schema())


@pytest.mark.parametrize("name", sorted(p.name for p in EXAMPLES.glob("*.gprv")))
def test_example_records_validate(name):
    assert list(VALIDATOR.iter_errors(example(name))) == []


def unknown_key(r): r["processStep"][2]["view"] = {}
def no_description(r): del r["processStep"][1]["description"]
def bad_sha(r): r["source"][0]["sourceCitation"]["sha256"] = "ABC"
def bad_id(r): r["processStep"][0]["id"] = "1p"
def other_scope(r): r["source"][0]["scope"] = {"level": "dataset"}
def no_identifier(r): del r["processStep"][0]["processingInformation"]["identifier"]
def wrong_version(r): r["gprv"] = "9.9"
def bad_time(r): r["processStep"][2]["stepDateTime"] = "yesterday"
def parent_without_sha(r): del r["source"][0]["sourceMetadata"][0]["sha256"]
def no_steps(r): r["processStep"] = []


@pytest.mark.parametrize("mutate", [unknown_key, no_description, bad_sha, bad_id, other_scope, no_identifier,
                                    wrong_version, bad_time, parent_without_sha, no_steps])
def test_schema_and_checks_both_reject(mutate):
    r = example("fbm_recon.tif.gprv")
    mutate(r)
    assert list(VALIDATOR.iter_errors(r)) != []
    assert check_obj(r) != []
