"""Modelo de datos relacional + vectorial (Sprint 2: tickets, usuarios y registros históricos)."""
from datetime import datetime, timezone

from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .config import get_settings
from .db import Base


def ahora() -> datetime:
    return datetime.now(timezone.utc)


class Usuario(Base):
    """Administrador técnico (actor primario de CU-06 y CU-07)."""
    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    rol: Mapped[str] = mapped_column(String(20), default="admin")
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=ahora)


class Manual(Base):
    __tablename__ = "manuales"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(255))  # nombre del PDF (se usa en la cita)
    archivo: Mapped[str] = mapped_column(String(500))
    paginas: Mapped[int] = mapped_column(Integer, default=0)
    fragmentos_total: Mapped[int] = mapped_column(Integer, default=0)
    cargado_por: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id", ondelete="SET NULL"))
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=ahora)

    fragmentos: Mapped[list["Fragmento"]] = relationship(
        back_populates="manual", cascade="all, delete-orphan"
    )


class Fragmento(Base):
    """Chunk vectorizado con metadatos: PDF, página y marca de tiempo (CU-06 paso 6)."""
    __tablename__ = "fragmentos"

    id: Mapped[int] = mapped_column(primary_key=True)
    manual_id: Mapped[int] = mapped_column(ForeignKey("manuales.id", ondelete="CASCADE"), index=True)
    pagina: Mapped[int] = mapped_column(Integer)
    contenido: Mapped[str] = mapped_column(Text)
    embedding = mapped_column(Vector(get_settings().embedding_dim))
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=ahora)

    manual: Mapped[Manual] = relationship(back_populates="fragmentos")


class Ticket(Base):
    __tablename__ = "tickets"

    id: Mapped[int] = mapped_column(primary_key=True)
    consulta: Mapped[str] = mapped_column(Text)
    urgencia: Mapped[str | None] = mapped_column(String(10))  # alta | media | baja
    area: Mapped[str | None] = mapped_column(String(50))
    confianza_clasificacion: Mapped[float | None] = mapped_column(Float)
    # resuelto_ia | escalado | pendiente_reintento | cerrado_n2
    estado: Mapped[str] = mapped_column(String(20), default="recibido", index=True)
    motivo_escalamiento: Mapped[str | None] = mapped_column(String(255))
    respuesta: Mapped[str | None] = mapped_column(Text)
    fuentes: Mapped[list | None] = mapped_column(JSON)
    similitud_max: Mapped[float | None] = mapped_column(Float)
    modelo_llm: Mapped[str | None] = mapped_column(String(80))
    tiempo_respuesta_ms: Mapped[int | None] = mapped_column(Integer)
    calificacion: Mapped[int | None] = mapped_column(Integer)  # 1 = útil, -1 = no útil
    puntos_control: Mapped[list | None] = mapped_column(JSON)
    intentos: Mapped[int] = mapped_column(Integer, default=1)
    nota_cierre: Mapped[str | None] = mapped_column(Text)
    cerrado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=ahora, index=True)


class RegistroHistorico(Base):
    """Auditoría de eventos del sistema (trazabilidad del ticket y de la administración)."""
    __tablename__ = "registros_historicos"

    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_id: Mapped[int | None] = mapped_column(ForeignKey("tickets.id", ondelete="CASCADE"), index=True)
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id", ondelete="SET NULL"))
    tipo: Mapped[str] = mapped_column(String(40))
    detalle: Mapped[dict | None] = mapped_column(JSON)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=ahora, index=True)


class Alerta(Base):
    """CP5: alertas operativas para el administrador técnico."""
    __tablename__ = "alertas"

    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_id: Mapped[int | None] = mapped_column(ForeignKey("tickets.id", ondelete="CASCADE"))
    tipo: Mapped[str] = mapped_column(String(40))  # urgencia_alta | escalamiento | falla_llm | clasificacion_ambigua
    nivel: Mapped[str] = mapped_column(String(10), default="media")  # alta | media | baja
    mensaje: Mapped[str] = mapped_column(String(500))
    leida: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=ahora)
