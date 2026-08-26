# Architecture

The atlas has one evidence boundary: a general paper corpus with independently reviewed paper records. It does not scan a local workspace or ingest user repositories.

## Data flow

```text
collection ─► canonical IDs ─► abstracts ─► source inventory ─► full text
                                                               └─► reviewed readings ─► provisional ideas
                                                                                       └─► researched briefs
                                                                                               │
                                                                                               ▼
                                                        compact atlas + progress + static reading details
                                                                  └─► compact hosted corpus search

arXiv metadata stream ─► monthly remote shards ─► likely / possible / outside scope
          │                    │                         └─► no destructive filtering
          │                    └─► resumable 2020-present backfill
          └─► newest day first ─► daily discovery ─► interest rank ─► shortlist
```

## Module boundaries

- `identifiers.py` owns canonical paper identity.
- `ontology.py` performs conservative, phrase-bounded first-pass routing.
- `sources.py` classifies every canonical record and resolves supported document routes.
- `data/source/overrides.json` records audited corrections for malformed source links and explicitly classifies contextual, non-paper entries; upstream collection data remains untouched.
- `identity.py` owns the mutually exclusive PDF/HTML source identity contract.
- `scholar.py` verifies and page-separates the two explicitly audited Scholar HTML
  conversions used when the corresponding OpenReview PDFs are inaccessible.
- `quality.py` owns reusable extraction metrics and exact-revision page-gap promotion.
- `extract.py` retrieves and page-separates supported artifacts; it does not summarize them.
- `ocr.py` is an explicit local fallback that replaces only pages the native
  extractor marked unreadable; it reuses the same quality policy and never promotes
  a record merely because OCR ran.
- `analysis.py` owns extractive previews and compact paper records.
- `assets.py` owns identity-and-content-addressed detail paths,
  byte-identical staging, post-index stale-detail pruning, and
  source/public-copy validation.
- `ledger.py` derives the one authoritative coverage snapshot without shadowing
  the third-party coverage package.
- `assign.py` and `verify.py` derive fixed,
  non-overlapping first-pass and second-pass assignments from canonical IDs; they
  describe work state but never mutate reviewed readings.
- `experiments.py` supplies topic-specific controls and falsifiers without coupling them to orchestration.
- `ideas.py` creates explicitly provisional candidates and auditable screening scores.
- `related.py` purely derives deterministic lexical review queues; orchestration only loads and publishes them.
- `feed.py` owns complete UTC date pagination, raw audit archives, and atomic daily
  publication; it does not modify the reviewed corpus or compact atlas.
- `rank.py` owns the configurable relevance boundary and the separate interest
  ordering. `data/source/feed.json` keeps category and phrase policy inspectable.
- `archive.py` owns deterministic monthly shards and reversible scope lanes;
  `backfill.py` keeps the newest date current before filling historical gaps. The
  release index is sufficient to resume without downloading completed months.
- `feedcheck.py` verifies source totals, raw lineage, ranking order, and byte-identical
  public/build copies. `web/src/lib/feed.ts` independently revalidates the served
  contracts before the `Daily` view renders them.
- `db.py` projects only complete public day payloads into stable database rows;
  it also projects the public corpus into identity-only search results. `sync.py`
  owns transactional, idempotent synchronization and rolling retention;
  `migrate.py` applies reviewed SQL without accepting credentials on the command
  line. `db/schema.sql` is the PostgreSQL contract and `db/policy.sql` is the narrow
  Supabase role policy.
- `web/src/lib/hosted.ts` is the only browser adapter for hosted reads. It validates
  service configuration and every response, while `hooks/feed.ts` owns transparent
  fallback to same-origin static feed artifacts and `hooks/search.ts` owns cancellable
  historical search state.
- `atlas.py` is orchestration only: it composes the modules and atomically publishes artifacts.
- `rules.py` owns small shared contract primitives; `shapes.py` owns common Python
  idea, brief, and experiment runtime shapes mirrored by the browser;
  `readings.py` validates source pins and page evidence; `briefs.py` validates
  feasibility, lifecycle, research, and portfolio semantics;
  `artifacts.py` verifies deterministic ledgers and published copies; `validate.py`
  composes those boundaries without reimplementing them.
- `web/src` separates data loading, graph derivation, portfolio hierarchy, views,
  and detail surfaces. Browser contracts likewise separate generic guards,
  full-reading validation, idea validation, and atlas-level references into
  `guards.ts`, `reading.ts`, `idea.ts`, and `atlas.ts`. `lib/portfolio.ts` is the
  single browser-side owner of program/work-package grouping and
  independent-ranking semantics.

## Evidence invariants

1. Metadata and abstract previews are never described as full-paper readings.
2. Every full reading has page-anchored findings, direct primary-source competitors, and a novelty assessment.
3. `atlas.coverage` is byte-for-byte the semantic snapshot written to `progress.json`.
4. The compact atlas never embeds a `full_reading` body. Only `full_text` and
   `verified` records expose a safe `full_reading_path`; their depth remains in the
   index so filters and graph sizing need no detail fetch.
