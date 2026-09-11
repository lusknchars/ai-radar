from contextlib import contextmanager
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from threading import Thread

import pytest

from radar.preview import preview_handler


@contextmanager
def serve(root, base):
    server = ThreadingHTTPServer(('127.0.0.1', 0), preview_handler(root, base))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_port
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def get(port, path, method='GET'):
    connection = HTTPConnection('127.0.0.1', port)
    try:
        connection.request(method, path)
        response = connection.getresponse()
        return response.status, dict(response.getheaders()), response.read().decode()
    finally:
        connection.close()


@pytest.mark.parametrize('base', ['/ai-radar', '/another-fork', ''])
def test_article_links_assets_and_back_link_resolve_at_publication_mount(tmp_path, base):
    root = tmp_path / 'site'
    article = root / 'papers/2601.12164'
    article.mkdir(parents=True)
    (root / 'assets').mkdir()
    (root / 'index.html').write_text(f'<a href="{base}/papers/2601.12164/">Read paper</a>')
    (article / 'index.html').write_text(f'<h1>Research page</h1><a href="{base}/#acervo">Back</a>')
    (article / 'index.json').write_text('{"arxiv_id":"2601.12164"}')
    (root / 'assets/site.css').write_text('body{color:black}')
    (tmp_path / 'private.txt').write_text('must not be served')
    with serve(root, base) as port:
        if base:
            assert get(port, '/')[1]['Location'] == base + '/'
            assert get(port, base, 'HEAD')[1]['Location'] == base + '/'
        assert get(port, base + '/')[0] == 200
        assert get(port, base + '/papers/2601.12164/')[0] == 200
        redirect = get(port, base + '/papers/2601.12164')
        assert redirect[0] == 301
        assert redirect[1]['Location'] == base + '/papers/2601.12164/'
        assert get(port, base + '/papers/2601.12164/index.json')[0] == 200
        assert get(port, base + '/assets/site.css?v=1')[0] == 200
        assert get(port, base + '/#acervo')[0] == 200
        assert get(port, base + '/../private.txt')[0] == 404
        assert get(port, base + '/missing-article/')[0] == 404
