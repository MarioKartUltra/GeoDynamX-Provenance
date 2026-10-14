import gprv


def test_public_api():
    for name in ["canonical", "normalize", "sha256", "write", "check", "check_obj", "RecordError", "schema",
                 "assemble", "collect", "load_store", "verify", "export"]:
        assert callable(getattr(gprv, name)), name
    assert gprv.FORMAT_VERSION == "0.1"
