from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    nombre_empresa: str = "PYME"
    database_url: str = "postgresql+psycopg://soporte:soporte@localhost:5432/incidencias"

    # --- LLM (R2: proveedor desacoplado vía variables de entorno) ---
    # mock | openai | anthropic | google_genai
    llm_provider: str = "openai"
    llm_model: str = ""
    llm_timeout_s: float = 30
    llm_reintentos: int = 1
    # Contingencia R2: modelo alternativo si el principal falla (opcional)
    llm_fallback_provider: str = ""
    llm_fallback_model: str = ""

    # --- RAG ---
    embedding_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    embedding_dim: int = 384
    rag_umbral_similitud: float = 0.45  # CP3
    rag_top_k: int = 4
    chunk_size: int = 900
    chunk_overlap: int = 150

    # --- CP1: validación de entrada ---
    min_largo_consulta: int = 10
    max_largo_consulta: int = 2000

    # --- CP2: clasificación (R4: casos ambiguos se escalan) ---
    umbral_confianza_clasificacion: float = 0.5

    # --- Métricas (línea base del proceso manual) ---
    minutos_ticket_manual: float = 15  # tiempo de resolución humana de un ticket N1
    minutos_respuesta_manual: float = 30  # tiempo promedio de primera respuesta manual

    # --- Seguridad básica ---
    secret_key: str = "cambia-esta-clave-secreta"
    sesion_horas: int = 8
    admin_email: str = "admin@pyme.cl"
    admin_password: str = "admin123"
    admin_nombre: str = "Administrador Técnico"

    # --- R10: límites en etapa de prototipo ---
    rate_limit_por_minuto: int = 20

    manuales_dir: str = "data/manuales"
    modelos_dir: str = "data/modelos"


MODELOS_POR_DEFECTO = {
    "openai": "gpt-4o-mini",
    "anthropic": "claude-haiku-4-5",
    "google_genai": "gemini-2.0-flash",
}


@lru_cache
def get_settings() -> Settings:
    return Settings()
