"""Ingesta de manuales PDF (CU-06) y recuperación semántica con pgvector (CU-02)."""
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import Fragmento, Manual
from .embeddings import embed_consulta, embed_textos


class PDFInvalido(ValueError):
    pass


def extraer_fragmentos(ruta: str) -> tuple[int, list[tuple[int, str]]]:
    """CU-06 paso 4: LangChain carga el PDF por página y lo divide en chunks con solapamiento."""
    s = get_settings()
    try:
        paginas = PyPDFLoader(ruta).load()
    except Exception as e:
        raise PDFInvalido(f"No se pudo leer el PDF ({type(e).__name__}). ¿Está dañado o protegido?")

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=s.chunk_size, chunk_overlap=s.chunk_overlap,
        separators=["\n\n", "\n", ". ", " ", ""],
    )
    pares: list[tuple[int, str]] = []
    for doc in paginas:
        n_pagina = int(doc.metadata.get("page", 0)) + 1  # PyPDFLoader numera desde 0
        texto = " ".join(doc.page_content.split())
        for trozo in splitter.split_text(texto):
            if len(trozo) > 30:
                pares.append((n_pagina, trozo))

    if not pares:
        raise PDFInvalido("El PDF no contiene texto legible (¿es un escaneo sin OCR o tiene el texto bloqueado?).")
    return len(paginas), pares


def ingerir_pdf(db: Session, ruta: str, nombre: str, usuario_id: int | None = None) -> Manual:
    n_paginas, pares = extraer_fragmentos(ruta)
    vectores = embed_textos([t for _, t in pares])  # CU-06 paso 5
    manual = Manual(nombre=nombre, archivo=ruta, paginas=n_paginas,
                    fragmentos_total=len(pares), cargado_por=usuario_id)
    manual.fragmentos = [
        Fragmento(pagina=p, contenido=t, embedding=v) for (p, t), v in zip(pares, vectores)
    ]
    db.add(manual)  # CU-06 paso 6
    db.commit()
    db.refresh(manual)
    return manual


def recuperar(db: Session, consulta: str, k: int) -> list[dict]:
    """CU-02: k fragmentos más cercanos por distancia coseno, con su similitud (0..1)."""
    vec = embed_consulta(consulta)
    distancia = Fragmento.embedding.cosine_distance(vec)
    filas = db.execute(
        select(Fragmento, Manual.nombre, distancia.label("dist"))
        .join(Manual)
        .order_by(distancia)
        .limit(k)
    ).all()
    return [
        {"manual": nombre, "pagina": frag.pagina, "contenido": frag.contenido,
         "similitud": round(1 - float(dist), 4)}
        for frag, nombre, dist in filas
    ]
