"""Las pruebas unitarias no necesitan PostgreSQL ni LLM: usan una sesión falsa y monkeypatch."""
import itertools
import os

os.environ.setdefault("LLM_PROVIDER", "mock")
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://x:x@localhost:1/x")  # no se conecta

import pytest  # noqa: E402


class SesionFalsa:
    """Imita lo mínimo de una sesión SQLAlchemy usado por el pipeline."""

    def __init__(self):
        self.objetos = []
        self._ids = itertools.count(1)
        self.commits = 0

    def add(self, obj):
        self.objetos.append(obj)

    def flush(self):
        for o in self.objetos:
            if getattr(o, "id", None) is None:
                o.id = next(self._ids)

    def commit(self):
        self.flush()
        self.commits += 1

    def refresh(self, obj):
        pass

    def de_tipo(self, cls):
        return [o for o in self.objetos if isinstance(o, cls)]


@pytest.fixture
def db():
    return SesionFalsa()
