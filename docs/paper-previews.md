# Paper previews and skill downloads

Each archive entry and research page links directly to its skill ZIP. The ZIP contains SKILL.md and evidence.json. Its description is a quoted YAML scalar and its archive timestamps are fixed so unchanged evidence produces unchanged downloads.

Research pages display the first three actual PDF pages in a native HTML/CSS/JavaScript stack. Click, Enter, Space or the next/previous controls cycle pages. Left/right arrow keys also work while focus is inside the preview. The source link follows the selected PDF page. Motion respects the system preference.

This is an original implementation of a click-to-cycle stack, not the licensed React Bits Click Stack source. The supplied registry endpoint returned HTTP 401. Paperraft has no React runtime.

To cache previews for newly indexed papers, install Poppler and run:

```sh
.venv/bin/python scripts/build_paper_previews.py
```

Pass `--arxiv-id 2608.21223` to select a paper. Existing caches are skipped. Delete a paper's cache directory to refresh it. Each manifest records the PDF URL and SHA-256 hash. These URLs are unversioned; the hash identifies the bytes used for the preview, while the current external PDF can change. Thumbnails preserve original page content and do not count as evidence extraction.

The script limits downloads to 30 MB and rendering to three pages with a 60-second timeout. It exits nonzero if any requested paper fails, leaving successful caches available. Publication copies cached assets without network calls. Papers without caches retain the original-paper link and skill download, with no fabricated preview.

Browser check against a build served on port 8778:

```sh
uv run --no-project --with playwright python scripts/verify_paper_stack.py
```
