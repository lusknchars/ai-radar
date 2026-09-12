import httpx
import pytest

from radar import cli


def test_arxiv_retries_transient_failure_with_backoff(monkeypatch):
    waits = []
    responses = iter([503, 429, 200])
    monkeypatch.setattr(cli.time, 'sleep', waits.append)
    def get(url, **kwargs):
        return httpx.Response(next(responses), text='<feed/>', request=httpx.Request('GET', url))
    monkeypatch.setattr(cli.httpx, 'get', get)
    assert cli._arxiv_fetch('https://export.arxiv.org/api/query') == '<feed/>'
    assert waits == [3, 6]


def test_arxiv_does_not_retry_invalid_request(monkeypatch):
    monkeypatch.setattr(cli.time, 'sleep', lambda _: pytest.fail('unexpected retry'))
    monkeypatch.setattr(cli.httpx, 'get', lambda url, **kw: httpx.Response(
        400, request=httpx.Request('GET', url)))
    with pytest.raises(httpx.HTTPStatusError):
        cli._arxiv_fetch('https://export.arxiv.org/api/query')
