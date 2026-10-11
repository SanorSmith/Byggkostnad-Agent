-- Byggkostnad Agent schema.
-- vector(1024) must equal EMBEDDING_DIM (voyage-3). Changing the embedding
-- model means changing this column and re-embedding every chunk.

create extension if not exists vector;

create table price_index (
  id            bigserial primary key,
  table_id      text        not null,
  series_key    text        not null,
  building_type text,
  cost_class    text        not null,
  period        date        not null,
  value         numeric(12,2) not null,
  base_year     text,
  source_url    text        not null,
  ingested_at   timestamptz not null default now(),
  unique (table_id, series_key, period)
);
create index on price_index (cost_class, period);
create index on price_index (building_type, cost_class, period);

create table documents (
  id           bigserial primary key,
  source_url   text        not null unique,
  title        text,
  raw_text     text        not null,
  content_hash text        not null,
  fetched_at   timestamptz not null default now()
);

create table doc_chunks (
  id              bigserial primary key,
  document_id     bigint not null references documents(id) on delete cascade,
  chunk_index     int    not null,
  text            text   not null,
  token_count     int,
  embedding       vector(1024) not null,
  embedding_model text   not null,
  created_at      timestamptz not null default now(),
  unique (document_id, chunk_index)
);
create index on doc_chunks using hnsw (embedding vector_cosine_ops);

create table eval_runs (
  id               bigserial primary key,
  run_at           timestamptz not null default now(),
  git_sha          text,
  recall_at_5      numeric(4,3),
  numeric_accuracy numeric(4,3),
  groundedness     numeric(4,3),
  notes            text
);

create table query_log (
  id           bigserial primary key,
  asked_at     timestamptz not null default now(),
  question     text not null,
  tools_called jsonb,
  answer       text,
  latency_ms   int
);

-- Supabase exposes the public schema over its REST API with the anon key.
-- The app connects as the database owner through DATABASE_URL, so enabling
-- RLS with no policies closes the REST path without affecting the app.
alter table price_index enable row level security;
alter table documents   enable row level security;
alter table doc_chunks  enable row level security;
alter table eval_runs   enable row level security;
alter table query_log   enable row level security;
