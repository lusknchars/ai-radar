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
    raw = json.loads((ROOT / "site/papers/2608.27428/index.json").read_text())
    return ResearchPage.model_validate({**raw, "lab_reproductions": []})


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


from radar.site import render_research_page


def real_page():
    return apply_lab_reproductions(page(), ROOT / "content/reproductions/2608.27428.json")


def test_paper_page_carries_the_demo_after_the_text_summary():
    html = render_research_page(real_page())
    section = html[html.index('id="lab-reproductions"'):]
    assert section.index("methods verified by a separate reviewer") < section.index('id="lab-flow"')
    assert 'data-src="/ai-radar/papers/2608.27428/lab-flow.json"' in section or 'data-src="/papers/2608.27428/lab-flow.json"' in section
    assert '"three": "' in section and "three-0.186.1/build/three.module.js" in section
    assert "Open the full view in Paper Raft" in section and 'rel="noopener noreferrer"' in section
    assert "Lab data from commit" in section


def test_page_without_flow_has_no_demo():
    html = render_research_page(page())
    assert 'id="lab-flow"' not in html and "three-0.186.1" not in html


def test_snapshot_text_never_reaches_the_page_html(tmp_path):
    data = json.loads((ROOT / "content/reproductions/2608.27428.flow.json").read_text())
    data["paper"]["title"] = '</script><img src=x onerror=alert(1)>'
    (tmp_path / "2608.27428.flow.json").write_text(json.dumps(data))
    edition = json.loads((ROOT / "content/reproductions/2608.27428.json").read_text())
    (tmp_path / "2608.27428.json").write_text(json.dumps(edition))
    html = render_research_page(apply_lab_reproductions(page(), tmp_path / "2608.27428.json"))
    assert "onerror" not in html


def test_vendored_flow_assets_are_present():
    base = ROOT / "assets/vendor"
    assert (base / "three-0.186.1/build/three.module.js").is_file()
    assert (base / "three-0.186.1/LICENSE").is_file()
    assert "export function mountFlow" in (base / "paper-raft-flow/flow.js").read_text()


def test_demo_box_is_a_region_not_an_image():
    html = render_research_page(real_page())
    assert '<noscript><style>#lab-flow{display:none}</style></noscript>' in html
    assert 'role="region" aria-label="Chain from the paper' in html
    assert 'role="img" aria-label="Chain' not in html


def test_provenance_line_differs_when_lab_reproductions_exist():
    with_lab = render_research_page(real_page())
    without = render_research_page(page())
    assert "Paperraft's editors have not rerun this experiment; see Reproduced in Paper Raft above" in with_lab
    assert "Paperraft has not reproduced this experiment." not in with_lab
    assert "Paperraft has not reproduced this experiment." in without


def test_flow_file_must_be_named_after_the_paper(tmp_path):
    data = json.loads((ROOT / "content/reproductions/2608.27428.json").read_text())
    data["reproductions"][0]["flow"]["file"] = "2608.99999.flow.json"
    (tmp_path / "2608.27428.json").write_text(json.dumps(data))
    (tmp_path / "2608.99999.flow.json").write_text(
        (ROOT / "content/reproductions/2608.27428.flow.json").read_text())
    with pytest.raises(ValueError, match="flow file"):
        apply_lab_reproductions(page(), tmp_path / "2608.27428.json")
