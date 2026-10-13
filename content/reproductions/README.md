# Lab reproductions

Each `<arxiv_id>.json` links a brief to a [Paper Raft](https://github.com/lusknchars/paper-raft) study.
In a Paper Raft study, independent agents reimplement the paper's methods, run them against a fixed yardstick
and review each other's code. The publisher loads a matching file while rendering and adds a
"Reproduced in Paper Raft" section to the brief.

A reproduction covers only the scope it states. `limits` is required and must say what was not checked, for
example stand-in data or experiments left out. A reproduction never changes editorial status, validation tiers,
claims or the "Independent tests" section. Those still follow the deep-report gate. Copy the numbers in
`summary` from the study's published results, and set `checked_at` to the date of the runs.
