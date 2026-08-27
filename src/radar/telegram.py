"""Envio do push. Transporte injetado para manter o modulo testavel offline."""
from __future__ import annotations

from typing import Callable

API_BASE = "https://api.telegram.org"


def build_endpoint(token: str) -> str:
    return f"{API_BASE}/bot{token}/sendMessage"


def send(text: str, token: str, chat_id: str, post: Callable[[str, dict], object]) -> bool:
    if not token:
        raise ValueError("token do Telegram ausente")
    if not chat_id:
        raise ValueError("chat_id do Telegram ausente")
    if not text.strip():
        return False      # silencio e resultado valido
    try:
        post(build_endpoint(token), {"chat_id": chat_id, "text": text,
                                     "disable_web_page_preview": False})
        return True
    except Exception:
        # Falha de entrega nao derruba o pipeline: o markdown ja foi gravado.
        return False
