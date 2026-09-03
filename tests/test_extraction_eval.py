from radar.extraction_eval import (ExpectedExcerpt, ExtractionFixture,
                                   evaluate_extractor)
from radar.fulltext import PdfExtraction


class Extractor:
    name = "docling"

    def __init__(self, pages=None, error=None):
        self.pages = pages
        self.error = error

    def extract(self, content, arxiv_id):
        if self.error:
            raise self.error
        return PdfExtraction(self.pages, method="docling")


def fixture():
    return ExtractionFixture(
        arxiv_id="2608.11111",
        expected_pages=2,
        required_excerpts=(
            ExpectedExcerpt(page=1, text="Latency fell by 37 percent."),
            ExpectedExcerpt(page=2, text="Model 7B on an A100."),
        ),
    )


def test_extraction_eval_scores_page_count_and_exact_page_excerpts():
    ticks = iter((10.0, 10.125))
    score = evaluate_extractor(
        fixture(),
        b"pdf",
        Extractor((
            "The result says latency fell   by 37 percent.",
            "Conditions: model 7B on an A100.",
        )),
        clock=lambda: next(ticks),
    )

    assert score.status == "ok"
    assert score.page_count_matches is True
    assert score.excerpt_recall == 1.0
    assert score.duration_ms == 125
    assert score.nonempty_pages == 2


def test_extraction_eval_does_not_accept_an_excerpt_on_the_wrong_page():
    score = evaluate_extractor(
        fixture(),
        b"pdf",
        Extractor((
            "Model 7B on an A100.",
            "Latency fell by 37 percent.",
        )),
    )

    assert score.excerpt_recall == 0.0


def test_extraction_eval_records_adapter_errors_without_leaking_messages():
    score = evaluate_extractor(
        fixture(), b"pdf", Extractor(error=RuntimeError("secret path")))

    assert score.status == "error"
    assert score.error == "RuntimeError"
    assert "secret" not in repr(score)
