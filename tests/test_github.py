import json
from datetime import date
from pathlib import Path

import pytest

from radar.github import GitHubClient, build_search_url, parse_search
from radar.models import Paper

PAYLOAD = json.loads((Path(__file__).parent / "fixtures" / "github_search.json").read_text())

PAPER = Paper(arxiv_id="2210.17323", title="GPTQ", abstract="",
              authors=["Elias Frantar"], categories=["cs.LG"], published="2022-10-31")
TODAY = date(2026, 8, 27)


def test_search_url_quotes_the_arxiv_id_and_scopes_to_readme():
    url = build_search_url("2210.17323")
    assert "%222210.17323%22" in url
    assert "in%3Areadme" in url or "in:readme" in url


def test_parse_extracts_the_fields_the_signal_needs():
    repos = parse_search(PAYLOAD)
    assert len(repos) == 4
    assert repos[0].full_name == "IST-DASLab/gptq"
    assert repos[0].owner == "IST-DASLab"
    assert repos[0].stars == 2360


def test_parse_of_empty_result_returns_empty():
    assert parse_search({"total_count": 0, "items": []}) == []


def test_signal_counts_total_and_independent_separately():
    s = GitHubClient(fetch=lambda url: PAYLOAD).signal_for(PAPER, today=TODAY)
    assert s.total_impls == 4
    # IST-DASLab/gptq e pego como oficial (mais antigo E mais estrelado)
    assert s.independent_impls == 3


def test_signal_sums_stars_across_all_repos():
    s = GitHubClient(fetch=lambda url: PAYLOAD).signal_for(PAPER, today=TODAY)
    assert s.stars_total == 2360 + 322 + 10 + 4


def test_velocity_counts_only_repos_created_in_the_last_14_days():
    s = GitHubClient(fetch=lambda url: PAYLOAD).signal_for(PAPER, today=TODAY)
    assert s.velocity_14d == 1        # so recente/fresh-impl, de 2026-08-20


def test_velocity_window_boundary_is_inclusive():
    payload = {"total_count": 1, "items": [
        {"full_name": "a/b", "owner": {"login": "a"},
         "stargazers_count": 1, "created_at": "2026-08-13T00:00:00Z"}]}
    s = GitHubClient(fetch=lambda url: payload).signal_for(PAPER, today=TODAY)
    assert s.velocity_14d == 1


def test_repo_older_than_the_window_is_not_counted_as_velocity():
    payload = {"total_count": 1, "items": [
        {"full_name": "a/b", "owner": {"login": "a"},
         "stargazers_count": 1, "created_at": "2026-08-12T00:00:00Z"}]}
    s = GitHubClient(fetch=lambda url: payload).signal_for(PAPER, today=TODAY)
    assert s.velocity_14d == 0


def test_no_results_yields_a_zeroed_signal():
    s = GitHubClient(fetch=lambda url: {"total_count": 0, "items": []}).signal_for(
        PAPER, today=TODAY)
    assert s == type(s)(total_impls=0, independent_impls=0, velocity_14d=0,
                        stars_total=0, citations=0)


def test_classifications_are_exposed_for_the_audit_trail():
    client = GitHubClient(fetch=lambda url: PAYLOAD)
    _, classifications = client.signal_with_repos(PAPER, today=TODAY)
    flagged = [c for c in classifications if c.is_author]
    assert len(flagged) == 1
    assert flagged[0].reason == "mais_antigo_e_mais_estrelado"


def test_citations_default_to_zero_when_not_supplied():
    s = GitHubClient(fetch=lambda url: PAYLOAD).signal_for(PAPER, today=TODAY)
    assert s.citations == 0
