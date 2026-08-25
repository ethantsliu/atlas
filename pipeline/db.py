"""Project public atlas artifacts into hosted PostgreSQL search rows."""

from __future__ import annotations

import json
from datetime import date, timedelta


DAY_SQL = """
insert into public.feed_days (
  date, generated_at, policy_version, query, source_total, fetched_count,
  unique_count, page_count, relevant_count, shortlist_count, complete, synced_at
) values (
  %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now()
)
on conflict (date) do update set
  generated_at = excluded.generated_at,
  policy_version = excluded.policy_version,
  query = excluded.query,
  source_total = excluded.source_total,
  fetched_count = excluded.fetched_count,
  unique_count = excluded.unique_count,
  page_count = excluded.page_count,
  relevant_count = excluded.relevant_count,
  shortlist_count = excluded.shortlist_count,
  complete = excluded.complete,
  synced_at = now()
"""

PAPER_SQL = """
insert into public.feed_papers (
  date, paper_id, position, shortlisted, url, title, abstract, authors,
  categories, primary_category, published, updated, comment, lane,
  relevance_score, relevance_reasons, strong_hits, support_hits,
  interest_score, interest_reasons, topics, tricks, search_vector
) values (
  %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
  %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, to_tsvector('english', %s)
)
"""

CORPUS_SQL = """
insert into public.corpus_papers (
  paper_id, stable_id, collection_id, record_kind, title, authors, categories,
  reading_depth, topics, tricks, search_vector
) values (
  %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, to_tsvector('english', %s)
)
"""

STATE_SQL = """
insert into public.corpus_state (id, digest, paper_count, synced_at)
values (true, %s, %s, now())
on conflict (id) do update set
  digest = excluded.digest,
  paper_count = excluded.paper_count,
  synced_at = now()
"""


def check_day(payload: dict) -> None:
    """Reject incomplete or internally inconsistent hosted projections."""
    source = payload.get("source", {})
    papers = payload.get("papers", [])
    shortlist = payload.get("shortlist_ids", [])
    complete = source.get("complete") is True
    if not complete or source.get("fetched_count") != source.get("source_total"):
        raise ValueError("Hosted sync requires a complete source day")
    if len(papers) != payload.get("relevant_count"):
        raise ValueError("Hosted sync relevant count does not match papers")
    if len(shortlist) != payload.get("shortlist_count"):
        raise ValueError("Hosted sync shortlist count does not match IDs")
    if shortlist != [paper.get("id") for paper in papers[: len(shortlist)]]:
        raise ValueError("Hosted sync shortlist must be the ranked prefix")


def day_values(payload: dict) -> tuple:
    """Return the stable parameter sequence for one feed-day upsert."""
    check_day(payload)
    source = payload["source"]
    return (
        payload["date"],
        payload["generated_at"],
        payload["policy_version"],
        source["query"],
        source["source_total"],
        source["fetched_count"],
        source["unique_count"],
        source["page_count"],
        payload["relevant_count"],
        payload["shortlist_count"],
        source["complete"],
    )


def search_text(paper: dict) -> str:
    """Build the public full-text document from useful discovery fields."""
    fields = [
        paper["title"],
        paper["abstract"],
        *paper["authors"],
        *paper["categories"],
        *paper["relevance"]["strong_hits"],
        *paper["relevance"]["support_hits"],
        *(route["id"] for route in paper["topics"]),
        *(route["id"] for route in paper["tricks"]),
    ]
    return " ".join(value for value in fields if value)


def paper_values(payload: dict) -> list[tuple]:
    """Return parameter rows for every relevance-positive paper in one day."""
    check_day(payload)
    shortlist = set(payload["shortlist_ids"])
    rows = []
    for position, paper in enumerate(payload["papers"]):
        relevance = paper["relevance"]
        interest = paper["interest"]
        rows.append(
            (
                payload["date"],
                paper["id"],
                position,
                paper["id"] in shortlist,
                paper["url"],
                paper["title"],
                paper["abstract"],
                paper["authors"],
                paper["categories"],
                paper["primary_category"],
                paper["published"],
                paper["updated"],
                paper["comment"],
                relevance["lane"],
                relevance["score"],
                relevance["reasons"],
                relevance["strong_hits"],
                relevance["support_hits"],
                interest["score"],
                interest["reasons"],
                json.dumps(paper["topics"], separators=(",", ":")),
                json.dumps(paper["tricks"], separators=(",", ":")),
                search_text(paper),
            )
        )
    return rows


