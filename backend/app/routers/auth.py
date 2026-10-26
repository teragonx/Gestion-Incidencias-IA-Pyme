from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import limitar_tasa, usuario_actual
from ..models import Usuario
from ..schemas import CambioPassword, Login
from ..security import crear_token, hash_password, verificar_password
from ..services.pipeline import registrar

router = APIRouter(prefix="/api/auth", tags=["autenticación"])


@router.post("/login", dependencies=[Depends(limitar_tasa)])
def login(datos: Login, db: Session = Depends(get_db)):
    usuario = db.scalar(select(Usuario).where(Usuario.email == datos.email.strip().lower()))
    if not usuario or not usuario.activo or not verificar_password(datos.password, usuario.password_hash):
        raise HTTPException(status_code=401, detail="Correo o contraseña incorrectos")
    registrar(db, "login", usuario_id=usuario.id)
    db.commit()
    return {"token": crear_token(usuario.id), "nombre": usuario.nombre, "email": usuario.email}


@router.get("/yo")
def yo(usuario: Usuario = Depends(usuario_actual)):
    return {"id": usuario.id, "nombre": usuario.nombre, "email": usuario.email, "rol": usuario.rol}


@router.post("/cambiar-password")
def cambiar_password(datos: CambioPassword, usuario: Usuario = Depends(usuario_actual),
                     db: Session = Depends(get_db)):
    if not verificar_password(datos.actual, usuario.password_hash):
        raise HTTPException(status_code=400, detail="La contraseña actual no es correcta")
    usuario.password_hash = hash_password(datos.nueva)
    registrar(db, "cambio_password", usuario_id=usuario.id)
    db.commit()
    return {"ok": True}
