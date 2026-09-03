"""Aquisicao segura do PDF e da fonte TeX oficial do arXiv."""
from __future__ import annotations

import gzip
import hashlib
import io
import re
import tarfile
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Literal, Protocol

import httpx
from pypdf import PdfReader

MAX_PDF_BYTES = 30 * 1024 * 1024
MAX_PDF_PAGES = 200
MAX_TEXT_CHARS = 240_000
MAX_SOURCE_ARCHIVE_BYTES = 20 * 1024 * 1024
MAX_SOURCE_FILE_BYTES = 2 * 1024 * 1024
MAX_SOURCE_TEXT_BYTES = 6 * 1024 * 1024
MAX_SOURCE_FILES = 500
_MODERN_ARXIV_ID = re.compile(r"^\d{4}\.\d{4,5}$")
PAGE_MARKER = "[AI-RADAR PAGE {page}]"
TexStatus = Literal["not_requested", "available", "unavailable", "rejected"]
PdfExtractionMethod = Literal["pypdf", "docling"]


@dataclass(frozen=True)
class PdfExtraction:
    """Texto por pagina e proveniencia do adaptador que o produziu."""

    pages: tuple[str, ...]
    method: PdfExtractionMethod
    fallback_from: PdfExtractionMethod | None = None
    fallback_reason: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "pages", tuple(self.pages))


class PdfExtractor(Protocol):
    """Seam estreito para trocar o parser sem tocar na aquisicao arXiv."""

    name: PdfExtractionMethod

    def extract(self, content: bytes, arxiv_id: str) -> PdfExtraction: ...


class PyPdfExtractor:
    name: PdfExtractionMethod = "pypdf"

    def extract(self, content: bytes, arxiv_id: str) -> PdfExtraction:
        pages = PdfReader(io.BytesIO(content)).pages
        if len(pages) > MAX_PDF_PAGES:
            raise ValueError(
                f"PDF de {arxiv_id} excede {MAX_PDF_PAGES} paginas")
        return PdfExtraction(
            pages=tuple((page.extract_text() or "").strip() for page in pages),
            method=self.name,
        )


class DoclingPdfExtractor:
    """Adaptador opcional para preservar layout, tabelas e leitura por pagina."""

    name: PdfExtractionMethod = "docling"

    def __init__(self, converter=None, stream_factory=None) -> None:
        self._converter = converter
        self._stream_factory = stream_factory

    def _document_converter(self):
        if self._converter is not None:
            return self._converter
        try:
            from docling.document_converter import DocumentConverter
        except ImportError as exc:
            raise RuntimeError(
                "Docling nao esta instalado; rode pip install -e '.[documents]'"
            ) from exc
        self._converter = DocumentConverter()
        return self._converter

    def extract(self, content: bytes, arxiv_id: str) -> PdfExtraction:
        if self._stream_factory is None:
            try:
                from docling.datamodel.base_models import DocumentStream
            except ImportError as exc:
                raise RuntimeError(
                    "Docling nao esta instalado; rode pip install -e '.[documents]'"
                ) from exc
            self._stream_factory = DocumentStream
        stream = self._stream_factory(
            name=f"{arxiv_id}.pdf", stream=io.BytesIO(content))
        result = self._document_converter().convert(
            stream, max_file_size=MAX_PDF_BYTES, max_num_pages=MAX_PDF_PAGES)
        document = result.document
        page_numbers = sorted(document.pages)
        if not page_numbers:
            raise ValueError(f"Docling nao encontrou paginas em {arxiv_id}")
        if page_numbers != list(range(1, len(page_numbers) + 1)):
            raise ValueError(
                f"Docling devolveu paginas nao contiguas em {arxiv_id}")
        pages = tuple(
            document.export_to_text(page_no=page, traverse_pictures=True).strip()
            for page in page_numbers
        )
        return PdfExtraction(pages=pages, method=self.name)


