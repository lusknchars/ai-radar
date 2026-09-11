"""Serve the generated site at the same base path as its published links."""
from __future__ import annotations

import argparse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from .config import load_public_config


def preview_handler(root: Path, base_path: str):
    """Mount only the publication directory, preserving nested-page redirects."""
    base = '/' + base_path.strip('/') if base_path.strip('/') else ''

    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(root.resolve()), **kwargs)

        def translate_path(self, path: str) -> str:
            if base and path.startswith(base + '/'):
                path = path[len(base):]
            return super().translate_path(path)

        def send_head(self):
            parsed = urlsplit(self.path)
            if base and parsed.path in ('/', base):
                target = base + '/' + ('?' + parsed.query if parsed.query else '')
                self.send_response(302)
                self.send_header('Location', target)
                self.send_header('Content-Length', '0')
                self.end_headers()
                return None
            if base and not parsed.path.startswith(base + '/'):
                self.send_error(404, 'Page is outside the publication path')
                return None
            return super().send_head()

    return Handler


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--site', type=Path, default=Path('site'))
    parser.add_argument('--port', type=int, default=8766)
    parser.add_argument('--base-path', default=load_public_config().base_path,
                        help='Must match the base path used to generate this site')
    args = parser.parse_args(argv)
    if not (args.site / 'index.html').is_file():
        parser.error('Generate site/index.html before starting the preview')
    server = ThreadingHTTPServer(('127.0.0.1', args.port), preview_handler(args.site, args.base_path))
    print(f'AI Radar preview: http://127.0.0.1:{args.port}{args.base_path}/', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
