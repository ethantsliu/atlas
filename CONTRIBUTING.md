# Contributing

Atlas welcomes focused pull requests for interface improvements, paper-record
corrections, research-brief evidence, and pipeline reliability.

By participating, you agree to [CONDUCT.md](CONDUCT.md). Report vulnerabilities and
privacy leaks through the private process in [SECURITY.md](SECURITY.md).

## Before opening a pull request

1. Keep source modules small, readable, and independently testable. File and folder
   names must use one semantic word; conventional test and schema markers do not
   count. Python and TypeScript function names use at most three words.
2. Use public research sources only. Never add local paths, private repositories,
   account-derived labels, credentials, or personal ranking fields.
3. Add or update a test for behavioral changes. Paper claims need primary-source,
   page-anchored evidence and related work.
4. Use the CI reference environment, Python 3.12 and Node.js 22. Install with
   `.venv/bin/pip install -r dev.txt`, `npm --prefix web ci`, and
   `npm --prefix web exec playwright install chromium firefox webkit`. Run
   `make check PYTHON=.venv/bin/python`. For a UI-only change, at minimum run
   `npm --prefix web test`, `npm --prefix web run build`,
   `npm --prefix web run test:e2e`, and `npm --prefix web run format:check`.

## Semantic layout

If a change alters reviewed semantic fields, compact fallback text, taxonomy,
papers, or ideas, install Ollama 0.13.1, run `ollama pull all-minilm`, and then run
`make layout PYTHON=.venv/bin/python`. The command verifies the pinned `all-minilm`
digest and 256-token context before embedding and binds the inputs to the
field-budget schema. Commit the resulting layout, canonical atlas, public core, and
content-addressed paper bundle; do not commit model weights, full embedding vectors,
or local vector checkpoints.

Review semantic diffs as data changes. Exact cosine neighbors are discovery links,
not citations or evidence. Projection quality describes committed UMAP coordinates,
not browser force-simulation endpoints. KMeans regions are coarse orientation, not
natural classes; inspect the trust/recall cohorts, silhouette and stability metrics,
balance gates, labels, and payload budgets before accepting regenerated artifacts.
Fixed seeds support a pinned build but do not by themselves guarantee bit-identical
native floating-point results across transitive numerical libraries, BLAS builds, or
hardware, so vector and layout hash changes must be explained.

`make check` validates freshness and the built distribution without regenerating or
publishing semantic data. Run `make data` after reviewed source changes and
`make layout` only when semantic inputs change; neither command deploys the site.

## Scope

Keep pull requests narrow and explain the user-visible outcome. Generated artifacts
must stay byte-identical to their public mirrors, and every feasibility score remains
on the documented one-decimal 1–10 rubric.