class FallbackPdfExtractor:
    """Tenta o parser rico e registra quando o parser simples assumiu."""

    def __init__(self, primary: PdfExtractor, fallback: PdfExtractor) -> None:
        self.primary = primary
        self.fallback = fallback
        self.name = primary.name

    def extract(self, content: bytes, arxiv_id: str) -> PdfExtraction:
        try:
            return self.primary.extract(content, arxiv_id)
        except Exception as exc:
            extracted = self.fallback.extract(content, arxiv_id)
            return PdfExtraction(
                pages=extracted.pages,
                method=extracted.method,
                fallback_from=self.primary.name,
                fallback_reason=type(exc).__name__,
            )


def build_pdf_extractor(name: str) -> PdfExtractor:
    """Constroi o adaptador configurado; Docling sempre tem fallback local."""
    if name == "pypdf":
        return PyPdfExtractor()
    if name == "docling":
        return FallbackPdfExtractor(DoclingPdfExtractor(), PyPdfExtractor())
    raise ValueError(f"extrator de PDF invalido: {name!r}")


@dataclass(frozen=True)
class TexFile:
    path: str
    content: str


@dataclass(frozen=True)
class PaperSource:
    arxiv_id: str
    pdf_pages: tuple[str, ...]
    pdf_sha256: str = ""
    pdf_extraction_method: PdfExtractionMethod = "pypdf"
    pdf_fallback_from: PdfExtractionMethod | None = None
    pdf_fallback_reason: str | None = None
    tex_files: tuple[TexFile, ...] = ()
    tex_status: TexStatus = "not_requested"

    def __post_init__(self) -> None:
        object.__setattr__(self, "pdf_pages", tuple(self.pdf_pages))
        object.__setattr__(self, "tex_files", tuple(self.tex_files))

    @property
    def pages(self) -> dict[int, str]:
        return dict(enumerate(self.pdf_pages, start=1))

    @property
    def tex(self) -> dict[str, str]:
        return {item.path: item.content for item in self.tex_files}

    @property
    def full_text(self) -> str:
        text = "\n\n".join(
            f"{PAGE_MARKER.format(page=number)}\n{page_text}"
            for number, page_text in self.pages.items()
        )
        if len(text) > MAX_TEXT_CHARS:
            return text[:MAX_TEXT_CHARS] + "\n\n[TEXTO TRUNCADO PELO RADAR]"
        return text


def _validate_arxiv_id(arxiv_id: str) -> None:
    if not _MODERN_ARXIV_ID.fullmatch(arxiv_id):
        raise ValueError(f"arxiv_id invalido para download: {arxiv_id!r}")


def _pdf(arxiv_id: str, *, get, extractor: PdfExtractor) -> tuple[bytes, PdfExtraction]:
    response = get(
        f"https://arxiv.org/pdf/{arxiv_id}",
        headers={"User-Agent": "ai-radar/0.1 (paper report)"},
        timeout=90.0,
        follow_redirects=True,
    )
    response.raise_for_status()
    content = response.content
    if len(content) > MAX_PDF_BYTES:
        raise ValueError(f"PDF de {arxiv_id} excede {MAX_PDF_BYTES} bytes")
    extracted = extractor.extract(content, arxiv_id)
    if len("\n\n".join(extracted.pages)) < 500:
        raise ValueError(f"PDF de {arxiv_id} nao produziu texto suficiente")
    return content, extracted


def _safe_source_path(name: str) -> str:
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"fonte TeX contem caminho inseguro: {name!r}")
    normalized = path.as_posix().lstrip("./")
    if not normalized:
        raise ValueError("fonte TeX contem caminho vazio")
    return normalized


def _gunzip_limited(content: bytes) -> bytes:
    with gzip.GzipFile(fileobj=io.BytesIO(content)) as stream:
        payload = stream.read(MAX_SOURCE_TEXT_BYTES + 1)
    if len(payload) > MAX_SOURCE_TEXT_BYTES:
        raise ValueError("fonte TeX descompactada excede o limite")
    return payload


