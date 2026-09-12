# Equation editions

These files pin a small selection of equations to a specific arXiv HTML version.
They add Paperraft explanations, symbol definitions, objectives, and links to
the paper's supporting discussion. They are editorial reading aids, separate
from full reports and the research-page evidence gate.

For each edition, retain the fetched HTML SHA-256 and date. Copy LaTeX and
sanitized MathML from `radar.arxiv_html.parse_arxiv_html`, preserve the source
equation numbers, and verify all equation and evidence anchors against the
original page. Write explanations in plain text. Distinguish identities,
assumptions, estimates, simulation results, and measured results.

The publisher loads a matching `<arxiv_id>.json` while rendering. The loader
checks the paper/version relationship, duplicate anchors, and sanitized MathML.
It does not establish the factual correctness of editorial prose. Review that
prose against the cited passages before committing an edition. No network or
model calls occur during publication; an edition does not promote editorial
status or populate PDF-linked claims.

The first edition selects equations (3) and (6) from
[2608.21223v1](https://arxiv.org/html/2608.21223v1), checked on 2026-09-12.
The methods section supports the algebraic interpretation; the energy section
distinguishes post-layout simulation from the estimated comparator.
