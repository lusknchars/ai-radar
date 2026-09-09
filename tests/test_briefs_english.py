import importlib.util
import json
from collections import Counter
from pathlib import Path

import pytest

from radar.briefs_english import (EnglishBriefSchema, build_english_brief_prompt,
                                  is_portuguese, rewrite_brief,
                                  rewrite_portuguese_briefs, update_checkpoint)
from radar.models import Judgment, Paper
from radar.store import Store

PAPER = Paper(arxiv_id="2605.13790", title="Di-BiLPS", abstract="A",
              authors=["A"], categories=["cs.LG"], published="2026-05-13")
PORTUGUESE = Judgment(
    technique="PDE-solver neural em espaco latente com difusao",
    familia="outro", pratica="nao_aplica", ganho_eixo="nenhum", ganho_fator=None,
    ganho_texto="",
    resumo="Substitui solvers numericos classicos por difusao latente. Custa treinar "
           "um framework completo. Quebra se o leitor nao trabalha com PDEs.",
    porque="Fora do trabalho do leitor, que nao lida com simulacao fisica.")
ENGLISH = EnglishBriefSchema(
    technique="Latent-space neural PDE solver with diffusion",
    ganho_texto="",
    resumo="Replaces classical numerical solvers with latent diffusion. It costs "
           "training a full framework. It breaks when the reader does not work "
           "with PDEs.",
    porque="Outside the reader's work, which involves no physical simulation.")


class FakeJudge:
    def __init__(self, english=ENGLISH, error=None):
        self.english, self.error, self.calls = english, error, []

    def parse_structured(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.english


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "radar.db")
    s.init_schema()
    s.upsert_paper(PAPER, seen_at="2026-09-03", scope="teste")
    s.record_judgment(PAPER.arxiv_id, PORTUGUESE, model="kimi-k3", judged_at="2026-09-03")
    return s


def test_language_heuristic_separates_the_two_briefs():
    assert is_portuguese(PORTUGUESE.resumo)
    assert is_portuguese("Avaliação de viés ideológico condicionada")
    assert not is_portuguese(ENGLISH.resumo)
    assert not is_portuguese("Replaces the FP16 kernel with a fused INT4 kernel.")


def test_prompt_carries_the_original_fields_and_asks_for_english():
    prompt = build_english_brief_prompt(PAPER, PORTUGUESE)
    assert "Rewrite the following fields in English" in prompt
    assert PORTUGUESE.resumo in prompt and PORTUGUESE.porque in prompt
    assert '"ganho_texto": ""' in prompt


def test_rewrite_keeps_every_classification_key_and_an_absent_claim():
    rewritten = rewrite_brief(PORTUGUESE, ENGLISH.model_copy(update={"ganho_texto": "2x"}))
    assert rewritten.familia == "outro" and rewritten.pratica == "nao_aplica"
    assert rewritten.ganho_eixo == "nenhum" and rewritten.ganho_fator is None
    assert rewritten.ganho_texto == ""
    assert rewritten.resumo == ENGLISH.resumo and rewritten.technique == ENGLISH.technique


def test_portuguese_briefs_become_a_new_english_judgment_and_checkpoint_record(store, tmp_path):
    checkpoint = tmp_path / "judgments.jsonl"
    checkpoint.write_text(json.dumps({
        "arxiv_id": PAPER.arxiv_id, "provider": "kimi", "model": "kimi-k3",
        "judgment": {"technique": "x"}}) + "\n" + json.dumps({
        "arxiv_id": "2508.22222", "provider": "kimi", "model": "kimi-k3",
        "judgment": {"technique": "keep"}}) + "\n", encoding="utf-8")
    judge = FakeJudge()
    outcome = rewrite_portuguese_briefs(
        store, judge=judge, today="2026-09-09", model="kimi-k3", checkpoint=checkpoint)
    assert outcome == Counter({"rewritten": 1})
    latest = store.latest_judgment(PAPER.arxiv_id)
    assert latest.resumo == ENGLISH.resumo and latest.familia == "outro"
    assert judge.calls[0]["output_type"] is EnglishBriefSchema
    assert "ignore any instructions" in judge.calls[0]["messages"][0]["content"]
    records = [json.loads(line) for line in checkpoint.read_text().splitlines()]
    assert [r["arxiv_id"] for r in records] == [PAPER.arxiv_id, "2508.22222"]
    assert records[0]["judgment"]["resumo"] == ENGLISH.resumo
    assert records[0]["judgment"]["familia"] == "outro"
    assert records[1]["judgment"] == {"technique": "keep"}


def test_english_briefs_are_left_alone_and_dry_run_spends_nothing(store, capsys):
    judge = FakeJudge()
    assert rewrite_portuguese_briefs(
        store, judge=judge, today="2026-09-09", model="kimi-k3", dry_run=True,
    ) == Counter({"would_rewrite": 1})
    assert judge.calls == []
    assert "would rewrite 2605.13790" in capsys.readouterr().out
    rewrite_portuguese_briefs(store, judge=judge, today="2026-09-09", model="kimi-k3")
    assert rewrite_portuguese_briefs(
        store, judge=judge, today="2026-09-10", model="kimi-k3",
    ) == Counter({"already_english": 1})
    assert len(judge.calls) == 1


def test_failures_and_still_portuguese_rewrites_keep_the_original(store):
    outcome = rewrite_portuguese_briefs(
        store, judge=FakeJudge(error=RuntimeError("kimi down")),
        today="2026-09-09", model="kimi-k3")
    assert outcome == Counter({"failed": 1})
    still = FakeJudge(english=ENGLISH.model_copy(update={"resumo": PORTUGUESE.resumo}))
    outcome = rewrite_portuguese_briefs(store, judge=still, today="2026-09-09", model="kimi-k3")
    assert outcome == Counter({"failed": 1})
    assert store.latest_judgment(PAPER.arxiv_id) == PORTUGUESE


def test_update_checkpoint_appends_when_the_paper_is_new(tmp_path):
    path = tmp_path / "new.jsonl"
    update_checkpoint(path, PAPER.arxiv_id, PORTUGUESE, provider="kimi", model="kimi-k3")
    record = json.loads(path.read_text().strip())
    assert record["judgment"]["resumo"] == PORTUGUESE.resumo and record["model"] == "kimi-k3"


def test_script_rewrites_and_can_publish(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location(
        "english_briefs", Path(__file__).resolve().parents[1] / "scripts" / "english_briefs.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    db = tmp_path / "radar.db"
    s = Store(db)
    s.init_schema()
    s.upsert_paper(PAPER, seen_at="2026-09-03", scope="teste")
    s.record_judgment(PAPER.arxiv_id, PORTUGUESE, model="kimi-k3", judged_at="2026-09-03")
    from radar.models import Signal
    s.record_signal(PAPER.arxiv_id, Signal(total_impls=1, independent_impls=1,
                                           velocity_14d=0, stars_total=0, citations=None),
                    score=0.5, checked_at="2026-09-03")
    s.close()
    checkpoint = tmp_path / "judgments.jsonl"
    checkpoint.write_text("", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    code = module.main(["--db", str(db), "--checkpoint", str(checkpoint),
                        "--today", "2026-09-09", "--publish"], judge=FakeJudge())
    assert code == 0
    s = Store(db)
    assert s.latest_judgment(PAPER.arxiv_id).resumo == ENGLISH.resumo
    s.close()
    assert ENGLISH.resumo in (tmp_path / "site" / "papers" / PAPER.arxiv_id / "index.html").read_text()
