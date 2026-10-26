"""Casos de prueba técnicos del flujo con puntos de control (Tabla N°9: unitarias y RAG/precisión).

Ejecutar:  cd backend && pytest -v
"""
import pytest

from app.models import Alerta, RegistroHistorico
from app.security import crear_token, hash_password, leer_token, verificar_password
from app.services import llm, pipeline, rag

FRAG_OK = {"manual": "Manual_IT_Seguridad_v2.pdf", "pagina": 12, "similitud": 0.82,
           "contenido": "Para configurar la VPN ingrese al panel de red y seleccione Añadir conexión."}
FRAG_BAJO = {**FRAG_OK, "similitud": 0.10}


@pytest.fixture
def recuperar(monkeypatch):
    def _set(fragmentos):
        monkeypatch.setattr(rag, "recuperar", lambda db, consulta, k: fragmentos)
    return _set


@pytest.fixture
def clasificacion(monkeypatch):
    def _set(urgencia="media", confianza=0.9):
        monkeypatch.setattr(llm, "clasificar", lambda c: {
            "urgencia": urgencia, "area": "redes", "confianza": confianza, "metodo": "test"})
    _set()
    return _set


# ---------- CP1 ----------

@pytest.mark.parametrize("entrada", ["", "hola", "1234567890!!", "   ?   "])
def test_cp1_rechaza_entradas_invalidas(entrada):
    with pytest.raises(pipeline.EntradaInvalida):
        pipeline.validar_entrada(entrada)


def test_cp1_rechaza_consulta_muy_larga():
    with pytest.raises(pipeline.EntradaInvalida):
        pipeline.validar_entrada("a" * 2001)


def test_cp1_sanitiza_html():
    assert "<" not in pipeline.validar_entrada("<script>no conecta la vpn</script>")


# ---------- CP4 ----------

def test_cp4_acepta_cita_de_fragmento_recuperado():
    assert pipeline.citas_validas("Siga los pasos [Manual_IT_Seguridad_v2.pdf, pág. 12]", [FRAG_OK])


def test_cp4_acepta_variantes_de_formato():
    assert pipeline.citas_validas("ver [manual_it_seguridad_v2.pdf, pagina 12]", [FRAG_OK])


@pytest.mark.parametrize("respuesta", [
    "Configure la VPN en el panel de red.",               # sin cita
    "Siga los pasos [Manual_IT_Seguridad_v2.pdf, pág. 99]",  # página no recuperada
    "Siga los pasos [Otro_manual.pdf, pág. 12]",          # manual inventado
])
def test_cp4_bloquea_respuestas_sin_cita_valida(respuesta):
    assert not pipeline.citas_validas(respuesta, [FRAG_OK])


# ---------- Flujo completo (CU-01) ----------

def test_flujo_resuelve_con_cita(db, recuperar, clasificacion):
    recuperar([FRAG_OK])
    t = pipeline.procesar_ticket(db, "No puedo configurar la VPN en mi equipo nuevo")
    assert t.estado == "resuelto_ia"
    assert t.fuentes[0]["manual"] == "Manual_IT_Seguridad_v2.pdf" and t.fuentes[0]["pagina"] == 12
    assert [c["id"] for c in t.puntos_control] == ["CP1", "CP2", "CP3", "CP4", "CP5", "CP6"]
    assert all(c["ok"] for c in t.puntos_control)
    assert t.tiempo_respuesta_ms is not None


def test_cp3_bajo_umbral_no_consulta_al_llm_y_escala(db, recuperar, clasificacion, monkeypatch):
    """Regla clave (TDD parcial): ninguna respuesta se genera si no se supera el umbral."""
    recuperar([FRAG_BAJO])

    def no_llamar(*a, **k):
        raise AssertionError("No se debe consultar al LLM bajo el umbral")
    monkeypatch.setattr(llm, "responder", no_llamar)

    t = pipeline.procesar_ticket(db, "¿Cómo reparo la cafetera de la oficina?")
    assert t.estado == "escalado"
    assert "Similitud" in t.motivo_escalamiento
    assert any(a.tipo == "escalamiento" for a in db.de_tipo(Alerta))


