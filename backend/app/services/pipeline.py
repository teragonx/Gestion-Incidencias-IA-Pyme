"""Flujo macroscópico del proceso automatizado con puntos de control (Fig. 6 y 7 del informe).

1 Recepción → 2 Validación (CP1) → 3 Clasificación IA (CP2) → 4 Recuperación RAG (CP3)
→ 5 Respuesta (CP4) o escalamiento (CU-04) → 6 Registro de métricas y alertas (CP5) y KPI (CP6)
"""
import re
import time
import unicodedata

from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import Alerta, RegistroHistorico, Ticket
from . import llm, rag

PATRON_CITA = re.compile(r"\[([^\[\]]+?),\s*p[áa]g(?:ina)?\.?\s*(\d+)\]", re.I)

MSG_ESCALADO = ("No encontré una solución confiable en los manuales técnicos. Tu ticket fue derivado "
                "a soporte de Nivel 2 y un especialista humano tomará tu caso.")
MSG_REINTENTO = ("El servicio de inteligencia artificial no está respondiendo en este momento. "
                 "Tu ticket quedó registrado en cola de espera; por favor reintenta en unos instantes.")


class EntradaInvalida(ValueError):
    pass


# ---------- utilidades de registro (CP5 / CP6) ----------

def registrar(db: Session, tipo: str, ticket_id: int | None = None, detalle: dict | None = None,
              usuario_id: int | None = None) -> None:
    db.add(RegistroHistorico(tipo=tipo, ticket_id=ticket_id, detalle=detalle, usuario_id=usuario_id))


def alertar(db: Session, tipo: str, mensaje: str, nivel: str = "media", ticket_id: int | None = None) -> None:
    db.add(Alerta(tipo=tipo, mensaje=mensaje[:500], nivel=nivel, ticket_id=ticket_id))


def _norm(t: str) -> str:
    t = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode()
    return " ".join(t.lower().split())


# ---------- CP1 ----------

def validar_entrada(consulta: str) -> str:
    """CP1: sanitiza y valida caracteres y longitud."""
    s = get_settings()
    limpia = "".join(c for c in (consulta or "") if c.isprintable() or c in "\n\t").strip()
    limpia = re.sub(r"[<>]", "", limpia)  # evita inyección de HTML en vistas
    if len(limpia) < s.min_largo_consulta:
        raise EntradaInvalida(f"La consulta debe tener al menos {s.min_largo_consulta} caracteres.")
    if len(limpia) > s.max_largo_consulta:
        raise EntradaInvalida(f"La consulta no puede superar {s.max_largo_consulta} caracteres.")
    if sum(c.isalpha() for c in limpia) < 5:
        raise EntradaInvalida("Describe el problema con palabras para poder ayudarte.")
    return limpia


# ---------- CP4 ----------

def citas_validas(respuesta: str, fragmentos: list[dict]) -> bool:
    """CP4: la respuesta debe citar al menos un manual + página que realmente se recuperó."""
    permitidas = {(_norm(f["manual"]), f["pagina"]) for f in fragmentos}
    for manual, pagina in PATRON_CITA.findall(respuesta):
        if (_norm(manual), int(pagina)) in permitidas:
            return True
    return False


def fuentes_citadas(respuesta: str, fragmentos: list[dict]) -> list[dict]:
    """Fuentes que la respuesta realmente cita, sin repetir manual+página (mejor similitud primero)."""
    citadas = {(_norm(m), int(p)) for m, p in PATRON_CITA.findall(respuesta)}
    vistas, fuentes = set(), []
    for f in sorted(fragmentos, key=lambda x: -x["similitud"]):
        clave = (_norm(f["manual"]), f["pagina"])
        if clave in citadas and clave not in vistas:
            vistas.add(clave)
            fuentes.append({"manual": f["manual"], "pagina": f["pagina"], "similitud": f["similitud"],
                            "extracto": " ".join(f["contenido"].split())[:220]})
    return sorted(fuentes, key=lambda x: (x["manual"], x["pagina"]))


# ---------- flujo principal (CU-01) ----------

