import time
from collections import defaultdict, deque

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from .config import get_settings
from .db import get_db
from .models import Usuario
from .security import leer_token


def usuario_actual(authorization: str = Header(default=""), db: Session = Depends(get_db)) -> Usuario:
    """Precondición de CU-06/CU-07: sesión autenticada del Administrador Técnico."""
    token = authorization.removeprefix("Bearer ").strip()
    uid = leer_token(token) if token else None
    usuario = db.get(Usuario, uid) if uid else None
    if not usuario or not usuario.activo:
        raise HTTPException(status_code=401, detail="Sesión inválida o expirada")
    return usuario


# R10: límite simple de peticiones por IP (en memoria; suficiente para el prototipo)
_ventanas: dict[str, deque] = defaultdict(deque)


def limitar_tasa(request: Request) -> None:
    limite = get_settings().rate_limit_por_minuto
    if limite <= 0:
        return
    ip = request.client.host if request.client else "?"
    ahora = time.monotonic()
    v = _ventanas[ip]
    while v and ahora - v[0] > 60:
        v.popleft()
    if len(v) >= limite:
        raise HTTPException(status_code=429, detail="Demasiadas consultas seguidas. Espera un minuto e inténtalo de nuevo.")
    v.append(ahora)
