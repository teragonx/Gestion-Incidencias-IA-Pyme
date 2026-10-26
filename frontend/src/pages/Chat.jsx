import { useEffect, useRef, useState } from "react";
import { api, ESTADOS } from "../api.js";

const BIENVENIDA = {
  rol: "agente",
  texto:
    "Hola, soy el agente de soporte técnico. Describe tu problema y buscaré la solución en los manuales técnicos de la empresa. Si no la encuentro, derivaré tu caso a un especialista.",
};

export default function Chat() {
  const [mensajes, setMensajes] = useState([BIENVENIDA]);
  const [texto, setTexto] = useState("");
  const [cargando, setCargando] = useState(false);
  const [buscarId, setBuscarId] = useState("");
  const finRef = useRef(null);

  useEffect(() => {
    finRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [mensajes, cargando]);

  const agregar = (m) => setMensajes((ms) => [...ms, m]);
  const reemplazarTicket = (ticket) =>
    setMensajes((ms) => ms.map((x) => (x.ticket?.id === ticket.id ? { ...x, texto: ticket.respuesta, ticket } : x)));

  async function enviar(e) {
    e.preventDefault();
    const consulta = texto.trim();
    if (!consulta || cargando) return;
    setTexto("");
    agregar({ rol: "usuario", texto: consulta });
    setCargando(true);
    try {
      const ticket = await api.crearTicket(consulta);
      agregar({ rol: "agente", texto: ticket.respuesta, ticket });
    } catch (err) {
      agregar({ rol: "agente", error: true, texto: err.message });
    } finally {
      setCargando(false);
    }
  }

  async function reintentar(ticket) {
    setCargando(true);
    try {
      reemplazarTicket(await api.reintentar(ticket.id));
    } catch (err) {
      agregar({ rol: "agente", error: true, texto: err.message });
    } finally {
      setCargando(false);
    }
  }

  async function calificar(ticket, valor) {
    try { reemplazarTicket(await api.calificar(ticket.id, valor)); } catch { /* opcional */ }
  }

  async function consultarEstado(e) {
    e.preventDefault();
    const id = parseInt(buscarId, 10);
    if (!id) return;
    setBuscarId("");
    try {
      const t = await api.ticket(id);
      const extra = t.estado === "cerrado_n2" && t.nota_cierre ? `\n\nRespuesta del especialista: ${t.nota_cierre}` : "";
      agregar({ rol: "agente", texto: `Estado del ticket #${t.id}: ${ESTADOS[t.estado]?.txt || t.estado}.${extra}`, info: true });
    } catch (err) {
      agregar({ rol: "agente", error: true, texto: err.message });
    }
  }

  return (
    <section className="chat">
      <div className="mensajes" aria-live="polite">
        {mensajes.map((m, i) => (
          <Mensaje key={i} m={m} onCalificar={calificar} onReintentar={reintentar} ocupado={cargando} />
        ))}
        {cargando && (
          <div className="estado-agente">
            <span className="puntos"><i /><i /><i /></span>
            Agente de IA analizando manuales…
          </div>
        )}
        <div ref={finRef} />
      </div>

      <form className="entrada" onSubmit={enviar}>
        <textarea
          value={texto}
          onChange={(e) => setTexto(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) enviar(e); }}
          placeholder="Describe tu problema técnico…"
          rows={2}
          maxLength={2000}
          aria-label="Consulta técnica"
        />
        <button type="submit" disabled={cargando || texto.trim().length === 0} aria-label="Enviar">Enviar</button>
      </form>
      <form className="consultar" onSubmit={consultarEstado}>
        <span>¿Ya tienes un ticket?</span>
        <input type="number" min="1" placeholder="N.º de ticket" value={buscarId} onChange={(e) => setBuscarId(e.target.value)} />
        <button type="submit" className="sec peq" disabled={!buscarId}>Consultar estado</button>
      </form>
    </section>
  );
}

function Mensaje({ m, onCalificar, onReintentar, ocupado }) {
  const t = m.ticket;
  const est = t ? ESTADOS[t.estado] : null;
  const clase = ["burbuja", m.rol, m.error ? "error" : "", t ? `est-${t.estado}` : ""].join(" ");

  return (
    <div className={clase}>
      {t && (
        <div className="meta">
          <span className="ticket-id">Ticket #{t.id}</span>
          {t.urgencia && <span className={`badge urg-${t.urgencia}`}>Urgencia {t.urgencia}</span>}
          {est && t.estado !== "resuelto_ia" && <span className={`badge ${est.cls}`}>{est.txt}</span>}
        </div>
      )}

      <div className="texto">{m.texto}</div>

      {t?.fuentes?.length > 0 && (
        <div className="fuentes">
          {t.fuentes.map((f, i) => (
            <span key={i} className="fuente" title={f.extracto}>
              📄 Fuente: {f.manual} (Pág. {f.pagina})
            </span>
          ))}
        </div>
      )}

      {t?.estado === "pendiente_reintento" && (
        <button className="peq" onClick={() => onReintentar(t)} disabled={ocupado}>Reintentar</button>
      )}

      {t && (
        <div className="pie">
          {t.estado === "resuelto_ia" ? (
            <div className="calificar">
              ¿Te sirvió?
              <button className={t.calificacion === 1 ? "sel" : ""} onClick={() => onCalificar(t, 1)} aria-label="Útil">👍</button>
              <button className={t.calificacion === -1 ? "sel" : ""} onClick={() => onCalificar(t, -1)} aria-label="No útil">👎</button>
            </div>
          ) : <span />}
          <details className="cps">
            <summary>Puntos de control</summary>
            <ul>
              {t.puntos_control?.map((cp) => (
                <li key={cp.id} className={cp.ok ? "ok" : "fallo"}>
                  <b>{cp.id}</b> {cp.nombre}: {cp.detalle}
                </li>
              ))}
            </ul>
          </details>
        </div>
      )}
    </div>
  );
}
