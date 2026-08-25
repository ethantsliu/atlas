# Public hosting

Atlas is a public, read-only website. Visitors need no account and
install nothing. The static build contains the compact atlas and reviewed reading
details; hosted PostgreSQL adds fast full-text search across all collection entries
and recent daily-paper metadata and abstracts. Neither layer publishes or stores
paper PDFs.

The default hosted window is 180 UTC days. `pipeline/sync.py --keep-days N` changes
that window. Pruning affects PostgreSQL only: the dated static JSON and compressed
raw audit remain the durable archive.

## Supabase setup

Supabase is the documented deployment because its free plan currently includes a
dedicated 500 MB PostgreSQL database and Data API. The SQL itself is standard
PostgreSQL; only `db/policy.sql` names Supabase's `anon` and `authenticated` roles.

1. Create a free Supabase project.
2. Copy its direct or session-pooler PostgreSQL connection string. Store it only as
   the GitHub Actions secret `ATLAS_DATABASE_URL`; never put it in a Vite variable.
3. Run the manual `host` workflow in `both` mode. It applies `db/schema.sql` and
   `db/policy.sql`, then uploads the compact corpus index and daily metadata.
4. In repository Actions variables, set `ATLAS_API_URL` to the project origin and
   `ATLAS_KEY` to a publishable `sb_publishable_...` key. A publishable key is
   intentionally visible in the browser. The browser sends it only in `apikey`;
   elevated keys and database credentials never enter the bundle.
5. In repository Pages settings, choose **GitHub Actions** as the source. Run the
   `deploy` workflow. Project Pages uses `/<repository>/` automatically; set the
   optional `ATLAS_BASE_PATH` repository variable for a custom path.
6. After the first manual deployment succeeds, set the repository variable
   `ATLAS_DEPLOY` to `true` to deploy pushes to `main`. Set `ATLAS_FEED` to `true`
   only when the daily scheduled refresh should begin. Until then, both jobs remain
   inert on automatic triggers and can still be run manually.

The deploy workflow runs the complete project check in the same checkout and build
environment as the Pages artifact, so it never relies on a racing check from another
workflow. After Pages publishes, it anonymously verifies the HTML shell, application
module, core, exact paper-bundle byte count and SHA-256, and one reading and feed day
when present. The separate `probe` workflow repeats that check daily and can be run
manually. Set the optional `ATLAS_SITE_URL` repository variable when the public root
uses a custom domain; otherwise the workflow derives the project Pages URL.

The scheduled `feed` workflow syncs only daily PostgreSQL rows after validating the
complete intake. The `deploy` workflow synchronizes the complete corpus index before
publishing the matching site. Without `ATLAS_DATABASE_URL`, either workflow performs
a dry run and continues publishing the static archive.

Corpus synchronization hashes the exact atlas and enriched bibliography artifacts.
An unchanged digest skips the 2,205-row replacement; a changed corpus is replaced in
one transaction, so public readers see either the prior complete index or the new one.

## Security model

- PostgreSQL row-level security is enabled on every public table.
- `anon` and `authenticated` receive `SELECT` and the fixed `search_feed` function
  only. There are no browser grants or policies for insert, update, or delete.
- Both search functions use stored `tsvector` values, parameterized
  `websearch_to_tsquery`, GIN
  indexes, a three-second statement timeout, 256-character query limit, 100-row
  page cap, and 10,000-row offset cap.
- The synchronization credential is read from an environment secret, never accepted
  on the command line, printed, or sent to the frontend.
- The browser validates all returned rows. Daily reads automatically fall back to
  same-origin static JSON; Library search falls back to local title matching if the
  hosted corpus endpoint fails or returns an unknown paper identity.
- Startup accepts only `sb_publishable_...` keys or legacy Supabase JWTs whose
  payload declares the `anon` role and Supabase issuer. Whitespace, control
  characters, arbitrary bearer strings, and elevated key formats fail closed.
- The corpus digest table has row-level security but no public read policy or grant;
  it is synchronization state, not part of the public API.

Run `python pipeline/sync.py --dry-run` to validate local feed projection without a
database. Run `make db-migrate` or `make db-sync` only with
`ATLAS_DATABASE_URL` in the environment.

## Capacity

The hosted tables contain a compact search projection of the 2,205 public collection
entries plus relevance-positive daily metadata, abstracts, scores, and routes. They
contain no structured full readings. The rolling daily window keeps this comfortably
below the free-tier database limit under current volume. Monitor Supabase's database-size dashboard;
the free project becomes read-only at its size limit. Reduce `--keep-days` before
approaching that limit. Static browsing continues if the project is paused or the
database is unavailable.

The large local `data/cache/` directory is a maintainer-only extraction cache and is
gitignored. It is neither deployed nor downloaded by visitors.
