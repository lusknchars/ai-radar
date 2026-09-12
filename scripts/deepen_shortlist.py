#!/usr/bin/env python3
"""Deepen up to three actionable papers from the live publication database."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from radar.config import load_database_path
from radar.research_round import select_shortlist
from radar.store import Store
from gerar_relatorio import main as generate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', type=Path, default=load_database_path())
    parser.add_argument('--limit', type=int, default=3)
    parser.add_argument('--plan', action='store_true')
    args = parser.parse_args()
    today = datetime.now(timezone.utc).date()
    store = Store(args.db)
    try:
        store.init_schema()
        selected = select_shortlist(store.site_data(today).pontos,
                                    reports_dir=Path('reports'), limit=args.limit)
    finally:
        store.close()
    plan = {'as_of': today.isoformat(), 'rule': 'Actionable briefs; recent papers first, varied research areas; skip existing reports.',
            'selected': [{'arxiv_id': p.arxiv_id, 'title': p.titulo, 'family': p.familia} for p in selected]}
    print(json.dumps(plan, indent=2), flush=True)
    if args.plan or not selected:
        return 0
    Path('data').mkdir(exist_ok=True)
    Path('data/latest-research-round.json').write_text(json.dumps(plan, indent=2) + '\n')
    targets = [arg for p in selected for arg in ('--arxiv-id', p.arxiv_id)]
    return generate([*targets, '--db', str(args.db), '--continue-on-error'])


if __name__ == '__main__':
    raise SystemExit(main())
