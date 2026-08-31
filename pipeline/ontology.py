"""Shared topic and technique ontology for conservative first-pass routing."""

from __future__ import annotations

TOPICS = {
    "alignment": [
        "ai alignment",
        "aligned model",
        "preference",
        "reward model",
        "rlhf",
        "dpo",
        "harmless",
        "safety",
        "constitutional",
    ],
    "post-training": [
        "post-training",
        "instruction tuning",
        "fine-tuning",
        "fine tuning",
        "finetuning",
        "preference optimization",
        "reinforcement learning",
        "rlhf",
        "dpo",
    ],
    "pre-training": [
        "pretraining",
        "pre-training",
        "language modeling",
        "foundation model",
        "scaling law",
        "tokenizer",
    ],
    "world-models": [
        "world model",
        "dynamics model",
        "model-based",
        "simulator",
        "physical reasoning",
        "video prediction",
    ],
    "agents": [
        "agent",
        "agents",
        "tool use",
        "planning",
        "multi-agent",
        "computer use",
        "web navigation",
    ],
    "environment-design": [
        "environment design",
        "environment generation",
        "procedural generation",
        "open-ended learning",
        "curriculum generation",
        "task generation",
    ],
    "reasoning": [
        "reasoning",
        "chain-of-thought",
        "theorem",
        "mathematical",
        "problem solving",
        "in-context learning",
    ],
    "interpretability": [
        "interpretability",
        "mechanistic",
        "feature visualization",
        "circuit",
        "activation",
        "monosemantic",
    ],
    "evaluation": [
        "evaluation",
        "benchmark",
        "judge",
        "calibration",
        "robustness",
        "out-of-distribution",
    ],
    "optimization": [
        "optimization",
        "optimizer",
        "gradient descent",
        "learning rate",
        "loss landscape",
        "convergence",
    ],
    "efficiency-systems": [
        "efficient",
        "inference",
        "serving",
        "compression",
        "quantization",
        "hardware",
        "memory efficient",
    ],
    "multimodal": [
        "multimodal",
        "vision-language",
        "image",
        "video",
        "audio",
        "visual question",
    ],
    "generative-modeling": [
        "diffusion",
        "flow matching",
        "generative",
        "score matching",
        "autoregressive",
        "gan",
    ],
    "continual-learning": [
        "continual",
        "lifelong",
        "catastrophic forgetting",
        "unlearning",
        "incremental learning",
    ],
    "representation-learning": [
        "representation",
        "embedding",
        "contrastive",
        "self-supervised",
        "latent",
        "manifold",
    ],
    "ai-for-science": [
        "physics",
        "science",
        "molecular",
        "protein",
        "pde",
        "climate",
        "materials",
        "symbolic regression",
    ],
    "learning-theory": [
        "generalization bound",
        "sample complexity",
        "neural tangent",
        "learning theory",
        "theoretical analysis",
        "grokking",
        "statistical learning",
    ],
}


WORD_CHARS = frozenset("abcdefghijklmnopqrstuvwxyz0123456789")


def phrase_hit(text: str, phrase: str) -> bool:
    """Match one literal phrase with the ontology's ASCII word boundaries."""
    start = text.find(phrase)
    while start >= 0:
        end = start + len(phrase)
        left = start == 0 or text[start - 1] not in WORD_CHARS
        right = end == len(text) or text[end] not in WORD_CHARS
        if left and right:
            return True
        start = text.find(phrase, start + 1)
    return False


TRICKS = {
    "variance-control": [
        "gradient variance",
        "variance estimate",
        "control variate",
        "antithetic",
        "variance reduction",
    ],
    "normalization": [
        "normalization",
        "layernorm",
        "layer norm",
        "batch norm",
        "gradient norm",
        "rmsnorm",
    ],
    "sparsity": ["sparse", "pruning", "lottery ticket", "sparsity"],
    "routing-and-moe": [
        "mixture of experts",
        "routing",
        "router",
        "expert model",
        "modular",
    ],
    "synthetic-data": [
        "synthetic data",
        "self-generated",
        "data generation",
        "distill data",
    ],
    "self-play": ["self-play", "self improvement", "self-improvement", "debate"],
    "distillation": ["distillation", "teacher-student", "knowledge distill"],
    "retrieval-and-memory": [
        "retrieval",
        "memory",
        "replay buffer",
        "rag",
        "context cache",
    ],
    "test-time-compute": [
        "test-time",
        "inference-time",
        "best-of-n",
        "search at inference",
        "majority voting",
    ],
    "curriculum": ["curriculum", "difficulty schedule", "data ordering"],
    "regularization": ["regularization", "dropout", "weight decay", "early stopping"],
    "low-rank-adaptation": ["low-rank", "lora", "qlora", "adapter"],
    "ensembling": ["ensemble", "majority vote", "model averaging", "mixture"],
    "parameter-sharing": [
        "parameter sharing",
        "weight tying",
        "recurrent depth",
        "module reuse",
    ],
    "contrastive-learning": ["contrastive", "negative sampling", "triplet loss"],
    "reward-modeling": [
        "reward model",
        "preference model",
        "verifier",
        "process reward",
    ],
    "data-selection": [
        "data selection",
        "coreset",
        "active learning",
        "sample reduction",
        "data filtering",
    ],
    "long-context": [
        "long context",
        "context length",
        "lost in the middle",
        "attention sink",
    ],
    "scaling-laws": ["scaling law", "power law", "compute optimal", "chinchilla"],
    "evolutionary-search": [
        "evolution strategy",
        "evolutionary search",
        "genetic algorithm",
        "mutation",
        "population based",
    ],
    "quality-diversity": [
        "quality diversity",
        "quality-diversity",
        "map-elites",
        "novelty search",
        "behavioral diversity",
    ],
    "procedural-generation": [
        "procedural generation",
        "level generation",
        "environment generation",
        "task generation",
    ],
    "human-in-the-loop": [
        "human in the loop",
        "human-in-the-loop",
        "human feedback",
        "human intervention",
        "active learning",
    ],
    "scaling-probes": [
        "scale prediction",
        "scaling experiment",
        "small model",
        "learning curve",
        "compute frontier",
    ],
}


def route(text: str, ontology: dict[str, list[str]], limit: int = 4) -> list[dict]:
    """Return phrase-backed labels; scores count distinct bounded matches.

    Word boundaries prevent accidental substring routes such as ``align`` in
    ``alignment-free`` or ``agent`` in ``reagent``. Broad single words are kept
    out of the ontology when they do not identify a research area on their own.
    """
    lowered = text.lower()
    matches = []
    for label, phrases in ontology.items():
        hits = sorted(
            {
                phrase
                for phrase in phrases
                if phrase_hit(lowered, phrase)
            }
        )
        if hits:
            matches.append({"id": label, "score": len(hits), "evidence": hits[:4]})
    matches.sort(key=lambda item: (-item["score"], item["id"]))
    return matches[:limit]
