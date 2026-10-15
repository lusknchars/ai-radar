import json
from pathlib import Path

import pytest

from radar.lab_reproductions import apply_lab_reproductions, copy_lab_flow, load_flow
from radar.public_research import LabFlowRef, ResearchPage

ROOT = Path(__file__).resolve().parents[1]
COMMIT = "a" * 40


def snapshot(**over):
    data = {
        "schema": 1, "study": "transduced-lm-2026",
        "source": {"repo": "https://github.com/lusknchars/paper-raft", "commit": COMMIT, "built_at": "2026-10-14T00:00:00+00:00"},
        "paper": {"title": "T", "authors_short": "S et al. 2026", "reference_checked": True, "draft": False},
        "items": [{"id": "a", "kind": "equation"}],
        "methods": [{"name": "m", "implements": ["a"], "status": "verified", "color": 0}],
        "cases": [{"key": "case=bigram", "label": "bigram"}],
        "runs": [{"run_id": "m-casebigram", "method": "m", "params": {"case": "bigram"}, "case": "case=bigram",
                  "status": "verified", "pass": True, "started_at": "2026-10-13T00:00:00+00:00",
                  "metrics": [{"key": "bias", "value": 2.1}]}],
        "metrics": [{"key": "bias", "label": "worst bias test", "note": "limit 4σ", "agg": "max", "format": "sigma"}],
    }
    data.update(over)
    return data


def ref(**over):
    base = {"file": "2608.27428.flow.json", "study": "transduced-lm-2026", "source_commit": COMMIT,
            "exported_at": "2026-10-14", "explorer_url": "https://lusknchars.github.io/paper-raft/#flow/transduced-lm-2026"}
    base.update(over)
    return LabFlowRef.model_validate(base)


def write(tmp_path, data):
    p = tmp_path / "2608.27428.flow.json"
    p.write_text(json.dumps(data))
    return p


def test_load_flow_accepts_a_matching_snapshot(tmp_path):
    snap = load_flow(write(tmp_path, snapshot()), ref())
    assert snap.study == "transduced-lm-2026" and snap.runs[0].passed is True


@pytest.mark.parametrize("change", ["study", "commit", "extra", "bad_format", "missing"])
def test_load_flow_rejects_mismatches(tmp_path, change):
    data = snapshot()
    if change == "study":
        data["study"] = "other-study"
    elif change == "commit":
        data["source"]["commit"] = "b" * 40
    elif change == "extra":
        data["runs"][0]["html"] = "<b>"
    elif change == "bad_format":
        data["metrics"][0]["format"] = "html"
    path = write(tmp_path, data) if change != "missing" else tmp_path / "none.flow.json"
    with pytest.raises(ValueError):
        load_flow(path, ref())


@pytest.mark.parametrize("field,value", [("file", "../x.flow.json"), ("source_commit", "abc"),
                                         ("explorer_url", "javascript:alert(1)"), ("study", "Bad Study")])
def test_flow_ref_rejects_unsafe_values(field, value):
    with pytest.raises(ValueError):
        ref(**{field: value})


def edition_with_flow(tmp_path):
    data = json.loads((ROOT / "content/reproductions/2608.27428.json").read_text())
    data["reproductions"][0]["flow"] = ref().model_dump()
    (tmp_path / "2608.27428.json").write_text(json.dumps(data))
    return tmp_path / "2608.27428.json"


def page():
    return ResearchPage.model_validate_json((ROOT / "site/papers/2608.27428/index.json").read_text())


def test_apply_validates_the_snapshot_and_copy_places_it(tmp_path):
    edition = edition_with_flow(tmp_path)
    with pytest.raises(ValueError):
        apply_lab_reproductions(page(), edition)  # snapshot file not there yet
    write(tmp_path, snapshot())
    linked = apply_lab_reproductions(page(), edition)
    assert linked.lab_reproductions[0].flow.study == "transduced-lm-2026"
    out = tmp_path / "out"
    out.mkdir()
    assert copy_lab_flow(linked, tmp_path, out) is True
    assert json.loads((out / "lab-flow.json").read_text())["study"] == "transduced-lm-2026"
    assert copy_lab_flow(page(), tmp_path, out) is False
