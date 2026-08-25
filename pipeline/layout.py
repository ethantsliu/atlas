"""Canonical public semantic-layout configuration."""

MODEL_NAME = "all-minilm"
MODEL_DIGEST = "1b226e2802dbb772b5fc32a58f103ca1804ef7501331012de126ab22f67475ef"
MODEL_CONTEXT = 256
OLLAMA_VERSION = "0.13.1"
EMBED_DIM = 384
LAYOUT_METHOD = "embedding-umap-3d-v1"
REDUCER = {
    "name": "umap",
    "dimensions": 3,
    "neighbors": 24,
    "min_dist": 0.12,
    "metric": "cosine",
    "random_seed": 42,
    "scale_percentile": 98,
    "clip": 1.25,
    "extent": 260,
}
