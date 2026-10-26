from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .db import init_db
from .routers import auth, dashboard, manuales, tickets
from .services.llm import proveedor_activo


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="Prototipo de gestión de incidencias basado en agentes IA",
    description="API del sistema de soporte de Nivel 1 con arquitectura RAG (FastAPI + LangChain + pgvector).",
    version="1.0.0",
    lifespan=lifespan,
)

# En producción el frontend llega por el proxy de Nginx (mismo origen);
# este CORS solo habilita el servidor de desarrollo de Vite.
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173"],
                   allow_methods=["*"], allow_headers=["*"])

app.include_router(auth.router)
app.include_router(tickets.router)
app.include_router(manuales.router)
app.include_router(dashboard.router)


@app.get("/api/salud", tags=["sistema"])
def salud():
    return {"ok": True, "empresa": get_settings().nombre_empresa, "llm": proveedor_activo()}
