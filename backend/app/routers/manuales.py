import os
import re
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..deps import usuario_actual
from ..models import Manual, Usuario
from ..schemas import ManualRespuesta
from ..services.pipeline import registrar
from ..services.rag import PDFInvalido, ingerir_pdf

router = APIRouter(prefix="/api/manuals", tags=["manuales (Administrador)"])

MAX_MB = 25


@router.get("", response_model=list[ManualRespuesta])
def listar(db: Session = Depends(get_db), _: Usuario = Depends(usuario_actual)):
    return db.scalars(select(Manual).order_by(Manual.creado_en.desc())).all()


@router.post("/upload", response_model=ManualRespuesta)
def cargar_manual(archivo: UploadFile = File(...), db: Session = Depends(get_db),
                  usuario: Usuario = Depends(usuario_actual)):
    """CU-06: cargar y vectorizar documentación técnica (síncrono: corre en el threadpool)."""
    nombre_original = os.path.basename(archivo.filename or "")
    # CU-06 paso 3: validar extensión, estructura y legibilidad
    if not nombre_original.lower().endswith(".pdf"):
        raise HTTPException(status_code=422, detail="Solo se aceptan archivos PDF.")
    contenido = archivo.file.read()
    if len(contenido) > MAX_MB * 1024 * 1024:
        raise HTTPException(status_code=422, detail=f"El PDF supera {MAX_MB} MB.")
    if not contenido.startswith(b"%PDF"):
        raise HTTPException(status_code=422, detail="El archivo está dañado o no es un PDF válido.")

    destino_dir = get_settings().manuales_dir
    os.makedirs(destino_dir, exist_ok=True)
    seguro = re.sub(r"[^\w.-]", "_", nombre_original)
    ruta = os.path.join(destino_dir, f"{uuid.uuid4().hex[:8]}_{seguro}")
    with open(ruta, "wb") as f:
        f.write(contenido)

    try:
        manual = ingerir_pdf(db, ruta, nombre_original, usuario.id)
    except PDFInvalido as e:
        os.remove(ruta)
        raise HTTPException(status_code=422, detail=str(e))
    registrar(db, "manual_cargado", usuario_id=usuario.id,
              detalle={"manual": manual.nombre, "paginas": manual.paginas, "fragmentos": manual.fragmentos_total})
    db.commit()
    return manual


@router.delete("/{manual_id}")
def eliminar(manual_id: int, db: Session = Depends(get_db), usuario: Usuario = Depends(usuario_actual)):
    manual = db.get(Manual, manual_id)
    if not manual:
        raise HTTPException(status_code=404, detail="Manual no encontrado")
    if os.path.exists(manual.archivo):
        os.remove(manual.archivo)
    registrar(db, "manual_eliminado", usuario_id=usuario.id, detalle={"manual": manual.nombre})
    db.delete(manual)
    db.commit()
    return {"ok": True}