5. Atlas reading references cover exactly the curated source IDs under
   `data/reviewed/readings/`. Reviewed human and research-agent judgments never live
   under `data/generated/`. Every reviewed reading has one deterministic file under
   `web/public/data/readings/`, every file is byte-identical and semantically equal
   to its source, and no orphan detail is allowed. A production build must copy the
   same exact set into `web/dist`.
6. Unreviewed ideas are labeled screening estimates and receive capped evaluation/novelty factors.
7. Idea ordering uses the published feasibility rubric and stable idea ID only;
   hidden user-specific ranking signals are not part of the data contract.
8. Lexical related-work candidates remain separate from reviewed competitors.
9. Every JSON artifact is atomically replaced. Static reading publication stages
   new content-addressed details before switching the compact index and prunes old
   details afterward, so an interruption cannot leave the visible index pointing at
   a missing detail.
10. Documentation, social posts, workshop indexes, repositories, and videos remain visible context but never receive fabricated paper readings.
11. Entry-level counts and canonical-record counts use different field names; duplicate collection entries never silently change the paper-reading denominator.
12. `make check` validates a deterministic in-memory reconstruction without
    regenerating source artifacts, so stale data fails without relying on Git history
    or volatile timestamps. Publication remains an explicit `make data` step.
13. The pipeline has no local-workspace or GitHub-repository ingestion adapter.
    `atlas.repos`, `meta.repo_count`, and every idea-level repository reference must
    remain empty. Validation rejects user-repository URLs and local device paths
    in the compact public artifact.
14. A promoted `researched-draft` brief requires a complete experiment plan, at least five unique primary competitors, a concrete novelty assessment, and support from at least two page-anchored collection readings. A user-specified flagship may substitute a substantially larger externally verified primary-source review when the collection itself does not contain the closest work. Every idea-level competitor also has an explicit `version-verified` or `legacy-unversioned` provenance state; the build joins canonical-ID keyed revision metadata from `data/source/competitors.json` and rejects missing, stale, conflicting, or partially verified rows.
15. Every full reading pins exactly one source artifact identity: either a PDF hash
    or an explicit HTML format and source hash, plus the extracted-text hash, page
    count, source locator, extraction time, and review-pass lineage. A source
    revision invalidates the reading until an explicit review action re-pins it.
    The audited Scholar conversions preserve ordered page text but omit raster figure
    pixels, so their readings disclose that limitation and make no visual-curve claims.
16. A successful document retrieval is not automatically a reviewable text extraction.
    Extracts below the page-coverage gate are labeled `partial_text`, retain the
    exact missing-page list, and stay outside full-text coverage and reading queues
    until an OCR pass or improved extraction replaces them.
17. OCR is page-selective and evidence-preserving: readable native pages remain
    unchanged, OCR output is reclassified by the normal text-quality gate, and the
    new text hash invalidates any stale reading provenance.
18. A visually audited non-content page gap is a source-side, revision-pinned
    exception rather than rewritten extraction data. The audit must match the
    stable ID, PDF SHA-256, page count, and complete native missing-page set; every
    page has an explicit `blank`, `divider`, or `non-content` classification plus
    evidence. Matching audits apply the unchanged coverage threshold to content
    pages and add separate content metrics. Native missing pages and native
    coverage remain intact. Hash or page-set drift removes the derived audit basis
    and returns the record to native quality classification.
19. The public corpus projection contains bibliographic records and reviewed evidence
    only; private source layers and device-derived metadata are rejected by validation.
20. A work package has one explicit parent program and
    `rank_independently: false`. It retains its one-decimal execution-feasibility
    score, but portfolio views nest it under the parent and independent frontiers
    exclude it. Python and browser validators reject orphaned, chained, or
    independently ranked work packages.
21. Reader and verifier queues use the same canonical ordering and fixed batch
    sizes. An unread paper is never presented as reviewer-ready, a first-pass
    reading is never presented as verified, and promotion requires independent
    passage and competitor lineage. Structural repair reasons remain explicit.
22. Daily discovery fetches the complete declared arXiv result set before applying
    relevance policy. Every relevance-positive row is retained independently from
    the interest shortlist, and every day keeps an unfiltered compressed audit
    archive. Source totals, raw counts, public counts, shortlist membership, score
    order, and static copies must agree before validation passes.
23. Hosted search is a disposable read accelerator, not evidence storage. Only a
    compact corpus search projection and complete public day projections enter
    PostgreSQL; PDFs, raw unfiltered intake, structured reviewed readings, full-text
    extracts do not. Corpus results
    return stable public entry IDs that the browser resolves against the validated
    static atlas. Deleting hosted rows never deletes the static archive.
24. Browser roles have `SELECT` and fixed-function execution only. They have no
    insert, update, or delete grant or policy. The server connection string never
    crosses the Actions/environment boundary, and the public publishable key is not
    treated as a secret or authorization boundary.
