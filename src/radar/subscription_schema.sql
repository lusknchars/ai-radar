CREATE TABLE IF NOT EXISTS signup_requests (
    token_hash TEXT PRIMARY KEY,
    email TEXT NOT NULL,
    expires INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending', 'processing', 'confirmed')),
    lease_until INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS signup_limits (
    key TEXT PRIMARY KEY,
    count INTEGER NOT NULL,
    expires INTEGER NOT NULL
);
