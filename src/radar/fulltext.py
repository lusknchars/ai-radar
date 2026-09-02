"""Aquisicao segura do PDF e da fonte TeX oficial do arXiv."""
from __future__ import annotations

import gzip
import io
import re
import tarfile
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Literal

import httpx
from pypdf import PdfReader

MAX_PDF_BYTES = 30 * 1024 * 1024
MAX_TEXT_CHARS = 240_000
MAX_SOURCE_ARCHIVE_BYTES = 20 * 1024 * 1024
MAX_SOURCE_FILE_BYTES = 2 * 1024 * 1024
MAX_SOURCE_TEXT_BYTES = 6 * 1024 * 1024
MAX_SOURCE_FILES = 500
_MODERN_ARXIV_ID = re.compile(r"^\d{4}\.\d{4,5}$")
PAGE_MARKER = "[AI-RADAR PAGE {page}]"
TexStatus = Literal["not_requested", "available", "unavailable", "rejected"]


@dataclass(frozen=True)
class TexFile:
    path: str
    content: str


@dataclass(frozen=True)
class PaperSource:
    arxiv_id: str
    pdf_pages: tuple[str, ...]
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


def _pdf_pages(arxiv_id: str, *, get) -> tuple[str, ...]:
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
    pages = PdfReader(io.BytesIO(content)).pages
    extracted = tuple((page.extract_text() or "").strip() for page in pages)
    if len("\n\n".join(extracted)) < 500:
        raise ValueError(f"PDF de {arxiv_id} nao produziu texto suficiente")
    return extracted


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


def fetch_full_text(arxiv_id: str, *, get=httpx.get) -> str:
    _validate_arxiv_id(arxiv_id)
    return PaperSource(
        arxiv_id=arxiv_id,
        pdf_pages=_pdf_pages(arxiv_id, get=get),
    ).full_text


def fetch_paper_source(arxiv_id: str, *, get=httpx.get) -> PaperSource:
    _validate_arxiv_id(arxiv_id)
    pages = _pdf_pages(arxiv_id, get=get)
    response = get(
        f"https://arxiv.org/src/{arxiv_id}",
        headers={"User-Agent": "ai-radar/0.1 (paper report)"},
        timeout=90.0,
        follow_redirects=True,
    )
    if getattr(response, "status_code", 200) == 404:
        return PaperSource(
            arxiv_id=arxiv_id, pdf_pages=pages, tex_status="unavailable")
    response.raise_for_status()
    try:
        tex_files = read_tex_source_archive(response.content)
    except ValueError:
        return PaperSource(
            arxiv_id=arxiv_id, pdf_pages=pages, tex_status="rejected")
    return PaperSource(
        arxiv_id=arxiv_id,
        pdf_pages=pages,
        tex_files=tex_files,
        tex_status="available" if tex_files else "unavailable",
    )
