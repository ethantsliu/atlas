# Related-work review protocol

`related_work_candidates.jsonl` is a recall-oriented queue, not a novelty result. Its lexical candidates come only from the 2,205-entry public collection. A paper becomes `reviewed` only when a structured reading contains external primary-source related work.

For each full-paper review:

1. Read the local extracted text end to end and write the method, assumptions, evaluation setting, and strongest claim before searching by title similarity.
2. Search arXiv, OpenReview, and the relevant official proceedings with at least three query families:
   - the claimed mechanism and task;
   - the evaluation setting and closest baseline;
   - the paper's own novelty language and cited predecessor.
3. Prefer direct competitors over broadly related surveys. Include at least three primary records and add more when the claim spans distinct subfields.
4. For every competitor, record a stable ID, primary URL, relationship, and a concrete methodological or empirical difference.
5. Check whether an earlier paper already contains the claimed combination. Narrow the novelty statement when it does.
6. Separate author-stated novelty from reviewer inference. Record omitted direct work and negative results.
7. Treat a result as `full_text` after this pass. Promote it to `verified` only
   after a second reviewer checks cited passages and competitor records, records
   finding attribution and competitor source versions, and writes the structured
   verification lineage required by the schema.

The reviewed competitor list is stored inside `data/reviewed/readings/<paper-id>.json` and copied into the corresponding related-work row. This curated directory contains human or research-agent judgments and remains separate from disposable candidate queues and other derived artifacts under `data/generated/`.

The candidate queue is produced by the pure `build_work_rows` function. Validation reconstructs every row from the enriched corpus and readings and compares the complete result, including lexical candidates, so same-count stale queues cannot pass the freshness check.
