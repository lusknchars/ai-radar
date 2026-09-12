"""Build one reusable weekly email from stored briefs, without model calls."""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from html import escape
from pathlib import Path

from .briefs_english import is_portuguese
from .config import PublicConfig, load_database_path, load_public_config
from .selection import recent_papers
from .site_data import SiteData
from .store import Store

UNSUBSCRIBE = "{{{RESEND_UNSUBSCRIBE_URL}}}"


@dataclass(frozen=True)
class WeeklyIssue:
    key: str
    week_start: str
    week_end: str
    paper_ids: list[str]
    subject: str
    html: str
    text: str
    preview: bool


def build_issue(data: SiteData, week_end: date, config: PublicConfig, *,
                preview: bool = False) -> WeeklyIssue | None:
    start = week_end - timedelta(days=6)
    if not preview:
        status = data.collection
        if (status.mode != "live" or status.outcome != "success"
                or not status.last_success
                or date.fromisoformat(status.last_success) < week_end):
            raise ValueError("A successful live collection covering this week is required")
    selected = recent_papers(data.pontos, week_end)[:5]
    if not selected:
        return None
    if not preview and any(is_portuguese(p.resumo + " " + p.porque) for p in selected):
        raise ValueError("Translate the selected briefs into English before preparing an issue")
    label = "[SAMPLE PREVIEW] " if preview else ""
    subject = f"{label}Paperraft: {len(selected)} papers worth reading · {week_end.isoformat()}"
    intro = ("Sample preview. This is not a current research newsletter." if preview else
             "This week's research for engineers building with AI. "
             "Claims below come from paper abstracts and have not been independently reproduced.")
    parts, text = [], [subject, "", intro, f"{start} to {week_end}", ""]
    for p in selected:
        url = f"{config.site_url.rstrip('/')}/papers/{p.arxiv_id}/"
        original = f"https://arxiv.org/abs/{p.arxiv_id}"
        signal = f"{p.independent_impls} independent implementations. Counts do not establish quality."
        parts.append(
            '<article style="padding:24px 0;border-top:1px solid #ddd">'
            f'<small>Published {escape(p.publicado)}</small>'
            f'<h2 style="font-size:21px;line-height:1.35">{escape(p.titulo)}</h2>'
            f'<p>{escape(p.resumo)}</p><p>{escape(p.porque)}</p>'
            f'<p style="font-size:12px">{escape(signal)}</p>'
            f'<a href="{escape(url)}" style="color:#cb2957">Read the research page</a>'
            f' · <a href="{escape(original)}">Original paper</a></article>'
        )
        text.extend([p.titulo, p.resumo, p.porque, signal, url, original, ""])
    html = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1"></head>'
        '<body style="margin:0;background:#eee;color:#111;font:16px/1.65 Arial,sans-serif">'
        '<main style="max-width:620px;margin:auto;padding:32px 24px">'
        f'<h1>Paperraft</h1><p>{escape(intro)}</p><p>{start} to {week_end}</p>'
        + ''.join(parts)
        + '<footer style="padding-top:24px;border-top:1px solid #ddd">'
        f'<p><a href="{escape(config.site_url)}">Research archive</a> · '
        f'<a href="{UNSUBSCRIBE}">Unsubscribe</a></p></footer></main></body></html>'
    )
    text.extend([f"Unsubscribe: {UNSUBSCRIBE}"])
    return WeeklyIssue(
        key=f"ai-radar-week-{week_end.isoformat()}", week_start=start.isoformat(),
        week_end=week_end.isoformat(), paper_ids=[p.arxiv_id for p in selected],
        subject=subject, html=html, text='\n'.join(text), preview=preview,
    )


def write_issue(issue: WeeklyIssue, root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{issue.key}.json"
    payload = json.dumps(asdict(issue), indent=2, ensure_ascii=False) + '\n'
    if path.exists() and path.read_text(encoding="utf-8") != payload:
        raise ValueError("This week's issue is frozen; review the existing draft before replacing it")
    path.write_text(payload, encoding="utf-8")
    path.with_suffix('.html').write_text(issue.html, encoding="utf-8")
    path.with_suffix('.txt').write_text(issue.text, encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', type=Path, default=load_database_path())
    parser.add_argument('--out', type=Path, default=Path('newsletter'))
    parser.add_argument('--week-ending', type=date.fromisoformat)
    parser.add_argument('--preview', action='store_true', help='Allow labelled sample previews')
    args = parser.parse_args(argv)
    today = date.today()
    end = args.week_ending or (today - timedelta(days=today.weekday() + 1))
    if end > today and not args.preview:
        parser.error('The issue cannot include a future week')
    store = Store(args.db)
    try:
        store.init_schema()
        data = store.site_data(end)
        # Collection health is current, while paper eligibility uses the issue window.
        from dataclasses import replace
        data = replace(data, collection=store.collection_status(today.isoformat()))
        issue = build_issue(data, end, load_public_config(), preview=args.preview)
        if issue is None:
            print('No qualifying papers this week. No email draft created.')
            return 0
        print(write_issue(issue, args.out))
        return 0
    except ValueError as exc:
        print(f'Newsletter not prepared: {exc}')
        return 1
    finally:
        store.close()


if __name__ == '__main__':
    raise SystemExit(main())
