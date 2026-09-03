import io
import hashlib
import tarfile

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


def test_paper_source_records_the_exact_pdf_hash(monkeypatch):
    monkeypatch.setattr(fulltext, "PdfReader",
                        lambda stream: type("R", (), {
                            "pages": [Page("A" * 600)]})())

    source = fulltext.fetch_paper_source(
        "2608.11111", get=lambda *a, **k: Response())

    assert source.pdf_sha256 == hashlib.sha256(Response.content).hexdigest()
    assert source.pdf_extraction_method == "pypdf"


def test_fulltext_rejects_an_id_before_building_a_url():
    with pytest.raises(ValueError, match="arxiv_id"):
        fulltext.fetch_full_text("../../secret", get=lambda *a, **k: None)


def test_fulltext_rejects_an_image_only_pdf(monkeypatch):
    monkeypatch.setattr(fulltext, "PdfReader",
                        lambda stream: type("R", (), {"pages": [Page("")]})())
    with pytest.raises(ValueError, match="texto suficiente"):
        fulltext.fetch_full_text("2608.11111", get=lambda *a, **k: Response())


def _tar_bytes(files):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for name, content in files.items():
            payload = content.encode("utf-8")
            member = tarfile.TarInfo(name)
            member.size = len(payload)
            archive.addfile(member, io.BytesIO(payload))
    return buffer.getvalue()


def test_source_archive_reader_keeps_only_tex_files_in_memory():
    files = fulltext.read_tex_source_archive(_tar_bytes({
        "paper/main.tex": r"\begin{document}x\end{document}",
        "paper/refs.bib": "@article{x}",
        "paper/figure.png": "not really an image",
    }))
    assert [(item.path, item.content) for item in files] == [
        ("paper/main.tex", r"\begin{document}x\end{document}"),
    ]


def test_source_archive_reader_rejects_path_traversal():
    archive = _tar_bytes({"../outside.tex": r"x = 1"})
    with pytest.raises(ValueError, match="caminho inseguro"):
        fulltext.read_tex_source_archive(archive)


def test_paper_source_exposes_pages_and_tex_without_duplicate_parsing():
    source = fulltext.PaperSource(
        arxiv_id="2608.11111",
        pdf_pages=("first page", "second page"),
        tex_files=(fulltext.TexFile(path="main.tex", content="x = 1"),),
        tex_status="available",
    )
    assert source.pages == {1: "first page", 2: "second page"}
    assert source.tex == {"main.tex": "x = 1"}
    assert "[AI-RADAR PAGE 2]\nsecond page" in source.full_text


def test_docling_extractor_keeps_page_provenance_without_the_real_dependency():
    calls = []

    class Document:
        pages = {1: object(), 2: object()}

        def export_to_text(self, **kwargs):
            calls.append(("export", kwargs))
            return f"page {kwargs['page_no']} " + "x" * 300

    class Converter:
        def convert(self, stream, **kwargs):
            calls.append(("convert", stream, kwargs))
            return type("Result", (), {"document": Document()})()

    extractor = fulltext.DoclingPdfExtractor(
        converter=Converter(),
        stream_factory=lambda **kwargs: type("Stream", (), kwargs)(),
    )
    extracted = extractor.extract(b"pdf", "2608.11111")

    assert extracted.method == "docling"
    assert extracted.pages[0].startswith("page 1")
    exports = [call for call in calls if call[0] == "export"]
    assert [call[1]["page_no"] for call in exports] == [1, 2]
    assert all(call[1]["traverse_pictures"] is True for call in exports)


def test_docling_configuration_falls_back_to_pypdf_and_records_why():
    class Broken:
        name = "docling"

        def extract(self, content, arxiv_id):
            raise RuntimeError("model unavailable")

    class Working:
        name = "pypdf"

        def extract(self, content, arxiv_id):
            return fulltext.PdfExtraction(("x" * 600,), method="pypdf")

    extracted = fulltext.FallbackPdfExtractor(Broken(), Working()).extract(
        b"pdf", "2608.11111")

    assert extracted.method == "pypdf"
    assert extracted.fallback_from == "docling"
    assert extracted.fallback_reason == "RuntimeError"


def test_fetch_paper_source_marks_missing_tex_as_unavailable(monkeypatch):
    monkeypatch.setattr(fulltext, "PdfReader",
                        lambda stream: type("R", (), {
                            "pages": [Page("A" * 600)]})())

    class MissingSource(Response):
        status_code = 404
        content = b"not found"

    def get(url, **kwargs):
        return Response() if "/pdf/" in url else MissingSource()

    source = fulltext.fetch_paper_source("2608.11111", get=get)
    assert source.tex_status == "unavailable"
    assert source.tex_files == ()


def test_fetch_paper_source_marks_unsafe_tex_archive_as_rejected(monkeypatch):
    monkeypatch.setattr(fulltext, "PdfReader",
                        lambda stream: type("R", (), {
                            "pages": [Page("A" * 600)]})())

    class UnsafeSource(Response):
        status_code = 200
        content = _tar_bytes({"../outside.tex": r"x = 1"})

    def get(url, **kwargs):
        return Response() if "/pdf/" in url else UnsafeSource()

    source = fulltext.fetch_paper_source("2608.11111", get=get)
    assert source.tex_status == "rejected"
    assert source.tex_files == ()
