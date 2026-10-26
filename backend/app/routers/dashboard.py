from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..deps import usuario_actual
from ..models import Alerta, Manual, RegistroHistorico, Ticket, Usuario
from ..schemas import AlertaRespuesta, CierreTicket, RegistroRespuesta, TicketAdmin
from ..services.llm import etiqueta, proveedor_activo
from ..services.pipeline import registrar

router = APIRouter(prefix="/api/dashboard", tags=["dashboard (Administrador)"],
                   dependencies=[Depends(usuario_actual)])

SEMANAS = 8


@router.get("")
def kpis(db: Session = Depends(get_db)):
    """CU-07: KPIs de negocio (tasa de resolución IA, tiempo de ahorro) y monitoreo de consultas."""
    s = get_settings()
    ahora = datetime.now(timezone.utc)
    inicio_mes = ahora.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    total = db.scalar(select(func.count(Ticket.id))) or 0
    por_estado = dict(db.execute(select(Ticket.estado, func.count()).group_by(Ticket.estado)).all())
    por_urgencia = dict(db.execute(select(Ticket.urgencia, func.count()).group_by(Ticket.urgencia)).all())
    resueltos = por_estado.get("resuelto_ia", 0)
    resueltos_mes = db.scalar(select(func.count()).where(
        Ticket.estado == "resuelto_ia", Ticket.creado_en >= inicio_mes)) or 0

    tiempo_prom_ms = float(db.scalar(select(func.avg(Ticket.tiempo_respuesta_ms))) or 0)
    base_ms = s.minutos_respuesta_manual * 60_000
    reduccion = 1 - (tiempo_prom_ms / base_ms) if tiempo_prom_ms and base_ms else None

    positivas = db.scalar(select(func.count()).where(Ticket.calificacion == 1)) or 0
    calificadas = db.scalar(select(func.count()).where(Ticket.calificacion.is_not(None))) or 0

    hoy = ahora.date()
    lunes_actual = hoy - timedelta(days=hoy.weekday())
    desde = lunes_actual - timedelta(weeks=SEMANAS - 1)
    semana = func.date_trunc("week", Ticket.creado_en)
    filas = db.execute(
        select(semana.label("s"), Ticket.estado, func.count())
        .where(Ticket.creado_en >= datetime.combine(desde, datetime.min.time(), timezone.utc))
        .group_by("s", Ticket.estado)
    ).all()
    serie = {desde + timedelta(weeks=i): {"resueltas_ia": 0, "otras": 0} for i in range(SEMANAS)}
    for inicio, estado, n in filas:
        clave = inicio.date()
        if clave in serie:
            serie[clave]["resueltas_ia" if estado == "resuelto_ia" else "otras"] += n

    return {
        "total_consultas": total,
        "resueltos_ia": resueltos,
        "escalados": por_estado.get("escalado", 0),
        "pendientes_reintento": por_estado.get("pendiente_reintento", 0),
        "cerrados_n2": por_estado.get("cerrado_n2", 0),
        "tasa_resolucion_ia": round(resueltos / total, 4) if total else 0,
        "horas_ahorradas_mes": round(resueltos_mes * s.minutos_ticket_manual / 60, 1),
        "horas_ahorradas_total": round(resueltos * s.minutos_ticket_manual / 60, 1),
        "tiempo_promedio_ms": round(tiempo_prom_ms),
        "reduccion_tiempo_respuesta": round(reduccion, 4) if reduccion is not None else None,
        "satisfaccion": round(positivas / calificadas, 4) if calificadas else None,
        "calificadas": calificadas,
        "manuales_activos": db.scalar(select(func.count(Manual.id))) or 0,
        "alertas_sin_leer": db.scalar(select(func.count()).where(Alerta.leida.is_(False))) or 0,
        "por_urgencia": {k: por_urgencia.get(k, 0) for k in ("alta", "media", "baja")},
        "consultas_por_semana": [{"semana": k.isoformat(), **v} for k, v in sorted(serie.items())],
        "proveedor_llm": proveedor_activo(),
    }


@router.get("/tickets", response_model=list[TicketAdmin])
def historial_consultas(estado: str | None = None, urgencia: str | None = None, limite: int = 100,
                        db: Session = Depends(get_db)):
    """Historial de consultas filtrable por estado y urgencia."""
    q = select(Ticket).order_by(Ticket.creado_en.desc()).limit(min(limite, 500))
    if estado:
        q = q.where(Ticket.estado == estado)
    if urgencia:
        q = q.where(Ticket.urgencia == urgencia)
    return db.scalars(q).all()


@router.get("/tickets/{ticket_id}/historial", response_model=list[RegistroRespuesta])
def trazabilidad(ticket_id: int, db: Session = Depends(get_db)):
    """Trazabilidad completa de un ticket (registros históricos)."""
    return db.scalars(select(RegistroHistorico).where(RegistroHistorico.ticket_id == ticket_id)
                      .order_by(RegistroHistorico.creado_en)).all()


@router.post("/tickets/{ticket_id}/cerrar", response_model=TicketAdmin)
def cerrar_ticket(ticket_id: int, datos: CierreTicket, db: Session = Depends(get_db),
                  usuario: Usuario = Depends(usuario_actual)):
    """Registra la resolución entregada por soporte humano (Nivel 2) a un ticket escalado."""
    ticket = db.get(Ticket, ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket no encontrado")
    if ticket.estado not in ("escalado", "pendiente_reintento"):
        raise HTTPException(status_code=409, detail="Solo se pueden cerrar tickets escalados o pendientes")
    ticket.estado = "cerrado_n2"
    ticket.nota_cierre = datos.nota.strip()
    ticket.cerrado_en = datetime.now(timezone.utc)
    registrar(db, "ticket_cerrado_n2", ticket.id, {"nota": ticket.nota_cierre}, usuario.id)
    db.commit()
    db.refresh(ticket)
    return ticket


@router.get("/alertas", response_model=list[AlertaRespuesta])
def alertas(solo_sin_leer: bool = False, db: Session = Depends(get_db)):
    """CP5: alertas operativas."""
    q = select(Alerta).order_by(Alerta.creado_en.desc()).limit(100)
    if solo_sin_leer:
        q = q.where(Alerta.leida.is_(False))
    return db.scalars(q).all()


@router.post("/alertas/leer-todas")
def leer_alertas(db: Session = Depends(get_db)):
    for a in db.scalars(select(Alerta).where(Alerta.leida.is_(False))):
        a.leida = True
    db.commit()
    return {"ok": True}


@router.get("/configuracion")
def configuracion():
    """Parámetros vigentes del agente (solo lectura; se modifican en .env)."""
    s = get_settings()
    return {
        "empresa": s.nombre_empresa,
        "llm_principal": proveedor_activo(),
        "llm_alternativo": etiqueta(s.llm_fallback_provider, s.llm_fallback_model) if s.llm_fallback_provider else None,
        "llm_timeout_s": s.llm_timeout_s,
        "modelo_embeddings": s.embedding_model,
        "umbral_similitud_cp3": s.rag_umbral_similitud,
        "fragmentos_top_k": s.rag_top_k,
        "tamano_fragmento": s.chunk_size,
        "solapamiento_fragmento": s.chunk_overlap,
        "umbral_confianza_cp2": s.umbral_confianza_clasificacion,
        "largo_consulta": [s.min_largo_consulta, s.max_largo_consulta],
        "minutos_ticket_manual": s.minutos_ticket_manual,
        "minutos_respuesta_manual": s.minutos_respuesta_manual,
        "limite_consultas_por_minuto": s.rate_limit_por_minuto,
    }
