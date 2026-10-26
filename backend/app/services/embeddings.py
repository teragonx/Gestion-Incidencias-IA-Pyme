"""Embeddings locales (sin costo de licencia) usando fastembed (ONNX).

El modelo multilingüe se descarga la primera vez y queda en un volumen de Docker.
"""
from functools import lru_cache

from ..config import get_settings


@lru_cache
def _modelo():
    from fastembed import TextEmbedding

    s = get_settings()
    return TextEmbedding(model_name=s.embedding_model, cache_dir=s.modelos_dir)


def _hash_embed(texto: str) -> list[float]:
    """Modo offline (EMBEDDING_MODEL=hash): bolsa de palabras con hashing.

    Sin red ni modelo; solo para pruebas. La calidad semántica es baja.
    """
    import hashlib
    import math
    import re
    import unicodedata

    dim = get_settings().embedding_dim
    t = unicodedata.normalize("NFKD", texto.lower()).encode("ascii", "ignore").decode()
    v = [0.0] * dim
    for palabra in re.findall(r"[a-z0-9]{3,}", t):
        raiz = palabra[:6]  # stemming muy básico
        v[int(hashlib.md5(raiz.encode()).hexdigest(), 16) % dim] += 1.0
    norma = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / norma for x in v]


def embed_textos(textos: list[str]) -> list[list[float]]:
    if get_settings().embedding_model == "hash":
        return [_hash_embed(t) for t in textos]
    return [v.tolist() for v in _modelo().embed(textos)]


def embed_consulta(texto: str) -> list[float]:
    return embed_textos([texto])[0]