25. Historical scope is non-destructive. Every harvested arXiv record remains in
    exactly one of `likely`, `possible`, or `outside`; policy changes may reclassify
    records but never erase their metadata. Monthly shard hashes and completed date
    lists make interrupted workers resumable and independently auditable.

## Engineering principles

- **Abstractability:** Canonical identities, source resolution, ontology routing,
  feasibility scoring, experiment design, and coverage are
  independent domain modules. A new source route or research taxonomy extends one
  boundary instead of changing the whole build.
- **Testability:** Pure derivations accept explicit inputs and return plain data.
  Network and filesystem adapters stay thin, generated artifacts are deterministic,
  and unit, contract, browser, responsive-layout, and accessibility checks exercise
  separate failure surfaces.
- **Modularization:** Collection ingestion, full-text extraction, structured reading,
  related-work review, idea synthesis, validation, and presentation do not silently
  perform one another's jobs. The absence of repository ingestion is a validated
  source boundary rather than a UI convention.
- **Human readability:** Evidence levels and source provenance are named fields in
  inspected JSON, research briefs use explicit hypotheses and rejection rules, and
  compact modules prefer direct prose and small functions over metaprogramming.
- **Naming:** An authored source file or folder has one semantic word. Conventional
  `test_`, `.test`, `.spec`, and `.schema` markers do not count as domain words;
  generated artifacts, canonical-ID reading filenames, and mandatory ecosystem
  filenames are outside this source rule because their tokens are identities rather
  than authored domain names. The curated source and audit directories remain inside
  the gate. Python and TypeScript function names have at most three lexical words.
  `tests/test_architecture.py` enforces authored paths and pipeline/test Python
  function naming; `web/src/lib/names.test.ts` independently uses the TypeScript
  compiler AST to enforce named TypeScript function, method, and assigned-arrow
  naming.
- **Proportional design:** The atlas remains a static, provenance-bound data product.
  Semantic fixed seeds are repeatability controls within a pinned numerical
  environment, not a cross-platform bitwise guarantee; input, vector, and layout
  hashes make drift explicit. The measured need for cross-day search is served by a
  narrow PostgreSQL read accelerator, not by moving evidence, PDFs, or reviewed
  readings into a service.
  Static artifacts remain authoritative and independently usable.

The public atlas adds a map-first boundary before paper metadata: the core owns
taxonomy, ideas, aggregate semantic metadata, and taxonomy/idea layout rows, while a
content-addressed paper bundle owns collection records and their coordinates,
neighbors, and region assignments. Core metadata pins the bundle's SHA-256, byte
length, schema, and record count; the browser verifies all four and exact map
ownership before reconstructing the canonical atlas. Publication stages the bundle
before switching the core and retains one valid predecessor for cached-core safety.

The compact-index/lazy-detail split remains the reading-evidence scale boundary. In a
measured historical 132-reading snapshot, reading bodies contributed 2.70 MiB (42.4%) of the
6.38 MiB atlas; projecting the same mean body size across the corpus approaches
49 MiB. Publishing independent static JSON details bounds initial transfer and parse
cost without placing corpus evidence in a database. The browser fetches a detail only while
its modal is open, aborts superseded requests, and revalidates identity, depth, and
the full-reading contract before rendering evidence. The stable index request uses
`no-cache` revalidation; detail URLs are immutable because semantic reading changes
produce a new content digest.

## Extension points

- Add a document route by extending `resolve_source` and its unit tests.
- Recover a rasterized PDF with `ocr.py`; partial-text OCR remains opt-in so
  a lower-fidelity pass cannot silently replace readable native pages.
- Add a topic or technique by changing the ontology and boundary/noise tests.
- Add a reviewed paper source through the canonical identity, provenance, and
  reading-validation contracts rather than a separate user-specific layer.
- Promote a reading from `full_text` to `verified` only after a second passage-level check.
- A `verified` reading must separate the author's novelty claim from the reviewer's inference structurally; legacy `full_text` readings may retain a clearly labeled prose assessment until promoted.

The project favors small pure functions and explicit JSON artifacts over a general
service layer. The hosted database has one bounded purpose—corpus and daily metadata
search—and can disappear without making the atlas or its evidence unreadable.

The automated quality floor reflects that choice. The Python architecture suite
caps pipeline Python and non-test web source modules at 600 lines, caps pipeline
Python functions at 180 lines, and rejects internal pipeline import cycles. The
Vitest compiler-AST gate separately caps named TypeScript functions, methods, and
assigned arrows at 180 lines; it does not claim to enforce TypeScript import cycles.
Ruff rejects functions above a cyclomatic complexity of 12. Unit tests enforce at
least 50% aggregate pipeline line coverage, and end-to-end validation reconstructs
all public derived sections from source inputs. The aggregate coverage threshold is
intentionally conservative because network and command orchestration remain thin
shells; the reusable domain modules carry the denser unit coverage.
