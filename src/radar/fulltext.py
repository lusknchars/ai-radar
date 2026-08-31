"""Extracao de texto do PDF oficial do arXiv."""
from __future__ import annotations

import io
import re

import httpx
from pypdf import PdfReader

MAX_PDF_BYTES = 30 * 1024 * 1024
MAX_TEXT_CHARS = 240_000
_MODERN_ARXIV_ID = re.compile(r"^\d{4}\.\d{4,5}$")


def fetch_full_text(arxiv_id: str, *, get=httpx.get) -> str:
    if not _MODERN_ARXIV_ID.fullmatch(arxiv_id):
        raise ValueError(f"arxiv_id invalido para download: {arxiv_id!r}")
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
    text = "\n\n".join(page.extract_text() or "" for page in pages).strip()
    if len(text) < 500:
        raise ValueError(f"PDF de {arxiv_id} nao produziu texto suficiente")
    if len(text) > MAX_TEXT_CHARS:
        text = text[:MAX_TEXT_CHARS] + "\n\n[TEXTO TRUNCADO PELO RADAR]"
    return text
