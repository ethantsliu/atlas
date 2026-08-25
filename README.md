# Atlas

Community participation follows [CONDUCT.md](CONDUCT.md), and sensitive security or
privacy findings should use the private process in [SECURITY.md](SECURITY.md).
Code and project documentation use the MIT License; [NOTICE](NOTICE) explains the
separate third-party source and dataset rights boundary.

Atlas organizes the 2,202 research-paper records in the
[Ziming paper collection](https://metacircleai.github.io/ziming-paper-collection/collection.html)
as a general research database, together with three non-personal context records.
Account-linked social context is intentionally omitted. Atlas preserves provenance
and reading depth so the interface never presents a title-only inference as a
full-paper conclusion.

## Try the atlas

The atlas is a web app, not a desktop binary. Its intended one-click distribution is
a hosted URL: visitors install nothing and download paper metadata only as they
browse. Docker is not required for local use, tests, or the hosted deployment.

To run the committed static atlas locally, use the CI reference runtime, Node.js 22,
and run:

```bash
npm --prefix web ci
npm --prefix web run dev
```

Open `http://127.0.0.1:5173`. This path needs neither Python nor a database. For the
complete project contract, install Python 3.12 and run:

```bash
python3 -m venv .venv
.venv/bin/pip install -r dev.txt
npm --prefix web exec playwright install chromium firefox webkit
make check PYTHON=.venv/bin/python
```

The database integration suite uses PostgreSQL compiled to WebAssembly, so it also
does not require Docker. A local Docker stack is optional only for maintainers who
want an offline Supabase-compatible service instead of the hosted service.

## Current pipeline

The maintained local and CI environment is Python 3.12 with Node.js 22. The npm
lockfile and exact direct Python requirements, rather than unpinned global packages,
define the supported build inputs.

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python pipeline/collection.py
.venv/bin/python pipeline/arxiv.py --resume
.venv/bin/python pipeline/feed.py --days 4
.venv/bin/python pipeline/extract.py --limit 25
.venv/bin/python pipeline/ocr.py --limit 5
.venv/bin/python pipeline/assign.py
.venv/bin/python pipeline/verify.py
.venv/bin/python pipeline/related.py
.venv/bin/python pipeline/atlas.py
ollama pull all-minilm
make layout PYTHON=.venv/bin/python
npm --prefix web ci
npm --prefix web run build
.venv/bin/python pipeline/validate.py
```

The production build defaults to origin-root hosting. For a static deployment below
a path prefix, build with a root-relative base that starts and ends with `/`, for
example `ATLAS_BASE_PATH=/atlas/ npm --prefix web run build`. Both Vite
assets and runtime atlas/detail requests use that base. Invalid or full-URL base
values fail the build instead of producing mixed-origin data requests.

Curated human and research-agent readings live in `data/reviewed/readings/`; they are
source judgments, not disposable build output. Generated data lives in
`data/generated/`. The build accepts paper records and reviewed paper evidence. It has
no workspace or repository-ingestion path. The browser receives the compact projection inside `atlas.json`,
copied to `web/public/data/atlas.json`.

### Semantic graph layout

`pipeline/embed.py` embeds papers, taxonomy markers, and research ideas in one
384-dimensional space. A reviewed paper uses normalized character budgets for
`question` (100), `core_idea` (170), `mechanism` (170), and up to six techniques
(70 combined) so one long field cannot crowd out later signals; title (160) and area
routes (70) remain present. Unreviewed rows fall back to their compact problem and
approach text, while placeholder prose is omitted. Ideas budget title (180), thesis
(250), the first two proposed-method items (250 combined), and routes (80).

The embedding contract is pinned, not merely model-named: Ollama `all-minilm` digest
`1b226e2802dbb772b5fc32a58f103ca1804ef7501331012de126ab22f67475ef`, 384
dimensions, a 256-token request context, `truncate: false`, Ollama 0.13.1, and text
schema `field-budget-v1`. Generation fails if the installed model digest, runtime,
or embedding dimensions differ, or if its context capacity is below 256. Full vectors
stay local; the public layout carries their SHA-256 provenance, not the vectors
themselves.

The published eight neighbors per node are an exact, exhaustive cosine ranking in
the original embedding space, with self-links and canonical or identical-text aliases
excluded. They are discovery suggestions only: a neighbor score is not a citation,
paper dependency, related-work judgment, or evidence of agreement.

UMAP reduces the embeddings to three rounded coordinates with seed 42 and one worker.
The reported trustworthiness and exact-neighbor recall compare those static points
with the original vectors at k=10; they do not measure the positions left on screen by
the browser. The browser starts at the UMAP coordinates, then its semantic mode uses
them as soft anchors while center, charge, and link forces move nodes. Connections
mode removes the semantic anchor and emphasizes graph links. Consequently, final
screen distance is an interactive orientation cue, not a reproducible similarity
score.

Layout quality must clear aggregate trustworthiness 0.90 and k-nearest-neighbor
recall 0.25. The artifact also reports both values for all nodes, research papers,
non-paper context, ideas, and taxonomy markers. Those cohorts are diagnostics over
the same global neighborhood, not separate embeddings. Paper, idea, and taxonomy
cohorts have explicit regression gates; the three context rows are descriptive only.
Alias-equivalent rows are excluded from the comparison.

The region overlay is deliberately coarse orientation, not a claim that the corpus
contains natural classes. Normalized KMeans fits research-paper and idea embeddings,
then assigns every node; taxonomy markers and context entries do not fit the centers.
Each center receives a one-to-one taxonomy label, with descriptive terms, medoid,
spread, and projected radius. The build reports cosine silhouette, mean inertia,
seed-42-versus-seed-43 adjusted Rand stability, minimum region size, and largest
region share. It requires silhouette at least 0, stability at least 0.20, label
similarity at least 0.30, at least 15 nodes per region, and no region above 35% of the
graph. These are artifact-health checks, not validation of a scientific taxonomy.

Run `ollama pull all-minilm` once with the pinned Ollama release, then
`make layout PYTHON=.venv/bin/python` whenever any semantic text, taxonomy, corpus,
or idea changes. Fixed seeds and one-worker UMAP make a pinned environment
repeatable, but a seed alone does not promise bit-identical floating-point output
across transitive numerical libraries, BLAS builds, or hardware. The requirements pin
direct Python dependencies, while artifact hashes bind semantic input, the exact
model contract, actual vector bytes, and reducer configuration. The committed result
is therefore provenance-bound, not a promise that every platform will rebuild the
same bytes. Any vector or layout hash change must be reviewed and committed. Only
rounded coordinates, quality metadata, exact neighbors, and coarse region assignments
are published.

## Daily paper discovery

`pipeline/feed.py` maintains a daily arXiv discovery stream independently from the
fixed reviewed collection. For each UTC date it queries the complete submitted-date
window, paginates until the API's declared total is fetched, and fails rather than
publishing a partial day. It scans every arXiv category before applying the local
policy in `data/source/feed.json`: `cs.LG` and `stat.ML` form the core lane; ML-heavy
AI, language, vision, neurocomputing, and robotics categories form a field lane;
math, statistics, and every other field require explicit ML phrases. This makes
math and statistics selective without creating a category blind spot elsewhere.

Relevance and interest are deliberately separate. Every relevance-positive paper is
published in `data/generated/feed/YYYY-MM-DD.json` and shown under **All relevant**.
The configurable top 40 form the **Interest shortlist**, but ranking never deletes a
relevant row. Each result carries one-decimal scores, phrase-backed reasons, topic and
technique routes, and an arXiv link. The browser loads a lightweight date index and
then one selected day, so daily history does not inflate `atlas.json`.

The complete unfiltered API response for each day is retained as
`data/generated/feed/raw/YYYY-MM-DD.json.gz`. This audit archive proves the declared
source count and permits later policy re-scoring without another download; it is not
copied into the web build. Run `make feed` for a four-day catch-up window, or use
`python3 pipeline/feed.py --date YYYY-MM-DD` for one date. The default date is the
previous UTC day. Page sizes are capped at 2,000 and the CLI refuses request delays
below three seconds. The scheduled `feed` workflow refreshes a four-day window daily,
validates raw/public counts and mirrors, then commits only changed feed artifacts.

The public site can optionally use hosted PostgreSQL for indexed, paginated search
across all 2,205 public collection entries and a rolling 180 days of daily metadata and
abstracts. It remains a read-only static site: visitors have no accounts or personal
workspace, PDFs never enter the database, and hosted failures fall back to
same-origin static data. Supabase's
publishable browser key receives only `SELECT` and bounded search functions; the
database connection used for synchronization remains a server-only Actions secret.
See [docs/HOSTING.md](docs/HOSTING.md) for the one-time deployment and security
setup.

Runtime validation has one common shape owner: `pipeline/shapes.py` checks the
Python idea, brief, and experiment structures mirrored in the browser, while
`pipeline/briefs.py` adds feasibility, lifecycle, research, and portfolio semantics.

The public `atlas.json` is a map-first core: taxonomy, ideas, coverage, semantic
configuration, quality reports, regions, and only the taxonomy and idea rows of the
three node-indexed maps load first. Collection records plus their coordinates,
exact-neighbor rows, and region assignments live in one lazy paper shard. Its
`paper_asset` contract names a content-addressed bundle and pins its SHA-256, byte
length, schema, and 2,205 record count. The browser fetches that immutable file only
when a paper layer or paper-dependent view needs it, verifies the bytes and shape,
and merges the maps only when core and shard ownership is exact.

The checked-in split is approximately 5.35 MB as a canonical full atlas, 0.94 MB for
the initial core (about 222 KB gzip), and 4.41 MB for the paper bundle (about 971 KB
gzip). Each generated core records the bundle's exact raw byte length. Validation
recomputes transfer sizes and caps the core at 1 MiB raw and 250 KiB gzip and the
paper bundle at 4.5 MiB raw and 1 MiB gzip. The reconstructed browser value equals
`data/generated/atlas.json`; splitting changes transfer timing, not the data model.
Publication stages the new shard before switching the core and retains the
immediately preceding valid shard, so an older cached core remains resolvable.

A `full_text` or `verified` paper keeps its reading depth and a safe
`full_reading_path`, but never embeds the structured reading body. `make data`
atomically publishes one byte-identical static detail file per
source reading from `data/reviewed/readings/` to
`web/public/data/readings/`. Each filename includes separate stable-identity and
semantic-content digests, so a revised reading cannot be served from a stale detail
URL. Publication stages every new detail, atomically switches the compact index,
and only then prunes old details; interruption therefore leaves either index version
resolvable. The browser revalidates the core with `no-cache` and lazily fetches
immutable reading details only when a paper modal opens. Vite copies the same assets
into `web/dist` during a production build. This preserves the static, no-server
deployment while keeping initial atlas cost bounded as reading coverage grows. In
a measured historical 132-reading snapshot, embedded bodies accounted for 2.70 MiB
(42.4%) of a 6.38 MiB index; at the same average detail size, full-corpus embedding
would approach 49 MiB.

Install development checks inside the virtual environment with
`.venv/bin/pip install -r dev.txt`, `npm --prefix web ci`, and
`npm --prefix web exec playwright install chromium firefox webkit`.
On a fresh Linux host, Playwright may also require its documented system packages.
Run `make PYTHON=.venv/bin/python check` for the portable, non-publishing project
contract. It reconstructs the
atlas and related-work rows deterministically in memory, reusing stored timestamps,
so stale artifacts fail without first being overwritten. The preflight ignores
`web/dist`, which is an uncommitted build product. It then lints and compiles Python,
runs Python and frontend tests with a conservative 50% whole-pipeline line-coverage
floor, checks formatting, compiles the production UI, runs Playwright/axe smoke
checks at phone, tablet, and desktop widths, and validates the artifacts including
`web/dist`. The Python architecture suite enforces one semantic word per authored
source file or folder; 600 lines per pipeline Python or non-test web source module;
three words per pipeline or test Python function; 180 lines per pipeline Python
function; and acyclic internal pipeline imports. `web/src/lib/names.test.ts`
separately uses the TypeScript compiler AST to enforce three-word and 180-line
limits for named functions, methods, and assigned arrows; it does not claim a
TypeScript import-cycle gate. Core pure domain modules currently sit well above
that aggregate floor; command orchestration and network adapters account for most
uncovered lines. This freshness check compares data directly and therefore works
even when the checkout has no Git `HEAD`. Run `make data` after intentional source
or reading changes, then `make check`; its `enrich` prerequisite reapplies the
current collection and override state without making new API batches. Run
`python3 pipeline/arxiv.py --resume` when new arXiv abstracts actually need fetching.
Use `make refresh-data` to rebuild paper-derived artifacts from reviewed sources.

The full-text source inventory classifies arXiv, OpenReview, direct-PDF, publisher, audited-override, and manual-review routes. Contextual collection entries such as documentation, social posts, workshop indexes, repositories, and videos are preserved but explicitly excluded from the paper-reading denominator. Audited source corrections live in `data/source/overrides.json`; the upstream collection snapshot is never silently edited.

Idea-level competitor revision metadata is normalized separately in
`data/source/competitors.json`, keyed by canonical paper ID so a paper
reused by several briefs is audited once. `version-verified` requires an exact
source version, full ISO source date, source kind, and check date;
`legacy-unversioned` is a visible unresolved state and cannot carry partial version
metadata. Refresh arXiv rows from the official Atom API with
`python3 pipeline/refresh.py --checked-at YYYY-MM-DD`. The
updater retains manually audited official-proceedings and OpenReview rows, refuses
title/ID mismatches, and never manufactures a day from a year-only venue record.

## Evidence levels

- `metadata`: title, URL, collection tags, and curator note only.
- `abstract`: bibliographic metadata and abstract were read by the pipeline.
- `full_text`: the paper body was extracted and a structured reading was completed.
- `verified`: a structured reading was checked against the cited passages.
- `context`: a non-paper collection entry retained for provenance and excluded from
  paper synthesis and reading-completion requirements.

The long-running reading workflow must move every paper to `full_text` or `verified` before the corpus-wide synthesis is considered complete. `data/generated/progress.json` is the authoritative coverage ledger.

Two fixed, non-overlapping queues coordinate parallel agents without shifting paper
ownership between runs. `reading_queue.json` separates reader-ready papers from
those still awaiting extraction. `verification_queue.json` then separates unread
papers, readings that need attribution or structured-novelty repairs, readings that
still need an independent passage/competitor review, and verified readings. Each
review item carries explicit reasons; a thin competitor panel remains reviewable
even if another reviewer has already added verification lineage.

Artifact retrieval and readable-text extraction are tracked separately.
`full_text_ok` normally means at least 85% of document pages contain usable extracted
text; `partial_text` records the exact pages that require direct source inspection or
a later OCR pass. A partial extract stays outside the full-text coverage numerator
and cannot silently become a structured reading.

Two exact OpenReview records use audited, page-preserving Google Scholar HTML
conversions because the official PDF routes present an access challenge. Each raw
HTML artifact, ordered page text, origin forum ID, and both hashes are pinned and
validated. These third-party conversions omit raster figure pixels; their readings
state that limitation and do not infer plot coordinates or visual trends. PDF-only
OCR and visual page-gap exceptions do not apply to HTML artifacts.

An exact-revision exception exists only for visually confirmed non-content leaves.
`data/source/gaps.json` records the stable ID, PDF SHA-256, page count,
complete extraction-gap set, per-page `blank`/`divider`/`non-content`
classification, auditor, date, and evidence. When every identity field matches,
the same 85% gate is applied to content pages and the index stores separate
`content_*` metrics plus the audit digest. Native `missing_text_pages`,
`pages_with_text`, and `text_coverage_ratio` are never erased or inflated. Any PDF
hash, page-count, or missing-page-set drift invalidates the exception and restores
the native classification. Run `python3 pipeline/extract.py --audit-existing`
to apply or revoke these derived audit fields on cached extracts.

Rasterized papers labeled `needs_ocr` can be recovered locally with
`pipeline/ocr.py`. The adapter renders and OCRs only pages that lack usable
native text, preserves every readable native page, and reruns the same quality gate.
It requires Ghostscript (`gs`) and Tesseract (`tesseract`) on `PATH`; on macOS, for
example, install them with `brew install ghostscript tesseract`. Use
`--include-partial` only after inspecting a partial record's missing-page list.

## Design goals

- Explore ideas by research topic, reusable technique, paper, or evidence level.
- Rank every idea with an auditable one-decimal feasibility score.
- Compare topics and techniques in a density heatmap, then inspect publication time, overall and topic-level evidence depth, research-area distribution, full-text coverage, the feasibility frontier, score distribution, and reusable-technique footprint.
- Keep paper evidence one click away from every claim.
- Make weak mappings visible through confidence and provenance instead of hiding uncertainty.
- Prefer compact, direct technical writing in research briefs.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for module boundaries and invariants and [docs/RELATED.md](docs/RELATED.md) for the per-paper arXiv/OpenReview review standard. The coverage ledger is deliberately honest: the current 2,185-paper reading gate is satisfied, and any future supported paper without a page-anchored competitive reading will make it false again.
