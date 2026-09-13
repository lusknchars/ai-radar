
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
