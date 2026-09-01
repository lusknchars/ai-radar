import pytest

import radar.fulltext as fulltext


class Response:
    content = b"%PDF fake"

    def raise_for_status(self):
        pass


class Page:
    def __init__(self, text):
        self._text = text

    def extract_text(self):
        return self._text


def test_fulltext_downloads_the_official_pdf_and_extracts_pages(monkeypatch):
    calls = []
    monkeypatch.setattr(fulltext, "PdfReader",
                        lambda stream: type("R", (), {
                            "pages": [Page("A" * 300), Page("B" * 300)]})())

    def get(url, **kwargs):
        calls.append((url, kwargs))
        return Response()

    text = fulltext.fetch_full_text("2608.11111", get=get)
    assert "A" * 100 in text and "B" * 100 in text
    assert "[AI-RADAR PAGE 1]" in text
    assert "[AI-RADAR PAGE 2]" in text
    assert text.index("[AI-RADAR PAGE 1]") < text.index("[AI-RADAR PAGE 2]")
    assert calls[0][0] == "https://arxiv.org/pdf/2608.11111"
    assert calls[0][1]["follow_redirects"] is True


def test_fulltext_rejects_an_id_before_building_a_url():
    with pytest.raises(ValueError, match="arxiv_id"):
        fulltext.fetch_full_text("../../secret", get=lambda *a, **k: None)


def test_fulltext_rejects_an_image_only_pdf(monkeypatch):
    monkeypatch.setattr(fulltext, "PdfReader",
                        lambda stream: type("R", (), {"pages": [Page("")]})())
    with pytest.raises(ValueError, match="texto suficiente"):
        fulltext.fetch_full_text("2608.11111", get=lambda *a, **k: Response())
