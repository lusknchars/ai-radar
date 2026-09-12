"""Private, double-opt-in signup service. Run separately from the static site."""
from __future__ import annotations

import os
import re
import secrets
import sqlite3
import time
from contextlib import contextmanager
from hashlib import sha256
from html import escape
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from starlette.concurrency import run_in_threadpool

from .resend import ResendClient

GENERIC = 'Check your inbox for a confirmation link. If you recently requested one, use that email.'
EMAIL = re.compile(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?\.[A-Za-z]{2,63}")


class SignupStore:
    """Short-lived confirmation requests only; Resend owns the subscriber list."""
    def __init__(self, path: Path):
        self.path = path.resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with self.connection() as conn:
            conn.executescript((Path(__file__).parent / 'subscription_schema.sql').read_text())
        self.path.chmod(0o600)

    @contextmanager
    def connection(self):
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def request(self, email: str, ip: str, now: int) -> str | None:
        token = secrets.token_urlsafe(32)
        keys = [('email:' + sha256(email.encode()).hexdigest(), 1, 600),
                ('ip:' + sha256(ip.encode()).hexdigest(), 5, 3600)]
        with self.connection() as conn:
            conn.execute('BEGIN IMMEDIATE')
            conn.execute('DELETE FROM signup_requests WHERE expires <= ?', (now,))
            conn.execute('DELETE FROM signup_limits WHERE expires <= ?', (now,))
            for key, limit, window in keys:
                row = conn.execute('SELECT count FROM signup_limits WHERE key=?', (key,)).fetchone()
                if row and row['count'] >= limit:
                    return None
            for key, limit, window in keys:
                conn.execute(
                    'INSERT INTO signup_limits VALUES (?, 1, ?) '
                    'ON CONFLICT(key) DO UPDATE SET count=count+1', (key, now + window),
                )
            conn.execute('DELETE FROM signup_requests WHERE email=?', (email,))
            conn.execute('INSERT INTO signup_requests(token_hash,email,expires) VALUES (?, ?, ?)',
                         (sha256(token.encode()).hexdigest(), email, now + 86400))
        return token

    def confirm(self, token: str, subscribe, now: int) -> str:
        key = sha256(token.encode()).hexdigest()
        with self.connection() as conn:
            conn.execute('BEGIN IMMEDIATE')
            row = conn.execute('SELECT * FROM signup_requests WHERE token_hash=?', (key,)).fetchone()
            if not row or row['expires'] <= now:
                raise ValueError('This confirmation link has expired. Please subscribe again.')
            if row['status'] == 'confirmed':
                return 'Your subscription is already confirmed.'
            if row['status'] == 'processing' and row['lease_until'] > now:
                return 'Confirmation is in progress. Please try again in a minute.'
            conn.execute("UPDATE signup_requests SET status='processing',lease_until=? WHERE token_hash=?",
                         (now + 120, key))
            email = row['email']
        try:
            subscribe(email)
        except Exception:
            with self.connection() as conn:
                conn.execute("UPDATE signup_requests SET status='pending',lease_until=0 WHERE token_hash=?", (key,))
            raise
        with self.connection() as conn:
            # Remove the address immediately after confirmation. The token hash
            # prevents a replay from re-subscribing someone who later opts out.
            conn.execute("UPDATE signup_requests SET status='confirmed',email='',lease_until=0 WHERE token_hash=?", (key,))
        return 'You are subscribed. Look out for the next weekly Paperraft email.'


def page(title: str, body: str, *, turnstile: bool = False) -> HTMLResponse:
    script = ('<script src="https://challenges.cloudflare.com/turnstile/v0/api.js" async defer></script>'
              if turnstile else '')
    return HTMLResponse(
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<title>{escape(title)} · Paperraft</title>'
        '<style>body{background:#eee;color:#111;font:16px/1.6 system-ui;margin:0}'
        'main{max-width:540px;margin:8vh auto;padding:24px}input[type=email]{display:block;'
        'box-sizing:border-box;width:100%;padding:12px;font:inherit;margin:8px 0 20px}'
        'button{display:block;margin:20px 0;padding:12px 20px;background:#cb2957;color:white;'
        'border:0;font:inherit;cursor:pointer}a{color:#a41c43}:focus-visible{outline:3px solid #cb2957}</style>'
        f'{script}</head><body><main><p>Paperraft</p><h1>{escape(title)}</h1>{body}</main></body></html>',
        headers={'Cache-Control': 'no-store', 'Referrer-Policy': 'no-referrer',
                 'X-Content-Type-Options': 'nosniff', 'X-Frame-Options': 'DENY',
                 'Content-Security-Policy': "default-src 'self'; style-src 'unsafe-inline'; "
                 "script-src https://challenges.cloudflare.com; frame-src https://challenges.cloudflare.com; "
                 "connect-src 'self' https://challenges.cloudflare.com; form-action 'self'; base-uri 'none'; frame-ancestors 'none'"},
    )


def create_app(*, provider=None, verify_challenge=None, clock=time.time) -> FastAPI:
    origin = os.environ.get('RADAR_SIGNUP_ORIGIN', '').rstrip('/')
    sender = os.environ.get('RADAR_EMAIL_FROM', '')
    segment = os.environ.get('RESEND_SEGMENT_ID', '')
    site_key = os.environ.get('TURNSTILE_SITE_KEY', '')
    secret = os.environ.get('TURNSTILE_SECRET_KEY', '')
    path = Path(os.environ.get('RADAR_SUBSCRIBER_DB') or '~/.local/share/ai-radar/signup.db').expanduser()
    repository = Path(__file__).resolve().parents[2]
    if path.resolve().is_relative_to(repository):
        raise ValueError('RADAR_SUBSCRIBER_DB must be outside the public repository')
    parsed = urlsplit(origin)
    if (parsed.scheme != 'https' or not parsed.netloc or parsed.path
            or parsed.query or parsed.fragment or parsed.username or parsed.password):
        raise ValueError('RADAR_SIGNUP_ORIGIN must be an HTTPS origin without a path')
    if not all((sender, segment, site_key, secret)):
        raise ValueError('Configure the sending address, Resend segment, and Turnstile keys')
    if provider is None and not os.environ.get('RESEND_API_KEY'):
        raise ValueError('RESEND_API_KEY is required')
    store = SignupStore(path)

    def with_provider(operation):
        client = provider or ResendClient(os.environ.get('RESEND_API_KEY', ''))
        try:
            return operation(client)
        finally:
            if provider is None:
                client.close()

    def challenge(token: str) -> bool:
        if not token or len(token) > 2048:
            return False
        if verify_challenge is not None:
            return verify_challenge(token)
        result = httpx.post('https://challenges.cloudflare.com/turnstile/v0/siteverify',
                            data={'secret': secret, 'response': token}, timeout=10)
        result.raise_for_status()
        verdict = result.json()
        return verdict.get('success') is True and verdict.get('hostname') == parsed.hostname

    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    async def form(request: Request) -> dict[str, str]:
        if request.headers.get('content-type', '').split(';')[0] != 'application/x-www-form-urlencoded':
            raise HTTPException(415, 'Use the signup form')
        if request.headers.get('origin') not in (None, origin):
            raise HTTPException(403, 'Submit from the signup page')
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > 4096:
                raise HTTPException(413, 'Form is too large')
        try:
            fields = parse_qs(body.decode(), max_num_fields=8)
        except (ValueError, UnicodeError):
            raise HTTPException(400, 'Invalid form')
        return {k: v[0] for k, v in fields.items() if len(v) == 1}

    @app.get('/health')
    def health():
        return {'status': 'ok'}

    @app.get('/subscribe')
    def signup():
        return page('A weekly reading list',
                    '<p>Up to five AI papers for engineers. Free to subscribe.</p>'
                    '<form method="post" action="/subscribe">'
                    '<label for="email">Email address</label>'
                    '<input id="email" name="email" type="email" maxlength="254" required autocomplete="email">'
                    '<label><input name="consent" type="checkbox" value="yes" required> '
                    'Send me the weekly Paperraft newsletter. I can unsubscribe at any time.</label>'
                    f'<div class="cf-turnstile" data-sitekey="{escape(site_key)}"></div>'
                    '<button type="submit">Send confirmation link</button></form>'
                    '<p>Resend delivers our emails and stores confirmed subscriptions. '
                    'Unconfirmed requests expire after 24 hours. '
                    'Cloudflare Turnstile helps prevent automated signups.</p>', turnstile=True)

    @app.post('/subscribe')
    async def subscribe(request: Request):
        fields = await form(request)
        email = fields.get('email', '').strip().lower()
        if len(email) > 254 or not EMAIL.fullmatch(email) or fields.get('consent') != 'yes':
            raise HTTPException(400, 'Enter a valid email and agree to receive the newsletter')
        try:
            if not await run_in_threadpool(challenge, fields.get('cf-turnstile-response', '')):
                raise HTTPException(400, 'Please complete the signup check again')
            token = await run_in_threadpool(store.request, email,
                                           request.client.host if request.client else 'unknown', int(clock()))
            if token:
                await run_in_threadpool(with_provider, lambda client: client.send_confirmation(
                    email, sender, origin + '/confirm?token=' + token,
                    'signup-' + sha256(token.encode()).hexdigest(),
                ))
        except (RuntimeError, httpx.HTTPError):
            raise HTTPException(503, 'Email delivery is unavailable. Please try again later.')
        return page('Check your inbox', f'<p>{GENERIC}</p>')

    @app.get('/confirm')
    def confirmation(token: str = ''):
        if not re.fullmatch(r'[A-Za-z0-9_-]{43}', token):
            raise HTTPException(400, 'Invalid confirmation link')
        # GET never subscribes: email scanners routinely follow links.
        return page('Confirm your subscription', '<form method="post" action="/confirm">'
                    f'<input type="hidden" name="token" value="{escape(token)}">'
                    '<button type="submit">Confirm weekly emails</button></form>')

    @app.post('/confirm')
    async def confirm(request: Request):
        fields = await form(request)
        token = fields.get('token', '')
        if not re.fullmatch(r'[A-Za-z0-9_-]{43}', token):
            raise HTTPException(400, 'Invalid confirmation link')
        try:
            message = await run_in_threadpool(
                store.confirm, token,
                lambda email: with_provider(lambda client: client.subscribe(email, segment)), int(clock()),
            )
        except ValueError as exc:
            return page('Link expired', f'<p>{escape(str(exc))}</p><a href="/subscribe">Subscribe again</a>')
        except (RuntimeError, httpx.HTTPError):
            raise HTTPException(503, 'Confirmation is unavailable. Please try this link again later.')
        return page('Subscription confirmation', f'<p>{escape(message)}</p>')

    return app
