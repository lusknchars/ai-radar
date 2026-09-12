"""Optional bounded discovery. arXiv remains the authority for paper metadata."""
from collections import Counter
from datetime import date, timedelta
import logging
import re
from urllib.parse import urlencode, urlsplit

from .arxiv import ARXIV_ENDPOINT, parse_feed
from .models import Discovery

_log = logging.getLogger(__name__)


def arxiv_id(url: str) -> str | None:
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname not in {"arxiv.org", "www.arxiv.org"}:
        return None
    match = re.fullmatch(r"/(?:abs|pdf|html)/(\d{4}\.\d{4,5})(?:v\d+)?(?:\.pdf)?", parsed.path)
    return match[1] if match else None


class ExaDiscovery:
    def __init__(self, primary, *, search, fetch, today: date, results: int = 10,
                 queries: int = 1, lookback_days: int = 30):
        if not 1 <= results <= 25:
            raise ValueError("RADAR_EXA_RESULTS must be between 1 and 25")
        if not 1 <= queries <= 3 or not 1 <= lookback_days <= 180:
            raise ValueError("Exa requires 1–3 queries and a 1–180 day lookback")
        self.primary, self.search, self.fetch = primary, search, fetch
        self.today, self.results = today, results
        self.queries, self.lookback_days = queries, lookback_days

    def recent(self, scope):
        original = self.primary.recent(scope)
        papers = {paper.arxiv_id: paper for paper in original.papers}
        cuts = Counter(original.cuts)
        start = self.today - timedelta(days=self.lookback_days)
        ids = set()
        for index in range(min(self.queries, max(1, len(scope.terms)))):
            terms = scope.terms[index::self.queries]
            try:
                response = self.search({
                    "query": f"AI research {scope.name}: " + ", ".join(terms),
                    "type": "auto", "category": "research paper",
                    "includeDomains": ["arxiv.org"], "numResults": self.results,
                    "startPublishedDate": f"{start.isoformat()}T00:00:00Z",
                })
                for result in response["results"][:self.results]:
                    candidate = arxiv_id(result.get("url", ""))
                    if candidate:
                        ids.add(candidate)
                    else:
                        cuts["exa_invalid_source"] += 1
            except Exception as error:
                _log.warning("Exa query %s failed: %s, HTTP %s", index + 1,
                             type(error).__name__, getattr(getattr(error, 'response', None), 'status_code', None))
                cuts["exa_search_failed"] += 1
        try:
            ids -= papers.keys()
            if ids:
                url = ARXIV_ENDPOINT + "?" + urlencode({"id_list": ",".join(sorted(ids)), "max_results": len(ids)})
                resolved = parse_feed(self.fetch(url))
                found = set()
                for paper in resolved:
                    if paper.arxiv_id not in ids:
                        continue
                    found.add(paper.arxiv_id)
                    if not set(scope.categories).intersection(paper.categories):
                        cuts["exa_out_of_scope"] += 1
                    elif not start.isoformat() <= paper.published <= self.today.isoformat():
                        cuts["exa_outside_window"] += 1
                    else:
                        papers[paper.arxiv_id] = paper
                cuts["exa_metadata_missing"] += len(ids - found)
        except Exception as error:
            # Never log provider response bodies or credentials. Preserve the
            # primary discovery and mark the collection partial in the caller.
            _log.warning("Exa metadata resolution failed: %s, HTTP %s",
                         type(error).__name__, getattr(getattr(error, 'response', None), 'status_code', None))
            cuts["exa_metadata_failed"] += 1
        return Discovery(papers=list(papers.values()), cuts={k: v for k, v in cuts.items() if v})
