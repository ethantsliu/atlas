import { PGlite } from "@electric-sql/pglite";
import { readFile } from "node:fs/promises";
import { afterAll, beforeAll, describe, expect, it } from "vitest";

let database: PGlite;

async function readSql(name: string): Promise<string> {
  return readFile(new URL(`../../../db/${name}.sql`, import.meta.url), "utf8");
}

beforeAll(async () => {
  database = new PGlite();
  await database.exec("create role anon; create role authenticated;");
  await database.exec(await readSql("schema"));
  await database.exec(await readSql("policy"));
});

afterAll(async () => database.close());

describe("hosted PostgreSQL", () => {
  it("grants read without writes", async () => {
    const result = await database.query<{
      read: boolean;
      write: boolean;
      search: boolean;
      corpus_read: boolean;
      corpus_search: boolean;
      state_read: boolean;
    }>(`
      select
        has_table_privilege('anon', 'feed_days', 'select') as read,
        has_table_privilege('anon', 'feed_days', 'insert') as write,
        has_function_privilege(
          'anon',
          'search_feed(text,text,boolean,date,date,integer,integer)',
          'execute'
        ) as search,
        has_table_privilege('anon', 'corpus_papers', 'select') as corpus_read,
        has_function_privilege(
          'anon', 'search_corpus(text,integer,integer)', 'execute'
        ) as corpus_search,
        has_table_privilege('anon', 'corpus_state', 'select') as state_read
    `);

    expect(result.rows[0]).toEqual({
      read: true,
      write: false,
      search: true,
      corpus_read: true,
      corpus_search: true,
      state_read: false,
    });
  });

  it("runs bounded full-text search", async () => {
    await database.exec(`
      insert into feed_days values (
        '2026-08-21', '2026-08-22Z', 'v1', 'q', 1, 1, 1, 1, 1, 1, true
      );
      insert into feed_papers (
        date, paper_id, position, shortlisted, url, title, abstract, authors,
        categories, primary_category, published, updated, comment, lane,
        relevance_score, relevance_reasons, strong_hits, support_hits,
        interest_score, interest_reasons, topics, tricks, search_vector
      ) values (
        '2026-08-21', '2608.00001', 0, true,
        'https://arxiv.org/abs/2608.00001', 'Evolutionary RL environments',
        'Synthetic environment generation', array['Ada'], array['cs.LG'],
        'cs.LG', '', '', '', 'core', 9.0, array['core'],
        array['reinforcement learning'], array[]::text[], 8.0, array['novel'],
        '[]', '[]', to_tsvector('english', 'evolutionary environment generation')
      );
    `);
    const result = await database.query<{ title: string; total_count: number }>(
      "select title, total_count from search_feed('environment')",
    );

    expect(result.rows).toEqual([
      { title: "Evolutionary RL environments", total_count: 1 },
    ]);
  });

  it("runs corpus full-text search", async () => {
    await database.exec(`
      insert into corpus_papers (
        paper_id, stable_id, collection_id, record_kind, title, authors,
        categories, reading_depth, topics, tricks, search_vector
      ) values (
        'paper-1', 'arxiv:2608.00001', 1, 'paper',
        'Evolutionary environment design', array['Ada'], array['cs.LG'],
        'full_text', array['environment-design'], array['evolutionary-search'],
        to_tsvector('english', 'evolutionary synthetic RL environment design')
      );
    `);
    const result = await database.query<{ paper_id: string; total_count: number }>(
      "select paper_id, total_count from search_corpus('synthetic environment')",
    );

    expect(result.rows).toEqual([{ paper_id: "paper-1", total_count: 1 }]);
  });
});
