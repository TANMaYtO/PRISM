-- Supabase schema for PRISM
-- Ensure these tables are created in the public schema

CREATE TABLE IF NOT EXISTS reviews (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    repo_owner TEXT NOT NULL,
    repo_name TEXT NOT NULL,
    pr_number INT NOT NULL,
    review_data JSONB NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS benchmarks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    summary_data JSONB NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
