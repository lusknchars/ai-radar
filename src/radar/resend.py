"""Resend transport. Subscriber details never enter the public research store."""
from __future__ import annotations

import httpx


class ResendClient:
    def __init__(self, api_key: str, *, transport=None):
        if not api_key:
            raise ValueError('RESEND_API_KEY is required')
        self.client = httpx.Client(
            base_url='https://api.resend.com', timeout=20,
            headers={'Authorization': f'Bearer {api_key}'}, transport=transport,
        )

    def close(self) -> None:
        self.client.close()

    def request(self, method: str, path: str, **kwargs) -> dict:
        response = self.client.request(method, path, **kwargs)
        if not response.is_success:
            # Provider errors can contain recipient details. Do not log the response body.
            raise RuntimeError(f'Resend request failed with HTTP {response.status_code}')
        return response.json()

    def send_confirmation(self, email: str, sender: str, url: str, key: str) -> None:
        from html import escape
        result = self.request('POST', '/emails', headers={'Idempotency-Key': key}, json={
            'from': sender, 'to': [email], 'subject': 'Confirm your Paperraft subscription',
            'html': '<p>You requested the weekly Paperraft newsletter.</p>'
                    f'<p><a href="{escape(url)}">Confirm subscription</a></p>'
                    '<p>This link expires in 24 hours. If you did not request it, ignore this email.</p>',
            'text': f'Confirm your weekly Paperraft subscription: {url}\n'
                    'This link expires in 24 hours. Ignore it if you did not request it.',
        })
        if not result.get('id'):
            raise RuntimeError('Resend did not acknowledge the confirmation email')

    def subscribe(self, email: str, segment_id: str) -> None:
        from urllib.parse import quote
        path = '/contacts/' + quote(email, safe='')
        response = self.client.get(path)
        if response.status_code == 404:
            self.request('POST', '/contacts', json={
                'email': email, 'unsubscribed': False, 'segments': [{'id': segment_id}],
            })
        elif response.is_success:
            self.request('PATCH', path, json={'unsubscribed': False})
            self.request('POST', path + '/segments/' + quote(segment_id, safe=''))
        else:
            raise RuntimeError(f'Resend contact lookup failed with HTTP {response.status_code}')

    def create_draft(self, issue, *, sender: str, segment_id: str) -> str:
        if issue.preview:
            raise ValueError('Sample previews cannot be uploaded as broadcasts')
        # A stable name permits recovery after a process dies between POST and
        # saving the ID. Callers serialize this operation using the workflow group.
        after = None
        while True:
            params = {'limit': 100}
            if after:
                params['after'] = after
            page = self.request('GET', '/broadcasts', params=params)
            rows = page.get('data', [])
            for row in rows:
                if row.get('name') == issue.key:
                    return row['id']
            if not page.get('has_more'):
                break
            if not rows or rows[-1]['id'] == after:
                raise RuntimeError('Broadcast pagination did not advance')
            after = rows[-1]['id']
        result = self.request('POST', '/broadcasts', json={
            'name': issue.key, 'segment_id': segment_id, 'from': sender,
            'subject': issue.subject, 'html': issue.html, 'text': issue.text,
            'send': False,
        })
        return result['id']
