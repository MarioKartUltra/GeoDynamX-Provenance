import math
from pathlib import Path

import pytest

from gprv.canon import CanonicalError, canonical, normalize, sha256

EXAMPLES = Path(__file__).resolve().parents[1] / "spec" / "examples"


def test_canonical_sorts_keys_and_writes_shortest_numbers():
    assert canonical({"b": 1, "a": [1.0, "α", 1e-7, 1e16, -0.0]}) == '{"a":[1,"α",1e-7,10000000000000000,0],"b":1}'.encode()


def test_canonical_refuses_non_finite_floats():
    with pytest.raises(CanonicalError):
        canonical({"x": math.nan})


def test_canonical_refuses_integers_outside_the_safe_range():
    with pytest.raises(CanonicalError):
        canonical(2**53)


def test_example_records_are_canonical_under_this_implementation():
    # the examples were canonicalized by an independent ECMAScript implementation
    import json
    for p in sorted(EXAMPLES.glob("*.gprv")):
        data = p.read_bytes()
        assert canonical(json.loads(data)) == data, p.name


def test_normalize_writes_non_finite_floats_as_strings():
    assert normalize({"a": math.nan, "b": math.inf, "c": -math.inf}) == {"a": "NaN", "b": "Infinity", "c": "-Infinity"}


def test_normalize_writes_unsafe_integers_as_strings():
    assert normalize([2**53, -(2**53), 2**53 - 1]) == [str(2**53), str(-(2**53)), 2**53 - 1]


def test_normalize_turns_tuples_into_lists():
    assert normalize({"extent": (0, 512)}) == {"extent": [0, 512]}


def test_normalize_unwraps_numpy_values():
    np = pytest.importorskip("numpy")
    out = normalize({"k": np.float32(0.5), "n": np.int64(3), "a": np.array([1.0, np.nan]), "b": np.bool_(True)})
    assert out == {"k": 0.5, "n": 3, "a": [1.0, "NaN"], "b": True}
    assert type(out["n"]) is int and type(out["b"]) is bool


def test_normalize_refuses_non_string_keys():
    with pytest.raises(CanonicalError):
        normalize({1: "x"})


def test_sha256_is_lowercase_hex_of_the_bytes():
    assert sha256(b"") == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


# --------------------------------------------------------------------------- 0.2: code hashes


def test_a_directory_hash_is_the_spec_concatenation_in_sorted_path_order(tmp_path):
    import hashlib

    from gprv.canon import hash_directory, hash_file

    (tmp_path / "b.py").write_bytes(b"print(2)\n")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "a.py").write_bytes(b"print(1)\n")
    (tmp_path / "empty").mkdir()                          # counts for nothing
    expected = ""
    for rel in ("b.py", "sub/a.py"):
        expected += rel + "\n" + hashlib.sha256((tmp_path / rel).read_bytes()).hexdigest() + "\n"
    assert hash_directory(tmp_path) == hashlib.sha256(expected.encode()).hexdigest()
    assert hash_file(tmp_path / "b.py") == hashlib.sha256(b"print(2)\n").hexdigest()
    (tmp_path / "sub" / "a.py").write_bytes(b"print(3)\n")
    assert hash_directory(tmp_path) != hashlib.sha256(expected.encode()).hexdigest()
