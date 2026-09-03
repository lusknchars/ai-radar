"""Offline evaluation of PDF adapters against page-grounded fixtures."""
from __future__ import annotations

import re
from dataclasses import dataclass
from time import perf_counter
from typing import Callable

from .fulltext import PdfExtractor

_WHITESPACE = re.compile(r"\s+")


@dataclass(frozen=True)
class ExpectedExcerpt:
    page: int
    text: str

    def __post_init__(self) -> None:
        if self.page < 1:
            raise ValueError("expected excerpt page must be positive")
        if not self.text.strip():
            raise ValueError("expected excerpt text cannot be empty")


@dataclass(frozen=True)
class ExtractionFixture:
    arxiv_id: str
    expected_pages: int
    required_excerpts: tuple[ExpectedExcerpt, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "required_excerpts", tuple(self.required_excerpts))
        if self.expected_pages < 1:
            raise ValueError("expected page count must be positive")
        if any(item.page > self.expected_pages for item in self.required_excerpts):
            raise ValueError("expected excerpt points past the expected page count")


@dataclass(frozen=True)
class ExtractionScore:
    arxiv_id: str
    extractor: str
    status: str
    duration_ms: int
    expected_pages: int
    actual_pages: int | None
    nonempty_pages: int
    excerpts_total: int
    excerpts_found: int
    fallback_from: str | None = None
    fallback_reason: str | None = None
    error: str | None = None

    @property
    def page_count_matches(self) -> bool:
        return self.actual_pages == self.expected_pages

    @property
    def excerpt_recall(self) -> float:
        if self.excerpts_total == 0:
            return 1.0
        return self.excerpts_found / self.excerpts_total


def _normalized(text: str) -> str:
    return _WHITESPACE.sub(" ", text).strip().casefold()


def evaluate_extractor(
    fixture: ExtractionFixture,
    pdf_bytes: bytes,
    extractor: PdfExtractor,
    *,
    clock: Callable[[], float] = perf_counter,
) -> ExtractionScore:
    """Scores one adapter without network access or model calls."""
    started = clock()
    try:
        extraction = extractor.extract(pdf_bytes, fixture.arxiv_id)
    except Exception as exc:
        duration_ms = round((clock() - started) * 1000)
        return ExtractionScore(
            arxiv_id=fixture.arxiv_id,
            extractor=extractor.name,
            status="error",
            duration_ms=duration_ms,
            expected_pages=fixture.expected_pages,
            actual_pages=None,
            nonempty_pages=0,
            excerpts_total=len(fixture.required_excerpts),
            excerpts_found=0,
            error=type(exc).__name__,
        )

    normalized_pages = tuple(_normalized(page) for page in extraction.pages)
    found = sum(
        1
        for item in fixture.required_excerpts
        if item.page <= len(normalized_pages)
        and _normalized(item.text) in normalized_pages[item.page - 1]
    )
    duration_ms = round((clock() - started) * 1000)
    return ExtractionScore(
        arxiv_id=fixture.arxiv_id,
        extractor=extraction.method,
        status="ok",
        duration_ms=duration_ms,
        expected_pages=fixture.expected_pages,
        actual_pages=len(extraction.pages),
        nonempty_pages=sum(bool(page) for page in normalized_pages),
        excerpts_total=len(fixture.required_excerpts),
        excerpts_found=found,
        fallback_from=extraction.fallback_from,
        fallback_reason=extraction.fallback_reason,
    )