def test_cp4_respuesta_sin_cita_se_bloquea_y_escala(db, recuperar, clasificacion, monkeypatch):
    recuperar([FRAG_OK])
    monkeypatch.setattr(llm, "responder", lambda c, f: ("Configure la VPN en el panel.", "test"))
    t = pipeline.procesar_ticket(db, "No puedo configurar la VPN en mi equipo nuevo")
    assert t.estado == "escalado"
    assert "no citar" in t.motivo_escalamiento


def test_agente_declara_no_poder_resolver(db, recuperar, clasificacion, monkeypatch):
    recuperar([FRAG_OK])
    monkeypatch.setattr(llm, "responder", lambda c, f: ("NO_PUEDO_RESOLVER", "test"))
    assert pipeline.procesar_ticket(db, "No puedo configurar la VPN en mi equipo").estado == "escalado"


def test_r4_clasificacion_ambigua_se_escala(db, recuperar, clasificacion):
    clasificacion(confianza=0.2)
    recuperar([FRAG_OK])
    t = pipeline.procesar_ticket(db, "tengo un problema con una cosa del sistema")
    assert t.estado == "escalado"
    assert any(a.tipo == "clasificacion_ambigua" for a in db.de_tipo(Alerta))


def test_8a_falla_llm_queda_en_cola_y_registra_incidente(db, recuperar, clasificacion, monkeypatch):
    recuperar([FRAG_OK])

    def caida(*a, **k):
        raise llm.LLMNoDisponible("timeout")
    monkeypatch.setattr(llm, "responder", caida)

    t = pipeline.procesar_ticket(db, "No puedo configurar la VPN en mi equipo nuevo")
    assert t.estado == "pendiente_reintento"
    assert any(r.tipo == "falla_llm" for r in db.de_tipo(RegistroHistorico))
    assert any(a.tipo == "falla_llm" for a in db.de_tipo(Alerta))

    # Reintento cuando el servicio vuelve
    monkeypatch.setattr(llm, "responder", lambda c, f: ("Ver [Manual_IT_Seguridad_v2.pdf, pág. 12]", "test"))
    t = pipeline.procesar_ticket(db, t.consulta, ticket=t)
    assert t.estado == "resuelto_ia" and t.intentos == 2


def test_cp5_alerta_urgencia_alta(db, recuperar, clasificacion):
    clasificacion(urgencia="alta")
    recuperar([FRAG_OK])
    pipeline.procesar_ticket(db, "Urgente: no funciona nada, la VPN se cayó")
    assert any(a.tipo == "urgencia_alta" for a in db.de_tipo(Alerta))


def test_cp6_registra_kpi_del_ticket(db, recuperar, clasificacion):
    recuperar([FRAG_OK])
    pipeline.procesar_ticket(db, "No puedo configurar la VPN en mi equipo nuevo")
    kpi = [r for r in db.de_tipo(RegistroHistorico) if r.tipo == "ticket_procesado"]
    assert kpi and {"estado", "urgencia", "tiempo_ms"} <= kpi[0].detalle.keys()


# ---------- CP2 heurístico (respaldo cuando el LLM no responde) ----------

def test_clasificacion_heuristica_detecta_urgencia_alta():
    r = llm._clasificar_heuristica("Urgente, el sistema está caído y no podemos vender")
    assert r["urgencia"] == "alta"


# ---------- Seguridad básica ----------

def test_password_y_token():
    h = hash_password("clave-segura")
    assert verificar_password("clave-segura", h) and not verificar_password("otra", h)
    token = crear_token(7)
    assert leer_token(token) == 7
    assert leer_token(token[:-2] + "xx") is None


def test_fuentes_solo_citadas_y_sin_duplicados():
    frags = [FRAG_OK, {**FRAG_OK, "similitud": 0.7},
             {**FRAG_OK, "pagina": 8, "similitud": 0.5}, {**FRAG_OK, "pagina": 1, "similitud": 0.48}]
    resp = "1. Paso uno.\n2. Paso dos.\nFuente: [Manual_IT_Seguridad_v2.pdf, pág. 12]"
    fuentes = pipeline.fuentes_citadas(resp, frags)
    assert [(f["pagina"], f["similitud"]) for f in fuentes] == [(12, 0.82)]
