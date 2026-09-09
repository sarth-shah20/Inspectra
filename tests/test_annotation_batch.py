import runpy

allocate = runpy.run_path("scripts/export_annotation_batch.py")["allocate"]


def test_stratified_allocation_is_deterministic_and_balanced():
    strata = {
        ("aviation", "a"): [{"record_id": "a1", "rank": "1"}, {"record_id": "a2", "rank": "2"}],
        ("aviation", "b"): [{"record_id": "b1", "rank": "1"}, {"record_id": "b2", "rank": "2"}],
        ("pipeline", "c"): [{"record_id": "c1", "rank": "1"}],
    }
    assert allocate(strata, 3) == {"a1", "a2", "b1", "c1"}
