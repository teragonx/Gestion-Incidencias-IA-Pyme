from datetime import datetime

from pydantic import BaseModel, Field


class TicketCrear(BaseModel):
    consulta: str = Field(max_length=5000)


class Fuente(BaseModel):
    manual: str
    pagina: int
    similitud: float
    extracto: str


class PuntoControl(BaseModel):
    id: str
    nombre: str
    ok: bool
    detalle: str


class TicketPublico(BaseModel):
    """Lo que ve el Cliente PYME: JSON {solución, manual, página} + estado (Fig. 13)."""
    id: int
    consulta: str
    urgencia: str | None
    area: str | None
    estado: str
    respuesta: str | None
    fuentes: list[Fuente] | None = None
    tiempo_respuesta_ms: int | None
    calificacion: int | None
    puntos_control: list[PuntoControl] | None = None
    nota_cierre: str | None = None
    creado_en: datetime


class TicketAdmin(TicketPublico):
    confianza_clasificacion: float | None
    motivo_escalamiento: str | None
    similitud_max: float | None
    modelo_llm: str | None
    intentos: int
    cerrado_en: datetime | None


class Calificacion(BaseModel):
    valor: int  # 1 o -1


class CierreTicket(BaseModel):
    nota: str = Field(min_length=3, max_length=2000)


class ManualRespuesta(BaseModel):
    id: int
    nombre: str
    paginas: int
    fragmentos_total: int
    creado_en: datetime


class Login(BaseModel):
    email: str
    password: str


class CambioPassword(BaseModel):
    actual: str
    nueva: str = Field(min_length=8)


class AlertaRespuesta(BaseModel):
    id: int
    ticket_id: int | None
    tipo: str
    nivel: str
    mensaje: str
    leida: bool
    creado_en: datetime


class RegistroRespuesta(BaseModel):
    id: int
    ticket_id: int | None
    tipo: str
    detalle: dict | None
    creado_en: datetime
