"""Domain-specific controls for provisional idea briefs."""

from __future__ import annotations

DEFAULT_PROTOCOL = {
    "baseline": "the strongest public baseline under the same data and compute budget",
    "primary_metric": "the task's primary metric with confidence intervals",
    "heldout": "one preregistered distribution shift",
    "failure_slice": "difficulty, data regime, and random seed",
}

TOPIC_PROTOCOLS = {
    "alignment": {
        "baseline": "a matched preference-optimization baseline",
        "primary_metric": "blind preference quality plus calibrated safety and exploit rates",
        "heldout": "adversarial prompts and an independently labeled preference set",
        "failure_slice": "annotator group, prompt risk, and reward-model disagreement",
    },
    "post-training": {
        "baseline": "the same base model and post-training tokens without the intervention",
        "primary_metric": "held-out task reward, KL drift, and pass rate at matched tokens",
        "heldout": "unseen task families and a second evaluator",
        "failure_slice": "trajectory length, reward sparsity, and policy staleness",
    },
    "pre-training": {
        "baseline": "a compute-optimal language-modeling run with the same token budget",
        "primary_metric": "held-out loss and downstream transfer at matched FLOPs",
        "heldout": "a disjoint data source and larger compute checkpoint",
        "failure_slice": "model size, token frequency, and domain mixture",
    },
    "world-models": {
        "baseline": "a model-free policy and a matched-capacity dynamics baseline",
        "primary_metric": "multi-step rollout error and downstream control return",
        "heldout": "longer horizons and unseen dynamics",
        "failure_slice": "horizon, stochasticity, and model exploitation",
    },
    "agents": {
        "baseline": "the same agent scaffold without the intervention",
        "primary_metric": "task success, tool calls, tokens, latency, and failure recovery",
        "heldout": "unseen tools and compositional tasks",
        "failure_slice": "horizon, tool error, and task family",
    },
    "environment-design": {
        "baseline": "random, curriculum, regret, and learnability-based task selection",
        "primary_metric": "compute-matched downstream transfer and reward/evaluator exploit gap",
        "heldout": "new environment families and a stronger policy optimizer",
        "failure_slice": "generator lineage, policy family, and difficulty",
    },
    "reasoning": {
        "baseline": "direct answering and matched-token search or sampling",
        "primary_metric": "pass@k and calibrated exactness at matched inference tokens",
        "heldout": "perturbed problems requiring the same underlying rule",
        "failure_slice": "problem length, branching factor, and answer contamination",
    },
    "interpretability": {
        "baseline": "correlational probes and random or magnitude-matched interventions",
        "primary_metric": "causal effect size, localization precision, and completeness",
        "heldout": "new prompts, checkpoints, and synthetic ground-truth circuits",
        "failure_slice": "layer, feature frequency, and intervention strength",
    },
    "evaluation": {
        "baseline": "the current benchmark or judge with identical examples",
        "primary_metric": "predictive validity, calibration, agreement, and contamination rate",
        "heldout": "a later model family and independently adjudicated examples",
        "failure_slice": "capability level, item source, and judge disagreement",
    },
    "optimization": {
        "baseline": "a tuned standard optimizer at equal parameter-update compute",
        "primary_metric": "compute to target loss plus stability and final generalization",
        "heldout": "a larger model and shifted conditioning regime",
        "failure_slice": "scale, curvature, batch size, and learning rate",
    },
    "efficiency-systems": {
        "baseline": "the production-quality reference implementation at equal quality",
        "primary_metric": "throughput, tail latency, peak memory, energy, and accuracy",
        "heldout": "a second hardware generation and realistic request distribution",
        "failure_slice": "batch size, sequence length, and hardware topology",
    },
    "multimodal": {
        "baseline": "a matched unimodal and multimodal model",
        "primary_metric": "task accuracy, calibration, and modality reliance",
        "heldout": "missing, corrupted, and compositionally shifted modalities",
        "failure_slice": "modality, corruption type, and cross-modal conflict",
    },
    "generative-modeling": {
        "baseline": "a matched-compute autoregressive, diffusion, or flow baseline",
        "primary_metric": "quality, diversity, likelihood proxy, and sampling cost",
        "heldout": "rare concepts and compositionally shifted prompts",
        "failure_slice": "sampling budget, rarity, and memorization risk",
    },
    "continual-learning": {
        "baseline": "rehearsal, regularization, and joint-training upper bounds",
        "primary_metric": "average accuracy, forgetting, forward transfer, memory, and compute",
        "heldout": "longer task streams without known boundaries",
        "failure_slice": "stream length, task similarity, and buffer size",
    },
    "representation-learning": {
        "baseline": "a matched-capacity supervised and self-supervised encoder",
        "primary_metric": "frozen transfer, sample efficiency, and intervention sensitivity",
        "heldout": "new domains and label-scarce tasks",
        "failure_slice": "data scale, probe capacity, and nuisance correlation",
    },
    "ai-for-science": {
        "baseline": "the strongest domain solver at equal observations and compute",
        "primary_metric": "predictive error, physical validity, and discovery utility",
        "heldout": "out-of-range regimes and a prospective scientific test",
        "failure_slice": "physical regime, measurement noise, and constraint violation",
    },
    "learning-theory": {
        "baseline": "the closest theorem and its empirical reference algorithm",
        "primary_metric": "bound tightness, assumption coverage, and predictive agreement",
        "heldout": "finite-width and out-of-assumption regimes",
        "failure_slice": "sample size, width, noise, and violated assumptions",
    },
}

TECHNIQUE_CONFOUNDS = {
    "variance-control": "Verify estimator bias separately from variance and match samples.",
    "synthetic-data": "Audit contamination, duplication, generator cost, and synthetic-to-real transfer.",
    "self-play": "Use an external evaluator so circular self-reward cannot define success.",
    "retrieval-and-memory": "Match stored information and measure stale or misleading retrievals.",
    "test-time-compute": "Match total sampled tokens and report quality as a compute frontier.",
    "curriculum": "Separate faster early learning from a higher converged performance ceiling.",
    "reward-modeling": "Track reward/evaluator divergence as policy optimization strengthens.",
    "evolutionary-search": "Charge every candidate evaluation and inner-loop training run to search cost.",
    "quality-diversity": "Report coverage and downstream utility, not archive occupancy alone.",
    "procedural-generation": "Split by generator lineage to prevent near-duplicate train-test leakage.",
    "human-in-the-loop": "Report human minutes, agreement, reversals, and sentinel-audit false negatives.",
    "scaling-probes": "Freeze the predictor before a held-out larger-scale run and report sign reversals.",
}


def protocol_for(topic: str) -> dict:
    """Return a copy so callers cannot mutate shared protocol constants."""
    return dict(TOPIC_PROTOCOLS.get(topic, DEFAULT_PROTOCOL))


def confound_for(trick: str | None) -> str:
    """Return the most important technique-specific matched control."""
    if trick is None:
        return "Define one falsifier before tuning the intervention."
    return TECHNIQUE_CONFOUNDS.get(
        trick,
        "Change only this mechanism and match parameters, data, and compute.",
    )
