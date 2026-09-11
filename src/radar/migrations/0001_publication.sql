CREATE TABLE IF NOT EXISTS collection_runs (
    id INTEGER PRIMARY KEY,
    day TEXT NOT NULL,
    mode TEXT NOT NULL CHECK (mode IN ('live', 'sample')),
    status TEXT NOT NULL CHECK (status IN ('running', 'success', 'partial', 'failed', 'unconfigured')),
    discovered INTEGER NOT NULL DEFAULT 0,
    indexed INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS delivery_outbox (
    id TEXT PRIMARY KEY,
    day TEXT NOT NULL,
    channel TEXT NOT NULL,
    destination_hash TEXT NOT NULL,
    body TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'sent'))
);
CREATE TABLE IF NOT EXISTS delivery_outbox_items (
    outbox_id TEXT NOT NULL REFERENCES delivery_outbox(id),
    arxiv_id TEXT NOT NULL REFERENCES papers(arxiv_id),
    rank INTEGER NOT NULL,
    PRIMARY KEY (outbox_id, arxiv_id)
);
