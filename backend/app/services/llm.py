"""Capa de acceso al LLM desacoplada del proveedor mediante LangChain (mitigación R2).

- Cambiar de proveedor = cambiar LLM_PROVIDER / LLM_MODEL en .env.
- Si el modelo principal falla, se intenta el modelo alternativo (LLM_FALLBACK_*).
- Si ambos fallan se lanza LLMNoDisponible y el ticket queda en cola de espera (CU-01, flujo 8a).
- LLM_PROVIDER=mock permite probar todo el flujo sin API key.
"""
import json
import re
from functools import lru_cache

from langchain_core.prompts import ChatPromptTemplate

from ..config import MODELOS_POR_DEFECTO, get_settings

URGENCIAS = {"alta", "media", "baja"}
AREAS = {"hardware", "software", "redes", "cuentas", "facturacion", "otro"}


class LLMNoDisponible(RuntimeError):
    """El servicio LLM externo no respondió (timeout, caída o error de API)."""


PROMPT_CLASIFICAR = ChatPromptTemplate.from_messages([
    ("system",
     "Eres el clasificador de tickets de soporte técnico de Nivel 1 de una PYME chilena.\n"
     "Responde SOLO con un JSON: "
     '{{"urgencia": "alta|media|baja", "area": "hardware|software|redes|cuentas|facturacion|otro", '
     '"confianza": número entre 0 y 1}}\n\n'
     "Criterios de urgencia:\n"
     "- alta: la operación del negocio está detenida, hay pérdida de datos o un problema de seguridad.\n"
     "- media: afecta el trabajo pero existe una alternativa temporal.\n"
     "- baja: dudas de uso, configuraciones o solicitudes menores.\n"
     "La confianza indica qué tan seguro estás; usa valores bajos si la consulta es ambigua."),
    ("human", "Consulta: {consulta}"),
])

PROMPT_RESPONDER = ChatPromptTemplate.from_messages([
    ("system",
     "Eres el agente de soporte técnico de Nivel 1 de la empresa {empresa}.\n"
     "Responde usando EXCLUSIVAMENTE el contexto de los manuales técnicos entregado.\n\n"
     "Reglas obligatorias:\n"
     "1. No inventes información que no esté en el contexto.\n"
     "2. Termina la respuesta con una línea 'Fuente: [nombre_del_manual.pdf, pág. N]' usando exactamente "
     "el nombre y la página indicados en el contexto. Si usaste varias páginas, cítalas todas en esa línea, "
     "separadas por coma. No repitas la cita en cada paso.\n"
     "3. Usa solo las páginas que realmente respondan la consulta; ignora el contexto que no sea pertinente.\n"
     "4. Si el contexto no alcanza para resolver la consulta, responde únicamente: NO_PUEDO_RESOLVER\n"
     "5. Responde en español, breve y con pasos numerados cuando corresponda."),
    ("human", "Contexto:\n{contexto}\n\nConsulta del cliente: {consulta}"),
])


@lru_cache
def _crear_chat(proveedor: str, modelo: str):
    from langchain.chat_models import init_chat_model

    s = get_settings()
    return init_chat_model(
        modelo or MODELOS_POR_DEFECTO.get(proveedor),
        model_provider=proveedor,
        temperature=0,
        timeout=s.llm_timeout_s,
        max_retries=s.llm_reintentos,
    )


def es_mock() -> bool:
    return get_settings().llm_provider == "mock"


def _cadena_modelos() -> list[tuple[str, str]]:
    """[(proveedor, modelo), ...]: principal y, si existe, alternativo (contingencia R2)."""
    s = get_settings()
    modelos = [(s.llm_provider, s.llm_model)]
    if s.llm_fallback_provider:
        modelos.append((s.llm_fallback_provider, s.llm_fallback_model))
    return modelos


def etiqueta(proveedor: str, modelo: str = "") -> str:
    if proveedor == "mock":
        return "mock"
    return f"{proveedor}:{modelo or MODELOS_POR_DEFECTO.get(proveedor, '')}"


def proveedor_activo() -> str:
    s = get_settings()
    return etiqueta(s.llm_provider, s.llm_model)


