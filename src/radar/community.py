"""Public configuration and markup for persistent, GitHub-backed discussions."""
from dataclasses import dataclass
from html import escape
import json
from pathlib import Path
import re
from urllib.parse import urlencode


@dataclass(frozen=True)
class CommunityConfig:
    repository: str
    repository_id: str
    category: str
    category_id: str
    embedded: bool = False

    def __post_init__(self):
        if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', self.repository):
            raise ValueError('Invalid community repository')
        if not self.category.strip() or len(self.category) > 100:
            raise ValueError('Invalid community category')
        for value in (self.repository_id, self.category_id):
            if not re.fullmatch(r'[A-Za-z0-9_=-]+', value):
                raise ValueError('Invalid GitHub community ID')
        if not isinstance(self.embedded, bool):
            raise ValueError('Community embedded setting must be a boolean')

    @property
    def forum_url(self):
        return f'https://github.com/{self.repository}/discussions'

    @property
    def sign_in_url(self):
        return 'https://github.com/login?' + urlencode({
            'return_to': f'/{self.repository}/discussions',
        })


def load_community_config(repository: str, path: Path | None = None):
    path = path or Path(__file__).resolve().parents[2] / 'content/community.json'
    if not path.exists():
        return None
    config = CommunityConfig(**json.loads(path.read_text()))
    # Forks must explicitly configure their own community.
    return config if config.repository == repository else None


def discussion_term(arxiv_id: str) -> str:
    if not re.fullmatch(r'\d{4}\.\d{4,5}', arxiv_id):
        raise ValueError('Discussion requires a canonical arXiv ID')
    return f'arXiv {arxiv_id}'


def discussion_search(config: CommunityConfig, arxiv_id: str) -> str:
    return config.forum_url + '?' + urlencode({
        'discussions_q': f'"{discussion_term(arxiv_id)}"',
    })


def render_paper_discussion(config: CommunityConfig, arxiv_id: str, asset_url: str) -> str:
    term = discussion_term(arxiv_id)
    embed = ''
    if config.embedded:
        embed = (
            '<div class="paper-discussion-widget" '
            f'data-repository="{escape(config.repository)}" '
            f'data-repository-id="{escape(config.repository_id)}" '
            f'data-category="{escape(config.category)}" '
            f'data-category-id="{escape(config.category_id)}" '
            f'data-term="{escape(term)}">'
            '<button class="community-load" type="button">Load discussion</button>'
            '<p class="community-status" role="status" aria-live="polite">'
            'Read the discussion here, then sign in with GitHub to comment.</p>'
            '<div class="giscus"></div></div>'
            f'<script defer src="{escape(asset_url)}"></script>'
        )
    else:
        embed = (
            '<p class="community-note">Join the conversation on GitHub. '
            'Use this paper\'s arXiv ID in the title when starting a discussion.</p>'
            f'<p class="community-paper-id">{escape(term)}</p>'
        )
    return (
        '<section id="discussion" class="research-section community-discussion" '
        'aria-labelledby="discussion-title">'
        '<div class="section-head"><h2 id="discussion-title">Discuss this paper</h2>'
        '<p class="sub">Question a claim, compare interpretations, '
        'or share what happened when you tried the method.</p></div>'
        f'{embed}<div class="community-links">'
        f'<a href="{escape(discussion_search(config, arxiv_id))}" target="_blank" '
        'rel="noopener noreferrer">Find this paper on the forum</a>'
        f'<a href="{escape(config.forum_url)}" target="_blank" '
        'rel="noopener noreferrer">Browse all discussions</a></div>'
        '<p class="community-note">Comments are public and separate from Paperraft\'s '
        'research brief. When sharing a result, include the model, hardware, '
        'baseline and a link to your work.</p></section>'
    )


COMMUNITY_SCRIPT = r"""
(() => {
  const host = document.querySelector('.paper-discussion-widget');
  if (!host) return;
  const button = host.querySelector('button');
  const status = host.querySelector('[role="status"]');
  const container = host.querySelector('.giscus');
  let loading = false;
  button.addEventListener('click', () => {
    if (loading) return;
    loading = true;
    button.disabled = true;
    status.textContent = 'Loading the paper discussion…';
    container.replaceChildren();
    const script = document.createElement('script');
    script.src = 'https://giscus.app/client.js';
    script.async = true;
    script.crossOrigin = 'anonymous';
    const values = {
      repo: host.dataset.repository, repoId: host.dataset.repositoryId,
      category: host.dataset.category, categoryId: host.dataset.categoryId,
      mapping: 'specific', term: host.dataset.term, strict: '1',
      reactionsEnabled: '1', emitMetadata: '0', inputPosition: 'top',
      theme: 'light', lang: 'en', loading: 'eager'
    };
    for (const [key, value] of Object.entries(values)) script.dataset[key] = value;
    let settled = false;
    const fail = () => {
      if (settled) return;
      settled = true;
      status.textContent = 'The embedded discussion could not load. You can open the forum below.';
      button.textContent = 'Try loading again';
      button.disabled = false;
      loading = false;
    };
    const timeout = setTimeout(fail, 15000);
    script.onerror = () => { clearTimeout(timeout); fail(); };
    script.onload = () => {
      if (settled) return;
      settled = true;
      clearTimeout(timeout);
      button.hidden = true;
      status.textContent = 'The discussion appears below. GitHub handles sign-in and comments.';
    };
    container.appendChild(script);
  });
})();
"""