def read_tex_source_archive(content: bytes) -> tuple[TexFile, ...]:
    """Le arquivos TeX em memoria; nunca extrai nem executa o archive."""
    if len(content) > MAX_SOURCE_ARCHIVE_BYTES:
        raise ValueError("archive da fonte TeX excede o limite")

    try:
        archive = tarfile.open(fileobj=io.BytesIO(content), mode="r:*")
    except (tarfile.ReadError, tarfile.CompressionError):
        try:
            payload = (
                _gunzip_limited(content)
                if content.startswith(b"\x1f\x8b") else content
            )
        except (OSError, EOFError) as exc:
            raise ValueError("fonte TeX compactada e invalida") from exc
        if len(payload) > MAX_SOURCE_FILE_BYTES:
            raise ValueError("arquivo TeX unico excede o limite")
        return (TexFile(path="main.tex", content=payload.decode(
            "utf-8", errors="replace")),)

    files: list[TexFile] = []
    total = 0
    with archive:
        members = archive.getmembers()
        if len(members) > MAX_SOURCE_FILES:
            raise ValueError("archive da fonte TeX contem arquivos demais")
        for member in members:
            if member.isdir():
                if member.name not in {".", "./"}:
                    _safe_source_path(member.name)
                continue
            path = _safe_source_path(member.name)
            if not member.isfile():
                raise ValueError(f"fonte TeX contem entrada insegura: {member.name!r}")
            if PurePosixPath(path).suffix.lower() != ".tex":
                continue
            if member.size > MAX_SOURCE_FILE_BYTES:
                raise ValueError(f"arquivo TeX excede o limite: {path!r}")
            total += member.size
            if total > MAX_SOURCE_TEXT_BYTES:
                raise ValueError("texto TeX total excede o limite")
            stream = archive.extractfile(member)
            if stream is None:
                raise ValueError(f"arquivo TeX ilegivel: {path!r}")
            payload = stream.read(MAX_SOURCE_FILE_BYTES + 1)
            if len(payload) != member.size:
                raise ValueError(f"tamanho inesperado no arquivo TeX: {path!r}")
            files.append(TexFile(
                path=path,
                content=payload.decode("utf-8", errors="replace"),
            ))
    return tuple(sorted(files, key=lambda item: item.path))


def fetch_full_text(
    arxiv_id: str, *, get=httpx.get, extractor: PdfExtractor | None = None,
) -> str:
    _validate_arxiv_id(arxiv_id)
    content, extraction = _pdf(
        arxiv_id, get=get, extractor=extractor or PyPdfExtractor())
    return PaperSource(
        arxiv_id=arxiv_id,
        pdf_pages=extraction.pages,
        pdf_sha256=hashlib.sha256(content).hexdigest(),
        pdf_extraction_method=extraction.method,
        pdf_fallback_from=extraction.fallback_from,
        pdf_fallback_reason=extraction.fallback_reason,
    ).full_text


def fetch_paper_source(
    arxiv_id: str, *, get=httpx.get, extractor: PdfExtractor | None = None,
) -> PaperSource:
    _validate_arxiv_id(arxiv_id)
    content, extraction = _pdf(
        arxiv_id, get=get, extractor=extractor or PyPdfExtractor())
    source_kwargs = {
        "arxiv_id": arxiv_id,
        "pdf_pages": extraction.pages,
        "pdf_sha256": hashlib.sha256(content).hexdigest(),
        "pdf_extraction_method": extraction.method,
        "pdf_fallback_from": extraction.fallback_from,
        "pdf_fallback_reason": extraction.fallback_reason,
    }
    response = get(
        f"https://arxiv.org/src/{arxiv_id}",
        headers={"User-Agent": "ai-radar/0.1 (paper report)"},
        timeout=90.0,
        follow_redirects=True,
    )
    if getattr(response, "status_code", 200) == 404:
        return PaperSource(
            **source_kwargs, tex_status="unavailable")
    response.raise_for_status()
    try:
        tex_files = read_tex_source_archive(response.content)
    except ValueError:
        return PaperSource(
            **source_kwargs, tex_status="rejected")
    return PaperSource(
        **source_kwargs,
        tex_files=tex_files,
        tex_status="available" if tex_files else "unavailable",
    )