def sync_day(cursor, payload: dict) -> int:
    """Replace one complete day atomically inside the caller transaction."""
    values = day_values(payload)
    rows = paper_values(payload)
    cursor.execute(DAY_SQL, values)
    cursor.execute("delete from public.feed_papers where date = %s", (payload["date"],))
    if rows:
        cursor.executemany(PAPER_SQL, rows)
    return len(rows)


def prune_days(cursor, newest: date, keep_days: int) -> date:
    """Delete hosted days outside the configured rolling search window."""
    if keep_days < 1:
        raise ValueError("Hosted retention must be at least one day")
    cutoff = newest - timedelta(days=keep_days - 1)
    cursor.execute("delete from public.feed_days where date < %s", (cutoff,))
    return cutoff


def sync_days(connection, payloads: list[dict], keep_days: int) -> tuple[int, date]:
    """Sync validated days and enforce rolling retention in one transaction."""
    if not payloads:
        raise ValueError("Hosted sync found no daily artifacts")
    dates = [date.fromisoformat(payload["date"]) for payload in payloads]
    total = 0
    with connection.cursor() as cursor:
        for payload in payloads:
            total += sync_day(cursor, payload)
        cutoff = prune_days(cursor, max(dates), keep_days)
    return total, cutoff


def check_corpus(atlas: dict, enriched: list[dict]) -> None:
    """Reject incomplete or identity-conflicting corpus projections."""
    papers = atlas.get("papers", [])
    expected = atlas.get("meta", {}).get("paper_count")
    paper_ids = [paper.get("id") for paper in papers]
    collection_ids = [paper.get("collection_id") for paper in papers]
    enriched_ids = [paper.get("id") for paper in enriched]
    if expected != len(papers) or len(set(paper_ids)) != len(papers):
        raise ValueError("Hosted corpus count or paper identity is invalid")
    if len(set(collection_ids)) != len(papers):
        raise ValueError("Hosted corpus collection identity is invalid")
    if len(enriched) != len(papers) or set(enriched_ids) != set(collection_ids):
        raise ValueError("Hosted corpus enrichment does not cover every entry")


def corpus_text(paper: dict, enriched: dict) -> str:
    """Build one corpus document from public bibliography and reading fields."""
    reading = paper["reading"]
    abstract = enriched.get("abstract")
    fields = [
        paper["title"],
        abstract if isinstance(abstract, str) else "",
        *paper["authors"],
        *paper["categories"],
        *(route["id"] for route in paper["topics"]),
        *(route["id"] for route in paper["tricks"]),
        reading["problem"],
        reading["approach"],
        reading["evidence"],
        reading["limitations"],
        reading["why_it_matters"],
    ]
    return " ".join(value for value in fields if value)


def corpus_rows(atlas: dict, enriched: list[dict]) -> list[tuple]:
    """Return compact hosted rows for every public collection entry."""
    check_corpus(atlas, enriched)
    details = {paper["id"]: paper for paper in enriched}
    return [
        (
            paper["id"],
            paper.get("stable_id"),
            paper["collection_id"],
            paper["record_kind"],
            paper["title"],
            paper["authors"],
            paper["categories"],
            paper["reading_depth"],
            [route["id"] for route in paper["topics"]],
            [route["id"] for route in paper["tricks"]],
            corpus_text(paper, details[paper["collection_id"]]),
        )
        for paper in atlas["papers"]
    ]


def sync_corpus(connection, atlas: dict, enriched: list[dict], digest: str) -> int:
    """Replace the complete corpus index inside the caller transaction."""
    rows = corpus_rows(atlas, enriched)
    if len(digest) != 64 or any(
        character not in "0123456789abcdef" for character in digest
    ):
        raise ValueError("Hosted corpus digest is invalid")
    with connection.cursor() as cursor:
        cursor.execute("select digest from public.corpus_state where id = true")
        current = cursor.fetchone()
        if current and current[0] == digest:
            return 0
        cursor.execute("delete from public.corpus_papers")
        if rows:
            cursor.executemany(CORPUS_SQL, rows)
        cursor.execute(STATE_SQL, (digest, len(rows)))
    return len(rows)
