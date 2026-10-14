from conftest import EXAMPLES, example
from gprv.assembly import assemble, collect, load_store, verify
from gprv.canon import canonical, sha256

PARENT = (EXAMPLES / "fbm_roi.npz.gprv").read_bytes()
CHILD = (EXAMPLES / "fbm_recon.tif.gprv").read_bytes()
SIBLING = (EXAMPLES / "fbm_recon.png.gprv").read_bytes()
BOEM = (EXAMPLES / "boem_roi.npz.gprv").read_bytes()


def test_assembly_lines_are_the_members_sorted_by_hash():
    blob = assemble([CHILD, PARENT])
    lines = blob.split(b"\n")
    assert lines[-1] == b"" and sorted(lines[:-1], key=sha256) == lines[:-1]
    assert set(lines[:-1]) == {CHILD, PARENT}


def test_assembly_bytes_do_not_depend_on_input_order_or_duplicates():
    assert assemble([CHILD, PARENT]) == assemble([PARENT, CHILD, PARENT])


def test_assembly_matches_the_published_example():
    assert assemble([PARENT, CHILD]) == (EXAMPLES / "fbm_recon.tif.gprv.jsonl").read_bytes()


def test_product_branch_verifies_with_the_child_as_sink():
    v = verify(assemble([PARENT, CHILD]))
    assert v.ok and v.sink == sha256(CHILD) and v.gaps == []


def test_single_record_with_no_parent_verifies():
    v = verify(assemble([BOEM]))
    assert v.ok and v.sink == sha256(BOEM)


def test_two_products_without_one_that_uses_both_fail():
    v = verify(assemble([PARENT, CHILD, SIBLING]))
    assert not v.ok and any("2 sinks" in p for p in v.problems)


def test_child_alone_verifies_and_lists_the_missing_parent_as_a_gap():
    v = verify(assemble([CHILD]))
    assert v.ok
    assert [(g.member, g.source, g.cited) for g in v.gaps] == [(sha256(CHILD), "s1", sha256(PARENT))]


def test_edited_parent_breaks_the_citation():
    tampered = PARENT.replace(b'"x0":256', b'"x0":257')
    v = verify(assemble([tampered, CHILD]))
    assert not v.ok and len(v.gaps) == 1


def test_child_reading_a_dataset_its_parent_never_wrote_fails():
    rec = example("fbm_recon.tif.gprv")
    rec["source"][0]["sourceCitation"]["sha256"] = "0" * 64
    v = verify(assemble([PARENT, canonical(rec)]))
    assert not v.ok and any("did not output" in p for p in v.problems)


def test_non_canonical_line_fails():
    pretty = CHILD.replace(b'{"gprv":"0.1",', b'{"gprv": "0.1",')
    v = verify(assemble([PARENT]) + pretty + b"\n")
    assert not v.ok and any("not canonical" in p for p in v.problems)


def test_unsorted_lines_fail():
    a, b = sorted([PARENT, CHILD], key=sha256)
    v = verify(b + b"\n" + a + b"\n")
    assert not v.ok and any("sorted" in p for p in v.problems)


def test_missing_final_newline_fails():
    v = verify(assemble([PARENT, CHILD])[:-1])
    assert not v.ok and any("LF" in p for p in v.problems)


def test_member_failing_the_record_checks_fails_the_assembly():
    rec = example("fbm_roi.npz.gprv")
    del rec["processStep"][-1]["stepDateTime"]
    v = verify(assemble([canonical(rec)]))
    assert not v.ok and any("stepDateTime" in p for p in v.problems)


def test_collect_takes_the_product_and_its_ancestors_only():
    store = {sha256(b): b for b in (PARENT, CHILD, SIBLING, BOEM)}
    members, gaps = collect(CHILD, store)
    assert sorted(members) == sorted([PARENT, CHILD]) and gaps == []


def test_collect_reports_an_ancestor_missing_from_the_store():
    members, gaps = collect(CHILD, {sha256(CHILD): CHILD})
    assert members == [CHILD] and [g.cited for g in gaps] == [sha256(PARENT)]


def test_load_store_reads_every_record_in_the_directories():
    store = load_store([EXAMPLES])
    assert store[sha256(PARENT)] == PARENT and len(store) == 4
