begin;

create table if not exists public.feed_days (
  date date primary key,
  generated_at timestamptz not null,
  policy_version text not null,
  query text not null,
  source_total integer not null check (source_total >= 0),
  fetched_count integer not null check (fetched_count >= 0),
  unique_count integer not null check (unique_count >= 0),
  page_count integer not null check (page_count >= 0),
  relevant_count integer not null check (relevant_count >= 0),
  shortlist_count integer not null check (shortlist_count >= 0),
  complete boolean not null,
  synced_at timestamptz not null default now(),
  check (fetched_count <= source_total),
  check (unique_count <= fetched_count),
  check (shortlist_count <= relevant_count),
  check (not complete or fetched_count = source_total)
);

create table if not exists public.feed_papers (
  date date not null references public.feed_days(date) on delete cascade,
  paper_id text not null,
  position integer not null check (position >= 0),
  shortlisted boolean not null,
  url text not null check (url ~ '^https://arxiv\.org/abs/'),
  title text not null,
  abstract text not null,
  authors text[] not null,
  categories text[] not null,
  primary_category text not null,
  published text not null,
  updated text not null,
  comment text not null,
  lane text not null check (lane in ('core', 'field', 'math-stat', 'adjacent')),
  relevance_score numeric(3, 1) not null check (
    relevance_score between 0 and 10
  ),
  relevance_reasons text[] not null,
  strong_hits text[] not null,
  support_hits text[] not null,
  interest_score numeric(3, 1) not null check (interest_score between 0 and 10),
  interest_reasons text[] not null,
  topics jsonb not null check (jsonb_typeof(topics) = 'array'),
  tricks jsonb not null check (jsonb_typeof(tricks) = 'array'),
  search_vector tsvector not null,
  primary key (date, paper_id),
  unique (date, position)
);

create table if not exists public.corpus_papers (
  paper_id text primary key,
  stable_id text,
  collection_id integer not null check (collection_id > 0),
  record_kind text not null check (record_kind in ('paper', 'non_paper_context')),
  title text not null,
  authors text[] not null,
  categories text[] not null,
  reading_depth text not null check (
    reading_depth in ('metadata', 'abstract', 'full_text', 'verified', 'context')
  ),
  topics text[] not null,
  tricks text[] not null,
  search_vector tsvector not null
);

create table if not exists public.corpus_state (
  id boolean primary key default true check (id),
  digest text not null check (digest ~ '^[0-9a-f]{64}$'),
  paper_count integer not null check (paper_count >= 0),
  synced_at timestamptz not null default now()
);

create index if not exists feed_papers_search_idx
  on public.feed_papers using gin (search_vector);
create index if not exists feed_papers_rank_idx
  on public.feed_papers (date desc, interest_score desc, position);
create index if not exists feed_papers_lane_idx
  on public.feed_papers (lane, date desc);
create index if not exists corpus_papers_search_idx
  on public.corpus_papers using gin (search_vector);
create index if not exists corpus_papers_order_idx
  on public.corpus_papers (collection_id);

create or replace function public.search_feed(
  search_query text,
  lane_filter text default null,
  shortlist_only boolean default false,
  date_from date default null,
  date_to date default null,
  page_size integer default 30,
  page_offset integer default 0
)
returns table (
  date date,
  paper_id text,
  shortlisted boolean,
  url text,
  title text,
  abstract text,
  authors text[],
  categories text[],
  primary_category text,
  published text,
  updated text,
  comment text,
  lane text,
  relevance_score numeric,
  relevance_reasons text[],
  strong_hits text[],
  support_hits text[],
  interest_score numeric,
  interest_reasons text[],
  topics jsonb,
  tricks jsonb,
  rank real,
  total_count bigint
)
language sql
stable
security invoker
set search_path = ''
set statement_timeout = '3s'
as $$
  with terms as (
    select
      websearch_to_tsquery('english', left(trim(search_query), 256)) as value
  ),
  matched as (
    select
      paper.*,
      ts_rank_cd(paper.search_vector, terms.value, 32)::real as match_rank
    from public.feed_papers as paper
    cross join terms
    where length(trim(search_query)) >= 2
      and paper.search_vector @@ terms.value
      and (lane_filter is null or paper.lane = lane_filter)
      and (not coalesce(shortlist_only, false) or paper.shortlisted)
      and (date_from is null or paper.date >= date_from)
      and (date_to is null or paper.date <= date_to)
  )
  select
    matched.date,
    matched.paper_id,
    matched.shortlisted,
    matched.url,
    matched.title,
    matched.abstract,
    matched.authors,
    matched.categories,
    matched.primary_category,
    matched.published,
    matched.updated,
    matched.comment,
    matched.lane,
    matched.relevance_score,
    matched.relevance_reasons,
    matched.strong_hits,
    matched.support_hits,
    matched.interest_score,
    matched.interest_reasons,
    matched.topics,
    matched.tricks,
    matched.match_rank,
    count(*) over () as total_count
  from matched
  order by
    matched.match_rank desc,
    matched.interest_score desc,
    matched.date desc,
    matched.position
  limit least(greatest(coalesce(page_size, 30), 1), 100)
  offset least(greatest(coalesce(page_offset, 0), 0), 10000);
$$;

create or replace function public.search_corpus(
  search_query text,
  page_size integer default 100,
  page_offset integer default 0
)
returns table (
  paper_id text,
  rank real,
  total_count bigint
)
language sql
stable
security invoker
set search_path = ''
set statement_timeout = '3s'
as $$
  with terms as (
    select websearch_to_tsquery(
      'english', left(trim(search_query), 256)
    ) as value
  ),
  matched as (
    select
      paper.paper_id,
      paper.collection_id,
      ts_rank_cd(paper.search_vector, terms.value, 32)::real as match_rank
    from public.corpus_papers as paper
    cross join terms
    where length(trim(search_query)) >= 2
      and paper.search_vector @@ terms.value
  )
  select
    matched.paper_id,
    matched.match_rank,
    count(*) over () as total_count
  from matched
  order by matched.match_rank desc, matched.collection_id
  limit least(greatest(coalesce(page_size, 100), 1), 100)
  offset least(greatest(coalesce(page_offset, 0), 0), 10000);
$$;

alter table public.feed_days enable row level security;
alter table public.feed_papers enable row level security;
alter table public.corpus_papers enable row level security;
alter table public.corpus_state enable row level security;

revoke all on function public.search_feed(
  text, text, boolean, date, date, integer, integer
) from public;
revoke all on function public.search_corpus(text, integer, integer) from public;

commit;
