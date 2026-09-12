"""Select a small, varied set of actionable briefs for full-paper reading."""
from pathlib import Path


def select_shortlist(points, *, reports_dir: Path, limit: int = 3):
    if not 1 <= limit <= 3:
        raise ValueError("A research round supports 1–3 deep reports")
    pending = [p for p in points if p.pratica in {"adotar", "testar"}
               and not (reports_dir / f"{p.arxiv_id}.json").exists()]
    pending.sort(key=lambda p: (p.publicado, p.score, p.arxiv_id), reverse=True)
    selected, families = [], set()
    for point in pending:
        if point.familia not in families:
            selected.append(point)
            families.add(point.familia)
        if len(selected) == limit:
            return selected
    chosen = {p.arxiv_id for p in selected}
    return (selected + [p for p in pending if p.arxiv_id not in chosen])[:limit]
