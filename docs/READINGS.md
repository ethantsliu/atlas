# Full-paper reading contract

Each structured reading must be based on extracted full text, not only the title or abstract. Write direct, compact sentences. Define uncommon terms at first use.

Required JSON fields:

```json
{
  "stable_id": "arxiv:0000.00000",
  "reading_depth": "full_text",
  "source_provenance": {
    "source_locator": "https://arxiv.org/pdf/0000.00000",
    "pdf_sha256": "...",
    "text_sha256": "...",
    "page_count": 12,
    "extracted_at": "...",
    "review_pass": "primary-full-text-v1"
  },
  "question": "The precise question the paper tests.",
  "key_findings": [
    {
      "claim": "A finding stated in your own words.",
      "evidence": "Experiment, theorem, or analysis that supports it.",
      "anchors": [{ "page": 4, "section": "3.2" }]
    }
  ],
  "method": { "core_idea": "...", "mechanism": "...", "assumptions": ["..."] },
  "techniques": [{ "id": "variance-control", "role": "What it does here." }],
  "evaluations": [
    { "setting": "...", "metric": "...", "result": "...", "baseline": "..." }
  ],
  "limitations": ["Author-stated or reader-identified limitation."],
  "failure_modes": ["Where the method is likely to fail and why."],
  "reusable_insights": ["Mechanism that may transfer beyond this paper."],
  "open_questions": ["Concrete unanswered question."],
  "competitive_landscape": [
    {
      "canonical_id": "arxiv:0000.00000",
      "title": "...",
      "url": "https://arxiv.org/abs/0000.00000",
      "relationship": "prior",
      "difference": "The direct methodological or empirical difference."
    }
  ],
  "novelty_assessment": "What remains new after comparison; label reviewer inference.",
  "confidence": 0.0,
  "reviewer_notes": "Separate inference from author claims."
}
```

The example shows the legacy/default PDF identity. An approved alternate artifact
uses the same provenance fields except that `source_format: "html"` and
`source_sha256` replace `pdf_sha256`; the two hash forms are mutually exclusive.
The only current HTML route is an exact, page-preserving Scholar conversion tied to
an OpenReview stable ID and origin identity in the extraction index. Converter
text and page order are reviewable, but raster figure pixels are absent. The reading
must disclose that boundary and must not claim inspection of plot axes, panels, or
curves that were not present in the cached artifact.

The cache locator is HTTPS on `scholar.googleusercontent.com/scholar`, with one
nonempty `q=cache:<token>...` field and only optional, nonempty, singleton `hl` and
`as_sdt` fields. Ports, alternate paths, path parameters, fragments, unknown fields,
and repeated fields fail validation. The raw conversion must identify the same
OpenReview stable-ID suffix through exactly
`https://openreview.net/forum?id=<suffix>` in its `<base>` element. The extraction
index may retain that forum URL or the corresponding exact `/pdf?id=<suffix>` origin;
both reject ports, path parameters, fragments, unknown fields, and repeated IDs.

Quality checks:

1. Every key finding has a page or section anchor.
2. Quantitative claims include the setting, metric, and baseline.
3. Limitations distinguish author statements from reviewer inference.
4. Technique tags describe a mechanism, not merely a research topic.
5. A second pass checks the output against cited passages before it becomes `verified`.
6. Competitive papers come from primary arXiv or publisher records; title similarity alone is not evidence of competition.
7. `source_provenance` must match the indexed artifact and extracted-text hashes. Run
   `pipeline/lineage.py --accept-current-source` only after checking a
   changed revision; ordinary builds never re-pin readings.
8. `verified` additionally requires finding attribution, competitor source kind,
   checked date and version, plus an explicit second-review record. A depth label
   alone cannot promote a reading.

Concurrent reviewers must reserve a stable ID before inspecting or writing it:

```sh
PYTHONPATH=pipeline python3 -m claims reserve arxiv:0000.00000 --agent reader-a
```

The command normalizes legacy marker names, rejects finalized readings, and creates
one canonical marker atomically. Write the final JSON only after another absence
check, validate it against the exact indexed source, and then release only your own
marker:

```sh
PYTHONPATH=pipeline python3 -m claims release arxiv:0000.00000 --agent reader-a
```

Claim-owner labels are local coordination state and must never be copied into a
reviewed reading. A committed `verification.reviewer_id` uses the opaque public
shape `reviewer-<12 hex>` returned by `privacy.public_reviewer_id(stable_id,
checked_at)`. The input is the paper identity and verification date, not an account,
machine, agent, or fleet label.

Never make an empty final reading file as a reservation and never overwrite an
existing final reading.