def _invocar(prompt, **variables) -> tuple[str, str]:
    """Ejecuta el prompt con el modelo principal y, si falla, con el alternativo."""
    errores = []
    for proveedor, modelo in _cadena_modelos():
        nombre = etiqueta(proveedor, modelo)
        try:
            resp = (prompt | _crear_chat(proveedor, modelo)).invoke(variables)
            contenido = resp.content
            if isinstance(contenido, list):  # algunos proveedores devuelven bloques
                contenido = "".join(c.get("text", "") if isinstance(c, dict) else str(c) for c in contenido)
            return contenido.strip(), nombre
        except Exception as e:  # timeout, error de red, cuota, etc.
            errores.append(f"{nombre}: {type(e).__name__}: {str(e)[:160]}")
    raise LLMNoDisponible(" | ".join(errores) or "Sin modelos configurados")


# ---------- CP2: clasificación de urgencia y área ----------

def _clasificar_heuristica(consulta: str) -> dict:
    t = consulta.lower()
    alta = ("no funciona nada", "caído", "caido", "detenid", "urgente", "virus", "hackeo", "hackea",
            "perdí", "perdi ", "borr", "no puedo vender", "bloquead", "ransomware", "robo")
    media = ("error", "falla", "lento", "no puedo", "no imprime", "no conecta", "no enciende",
             "no abre", "se cae", "no carga")
    if any(p in t for p in alta):
        urgencia, confianza = "alta", 0.8
    elif any(p in t for p in media):
        urgencia, confianza = "media", 0.7
    else:
        urgencia, confianza = "baja", 0.6
    areas = {
        "redes": ("wifi", "internet", " red", "router", "vpn", "conexión", "conexion"),
        "cuentas": ("contraseña", "clave", "usuario", "acceso", "login", "sesión", "sesion", "correo"),
        "hardware": ("impresora", "pantalla", "teclado", "equipo", "computador", "mouse", "notebook"),
        "facturacion": ("factura", "boleta", "pago", "cobro", "sii"),
        "software": ("programa", "sistema", "aplicación", "aplicacion", "instalar", "actualiz", "office"),
    }
    area = next((a for a, pal in areas.items() if any(p in t for p in pal)), "otro")
    return {"urgencia": urgencia, "area": area, "confianza": confianza, "metodo": "heuristica"}


def clasificar(consulta: str) -> dict:
    if es_mock():
        return _clasificar_heuristica(consulta)
    try:
        texto, modelo = _invocar(PROMPT_CLASIFICAR, consulta=consulta)
        datos = json.loads(re.search(r"\{.*\}", texto, re.S).group(0))
        urgencia = str(datos.get("urgencia", "")).lower()
        area = str(datos.get("area", "")).lower()
        confianza = float(datos.get("confianza", 0))
        if urgencia not in URGENCIAS:  # respuesta inválida → se trata como ambigua (R4)
            urgencia, confianza = "media", 0.0
        return {"urgencia": urgencia, "area": area if area in AREAS else "otro",
                "confianza": max(0.0, min(1.0, confianza)), "metodo": modelo}
    except (LLMNoDisponible, AttributeError, ValueError, TypeError):
        # Si el LLM no responde, la clasificación no bloquea el flujo: se usa la heurística.
        return _clasificar_heuristica(consulta)


# ---------- Generación de respuesta con RAG ----------

def responder(consulta: str, fragmentos: list[dict]) -> tuple[str, str]:
    """Devuelve (respuesta, modelo_usado). Lanza LLMNoDisponible si no hay respuesta."""
    if es_mock():
        return _responder_mock(fragmentos), "mock"
    contexto = "\n\n".join(f"[{f['manual']}, pág. {f['pagina']}]\n{f['contenido']}" for f in fragmentos)
    return _invocar(PROMPT_RESPONDER, empresa=get_settings().nombre_empresa,
                    contexto=contexto, consulta=consulta)


def _responder_mock(fragmentos: list[dict]) -> str:
    f = fragmentos[0]
    extracto = " ".join(f["contenido"].split())[:400]
    return (
        "(Respuesta simulada: configura LLM_PROVIDER y su API key en .env para respuestas reales.)\n\n"
        f"Según la documentación técnica: {extracto}… [{f['manual']}, pág. {f['pagina']}]"
    )
