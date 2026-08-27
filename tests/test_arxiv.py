from pathlib import Path

from radar.arxiv import ARXIV_ENDPOINT, ArxivClient, build_query, parse_feed
from radar.config import ScopeConfig

FIXTURE = (Path(__file__).parent / "fixtures" / "arxiv_response.xml").read_text()


def test_endpoint_is_https():
    """Em HTTP a API devolve 301 com corpo vazio; raise_for_status() nao
    levanta em 3xx e httpx nao segue redirect por padrao -- falha silenciosa."""
    assert ARXIV_ENDPOINT.startswith("https://")


def test_query_combines_categories_with_or_and_ands_the_term():
    q = build_query("quantization", ScopeConfig(categories=("cs.LG", "cs.AR"), terms=()))
    assert "cat:cs.LG OR cat:cs.AR" in q
    assert 'abs:"quantization"' in q
    assert " AND " in q


def test_parse_strips_version_from_the_arxiv_id():
    papers = parse_feed(FIXTURE)
    assert papers[0].arxiv_id == "2608.11111"


def test_parse_collapses_whitespace_in_title_and_abstract():
    p = parse_feed(FIXTURE)[0]
    assert p.title == "Fused INT4 Kernels for Ampere Inference"
    assert "  " not in p.abstract
    assert p.abstract.startswith("We present")


def test_parse_extracts_authors_in_order():
    assert parse_feed(FIXTURE)[0].authors == ("Elias Frantar", "Ji Lin")


def test_parse_extracts_all_categories():
    assert parse_feed(FIXTURE)[0].categories == ("cs.LG", "cs.AR")


def test_parse_keeps_published_as_iso_date():
    assert parse_feed(FIXTURE)[0].published == "2026-08-20"


def test_parse_returns_every_entry_without_filtering():
    """O parser nao filtra. Filtro de escopo e responsabilidade do cliente."""
    assert len(parse_feed(FIXTURE)) == 2


def test_empty_feed_returns_empty_list():
    empty = ('<?xml version="1.0" encoding="UTF-8"?>'
             '<feed xmlns="http://www.w3.org/2005/Atom"></feed>')
    assert parse_feed(empty) == []


def test_client_excludes_papers_with_no_category_in_scope():
    seen = []

    def fake_fetch(url):
        seen.append(url)
        return FIXTURE

    scope = ScopeConfig(categories=("cs.LG", "cs.AR"), terms=("quantization",))
    papers = ArxivClient(fetch=fake_fetch, sleep=lambda s: None).recent(scope)
    assert [p.arxiv_id for p in papers] == ["2608.11111"]   # a entrada eess.AS cai fora
    assert len(seen) == 1


CROSS_LISTED = """<?xml version='1.0' encoding='UTF-8'?>
<feed xmlns:arxiv="http://arxiv.org/schemas/atom" xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2608.33333v1</id>
    <published>2026-08-18T00:00:00Z</published>
    <title>Cross-listed Efficiency Work</title>
    <summary>Categoria primaria fora do escopo, secundaria dentro.</summary>
    <author><name>A B</name></author>
    <arxiv:primary_category term="cs.AI"/>
    <category term="cs.AI"/>
    <category term="cs.LG"/>
  </entry>
</feed>"""


def test_client_admits_a_paper_whose_only_in_scope_category_is_secondary():
    """Cross-listing e comum: trabalho de eficiencia costuma ter primaria
    cs.AI e secundaria cs.LG. A descoberta favorece recall de proposito --
    cinco filtros a jusante (termo, sinal do GitHub, portao, piso, teto de 3)
    cuidam da precisao. Este teste distingue interseccao de primary-only;
    o teste acima nao distinguia, porque a entrada descartada da fixture nao
    tem NENHUMA categoria no escopo."""
    scope = ScopeConfig(categories=("cs.LG",), terms=("quantization",))
    papers = ArxivClient(fetch=lambda url: CROSS_LISTED, sleep=lambda s: None).recent(scope)
    assert [p.arxiv_id for p in papers] == ["2608.33333"]


def test_client_unions_terms_and_deduplicates_by_id():
    scope = ScopeConfig(categories=("cs.LG",), terms=("quantization", "sparsity"))
    papers = ArxivClient(fetch=lambda url: FIXTURE, sleep=lambda s: None).recent(scope)
    assert [p.arxiv_id for p in papers] == ["2608.11111"]


def test_client_sleeps_between_calls_for_arxiv_etiquette():
    naps = []
    scope = ScopeConfig(categories=("cs.LG",), terms=("a", "b", "c"))
    ArxivClient(fetch=lambda url: FIXTURE, sleep=naps.append).recent(scope)
    assert len(naps) == 2          # dorme entre chamadas, nao depois da ultima
    assert all(n >= 3 for n in naps)


def test_client_survives_a_term_whose_response_is_empty():
    """Corpo vazio e exatamente o que a API devolve em HTTP simples, e
    ET.fromstring("") levanta ParseError. Sem o parse dentro do try, um unico
    termo ruim derruba a coleta de todos os outros."""
    def fetch(url):
        return "" if "sparsity" in url else FIXTURE

    scope = ScopeConfig(categories=("cs.LG",), terms=("quantization", "sparsity"))
    papers = ArxivClient(fetch=fetch, sleep=lambda s: None).recent(scope)
    assert [p.arxiv_id for p in papers] == ["2608.11111"]


def test_client_survives_a_term_whose_response_is_malformed():
    def fetch(url):
        return "<feed><entry>truncad" if "sparsity" in url else FIXTURE

    scope = ScopeConfig(categories=("cs.LG",), terms=("quantization", "sparsity"))
    papers = ArxivClient(fetch=fetch, sleep=lambda s: None).recent(scope)
    assert [p.arxiv_id for p in papers] == ["2608.11111"]


def test_client_survives_one_failing_term():
    def flaky(url):
        if "sparsity" in url:
            raise RuntimeError("502")
        return FIXTURE

    scope = ScopeConfig(categories=("cs.LG",), terms=("quantization", "sparsity"))
    papers = ArxivClient(fetch=flaky, sleep=lambda s: None).recent(scope)
    assert [p.arxiv_id for p in papers] == ["2608.11111"]