def procesar_ticket(db: Session, consulta_bruta: str, ticket: Ticket | None = None) -> Ticket:
    s = get_settings()
    inicio = time.perf_counter()
    cps: list[dict] = []

    def cp(id_, nombre, ok, detalle):
        cps.append({"id": id_, "nombre": nombre, "ok": ok, "detalle": detalle})

    # 1-2. Recepción y CP1
    consulta = validar_entrada(consulta_bruta)  # lanza EntradaInvalida
    if ticket is None:
        ticket = Ticket(consulta=consulta, estado="recibido", intentos=1)
        db.add(ticket)
        db.flush()  # asigna identificador único
        registrar(db, "ticket_recibido", ticket.id)
    else:
        ticket.intentos += 1
        registrar(db, "ticket_reintento", ticket.id, {"intento": ticket.intentos})
    ticket.respuesta = ticket.fuentes = ticket.motivo_escalamiento = None
    cp("CP1", "Validar entrada", True, f"{len(consulta)} caracteres válidos")

    # 3. CP2: clasificación IA con confianza
    clase = llm.clasificar(consulta)
    ticket.urgencia, ticket.area = clase["urgencia"], clase["area"]
    ticket.confianza_clasificacion = clase["confianza"]
    ambigua = clase["confianza"] < s.umbral_confianza_clasificacion
    cp("CP2", "Clasificar urgencia", not ambigua,
       f"urgencia {ticket.urgencia}, área {ticket.area}, confianza {clase['confianza']:.2f}"
       + (" (ambigua)" if ambigua else ""))

    relevantes: list[dict] = []
    if ambigua:
        # R4 contingencia: los casos ambiguos se escalan automáticamente
        _escalar(db, ticket, "Clasificación ambigua: requiere revisión humana de la prioridad")
        alertar(db, "clasificacion_ambigua", f"Ticket #{ticket.id} con clasificación ambigua", "media", ticket.id)
    else:
        # 4. CP3: recuperación RAG y umbral de similitud
        candidatos = rag.recuperar(db, consulta, s.rag_top_k)
        relevantes = [f for f in candidatos if f["similitud"] >= s.rag_umbral_similitud]
        ticket.similitud_max = max((f["similitud"] for f in candidatos), default=None)
        cp("CP3", "Validar fuentes RAG", bool(relevantes),
           f"{len(relevantes)}/{len(candidatos)} fragmentos sobre umbral {s.rag_umbral_similitud}"
           + (f" (máx. {ticket.similitud_max:.2f})" if ticket.similitud_max is not None else ""))

        if not relevantes:
            # CU-04 extiende CU-02: no se consulta al LLM
            _escalar(db, ticket, "Similitud semántica insuficiente: la consulta no está documentada")
        else:
            # 5. Respuesta + CP4
            try:
                respuesta, modelo = llm.responder(consulta, relevantes)
                ticket.modelo_llm = modelo
            except llm.LLMNoDisponible as e:
                # CU-01 flujo 8a: cola de espera (R2) y registro del incidente
                ticket.estado = "pendiente_reintento"
                ticket.respuesta = MSG_REINTENTO
                cp("CP4", "Controlar respuesta", False, "servicio LLM no disponible")
                registrar(db, "falla_llm", ticket.id, {"error": str(e)[:500]})
                alertar(db, "falla_llm", f"El servicio LLM no respondió (ticket #{ticket.id})", "alta", ticket.id)
            else:
                no_puede = "NO_PUEDO_RESOLVER" in respuesta
                cita_ok = (not no_puede) and citas_validas(respuesta, relevantes)
                cp("CP4", "Controlar respuesta", cita_ok,
                   "cita manual y página" if cita_ok else
                   ("el agente declaró no poder resolver" if no_puede else "bloqueada: sin cita válida"))
                if cita_ok:
                    ticket.estado = "resuelto_ia"
                    ticket.respuesta = respuesta
                    ticket.fuentes = fuentes_citadas(respuesta, relevantes)
                else:
                    _escalar(db, ticket, "El agente no encontró la solución en los manuales" if no_puede
                             else "Respuesta bloqueada por no citar manual y página (R5)")

    # 6. CP5: métricas y alertas
    ticket.tiempo_respuesta_ms = int((time.perf_counter() - inicio) * 1000)
    if ticket.urgencia == "alta":
        alertar(db, "urgencia_alta", f"Ticket #{ticket.id} de urgencia ALTA ({ticket.estado})", "alta", ticket.id)
    cp("CP5", "Registrar métricas y alertas", True, f"{ticket.tiempo_respuesta_ms} ms")

    # CP6: KPI del ticket
    registrar(db, "ticket_procesado", ticket.id, {
        "estado": ticket.estado, "urgencia": ticket.urgencia, "area": ticket.area,
        "tiempo_ms": ticket.tiempo_respuesta_ms, "similitud_max": ticket.similitud_max,
        "modelo": ticket.modelo_llm,
    })
    cp("CP6", "Registrar KPI", True, f"estado {ticket.estado}")
    ticket.puntos_control = cps

    db.commit()
    db.refresh(ticket)
    return ticket


def _escalar(db: Session, ticket: Ticket, motivo: str) -> None:
    """CU-04: deriva el ticket a soporte humano de Nivel 2."""
    ticket.estado = "escalado"
    ticket.motivo_escalamiento = motivo
    ticket.respuesta = MSG_ESCALADO
    registrar(db, "ticket_escalado", ticket.id, {"motivo": motivo})
    alertar(db, "escalamiento", f"Ticket #{ticket.id} derivado a Nivel 2: {motivo}",
            "alta" if ticket.urgencia == "alta" else "media", ticket.id)
