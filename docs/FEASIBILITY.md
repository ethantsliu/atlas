# Feasibility score

Every idea receives a score from 1.0 to 10.0 with one decimal place. The score measures how readily a decisive first experiment can be run; it does not measure importance.

| Factor | Points | Question |
|---|---:|---|
| Implementation leverage | 0–2.5 | Is there reliable code, data, and relevant local infrastructure? |
| Compute and data access | 0–2.5 | Can the experiment run with resources that are realistically available? |
| Evaluation clarity | 0–2.0 | Are the primary metric, baseline, and matched-budget control clear? |
| Novelty risk | 0–1.5 | Does the competitive review leave a distinct, defensible contribution? |
| Time to first signal | 0–1.5 | Can a reduced experiment disconfirm the idea quickly? |

Scores are provisional until paper readings and competitive landscapes are verified. For an unreviewed idea, evaluation clarity is capped at 0.9/2.0 and novelty at 0.3/1.5, so a lexical or template-generated connection cannot receive a research-ready score. The UI labels these values as screening estimates. Each idea stores factor-level scores, rationales, assumptions, and the rubric version so users can audit or revise the number.
