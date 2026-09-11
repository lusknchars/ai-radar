from urllib.parse import parse_qs, urlsplit

import pytest

pytest.importorskip('fastapi')
from fastapi.testclient import TestClient

from radar.subscriptions import SignupStore, create_app


class FakeProvider:
    def __init__(self):
        self.emails, self.contacts = [], []
        self.fail = False

    def send_confirmation(self, email, sender, url, key):
        self.emails.append((email, url))

    def subscribe(self, email, segment):
        if self.fail:
            raise RuntimeError('unavailable')
        self.contacts.append((email, segment))


@pytest.fixture
def signup(monkeypatch, tmp_path):
    for key, value in {
        'RADAR_SIGNUP_ORIGIN': 'https://signup.example.com',
        'RADAR_EMAIL_FROM': 'radar@example.com', 'RESEND_SEGMENT_ID': 'readers',
        'TURNSTILE_SITE_KEY': 'fake', 'TURNSTILE_SECRET_KEY': 'fake',
        'RADAR_SUBSCRIBER_DB': str(tmp_path / 'private.db'),
    }.items():
        monkeypatch.setenv(key, value)
    now = [100000]
    provider = FakeProvider()
    app = create_app(provider=provider, verify_challenge=lambda t: t == 'valid', clock=lambda: now[0])
    with TestClient(app, base_url='https://signup.example.com') as client:
        yield client, provider, now


def request_signup(client, **changes):
    return client.post('/subscribe', data={
        'email': 'reader@example.com', 'consent': 'yes', 'cf-turnstile-response': 'valid', **changes,
    })


def token(provider):
    return parse_qs(urlsplit(provider.emails[-1][1]).query)['token'][0]


def test_double_opt_in_and_replay_do_not_restore_a_later_unsubscribe(signup):
    client, provider, now = signup
    assert request_signup(client).status_code == 200
    assert provider.contacts == []
    value = token(provider)
    assert client.get('/confirm', params={'token': value}).status_code == 200
    assert provider.contacts == []  # Link scanners cannot opt anyone in.
    assert client.post('/confirm', data={'token': value}).status_code == 200
    assert provider.contacts == [('reader@example.com', 'readers')]
    assert client.post('/confirm', data={'token': value}).status_code == 200
    assert len(provider.contacts) == 1


def test_consent_challenge_rate_limit_and_cross_origin(signup):
    client, provider, now = signup
    assert request_signup(client, consent='no').status_code == 400
    assert request_signup(client, **{'cf-turnstile-response': 'invalid'}).status_code == 400
    assert request_signup(client).status_code == 200
    assert request_signup(client).status_code == 200
    assert len(provider.emails) == 1
    response = client.post('/subscribe', data={'email': 'a@b.com'}, headers={'Origin': 'https://attacker.example'})
    assert response.status_code == 403
    assert client.post('/subscribe', content='x'*5000,
                       headers={'Content-Type': 'application/x-www-form-urlencoded'}).status_code == 413


def test_expired_link_and_provider_failure_are_retryable(signup):
    client, provider, now = signup
    request_signup(client)
    value = token(provider)
    provider.fail = True
    assert client.post('/confirm', data={'token': value}).status_code == 503
    provider.fail = False
    assert client.post('/confirm', data={'token': value}).status_code == 200
    now[0] += 86401
    assert 'expired' in client.post('/confirm', data={'token': value}).text
    assert len(provider.contacts) == 1


def test_confirmation_removes_private_address_from_temporary_store(tmp_path):
    store = SignupStore(tmp_path / 'private.db')
    value = store.request('reader@example.com', '127.0.0.1', 100)
    store.confirm(value, lambda email: None, 101)
    with store.connection() as conn:
        assert conn.execute('SELECT email FROM signup_requests').fetchone()[0] == ''
    assert tmp_path.joinpath('private.db').stat().st_mode & 0o777 == 0o600
