from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import limitar_tasa
from ..models import Ticket
from ..schemas import Calificacion, TicketCrear, TicketPublico
from ..services.pipeline import EntradaInvalida, procesar_ticket, registrar

router = APIRouter(prefix="/api/tickets", tags=["tickets (Cliente PYME)"])


@router.post("", response_model=TicketPublico, dependencies=[Depends(limitar_tasa)])
def registrar_consulta(datos: TicketCrear, db: Session = Depends(get_db)):
    """CU-01: registrar consulta técnica (incluye CU-02 y CU-03; CU-04 por extensión)."""
    try:
        return procesar_ticket(db, datos.consulta)
    except EntradaInvalida as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.get("/{ticket_id}", response_model=TicketPublico)
def estado_ticket(ticket_id: int, db: Session = Depends(get_db)):
    """Solución / estado del ticket para el cliente (diagrama de contexto)."""
    ticket = db.get(Ticket, ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket no encontrado")
    return ticket


@router.post("/{ticket_id}/reintentar", response_model=TicketPublico, dependencies=[Depends(limitar_tasa)])
def reintentar(ticket_id: int, db: Session = Depends(get_db)):
    """CU-01 flujo 8a: reprocesa un ticket que quedó en cola de espera por falla del LLM."""
    ticket = db.get(Ticket, ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket no encontrado")
    if ticket.estado != "pendiente_reintento":
        return ticket
    return procesar_ticket(db, ticket.consulta, ticket=ticket)


@router.post("/{ticket_id}/calificar", response_model=TicketPublico)
def calificar(ticket_id: int, datos: Calificacion, db: Session = Depends(get_db)):
    """CU-05: calificar resolución (pulgar arriba = 1 / abajo = -1)."""
    if datos.valor not in (1, -1):
        raise HTTPException(status_code=422, detail="La calificación debe ser 1 o -1")
    ticket = db.get(Ticket, ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket no encontrado")
    ticket.calificacion = datos.valor
    registrar(db, "calificacion", ticket.id, {"valor": datos.valor})
    db.commit()
    db.refresh(ticket)
    return ticket
