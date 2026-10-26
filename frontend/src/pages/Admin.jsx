import { useCallback, useEffect, useState } from "react";
import { api, ESTADOS, fecha, sesion } from "../api.js";

const SECCIONES = [
  ["dashboard", "Dashboard"],
  ["manuales", "Gestión de manuales"],
  ["historial", "Historial de consultas"],
  ["alertas", "Alertas"],
  ["config", "Configuración"],
];

export default function Admin() {
  const [usuario, setUsuario] = useState(sesion.get());
  if (!usuario) return <Login onOk={setUsuario} />;
  return <Panel usuario={usuario} onSalir={() => { sesion.clear(); setUsuario(null); }} />;
}

function Login({ onOk }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");

  async function entrar(e) {
    e.preventDefault();
    try {
      const s = await api.login(email, password);
      sesion.set(s);
      onOk(s);
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <form className="login tarjeta" onSubmit={entrar}>
      <h2>Acceso Administrador Técnico</h2>
      <label>Correo<input type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoFocus required /></label>
      <label>Contraseña<input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required /></label>
      {error && <div className="aviso-error">{error}</div>}
      <button type="submit">Ingresar</button>
    </form>
  );
}

function Panel({ usuario, onSalir }) {
  const [seccion, setSeccion] = useState("dashboard");
  const [sinLeer, setSinLeer] = useState(0);

  const manejarError = useCallback((err) => { if (err.status === 401) onSalir(); }, [onSalir]);

  useEffect(() => {
    api.dashboard().then((k) => setSinLeer(k.alertas_sin_leer)).catch(manejarError);
  }, [seccion, manejarError]);

  const props = { manejarError, irA: setSeccion, setSinLeer };

  return (
    <div className="panel">
      <aside className="lateral">
        {SECCIONES.map(([id, txt]) => (
          <button key={id} className={seccion === id ? "activo" : ""} onClick={() => setSeccion(id)}>
            {txt}
            {id === "alertas" && sinLeer > 0 && <span className="contador">{sinLeer}</span>}
          </button>
        ))}
        <div className="usuario">
          <span>{usuario.nombre}</span>
          <button className="sec peq" onClick={onSalir}>Cerrar sesión</button>
        </div>
      </aside>
      <section className="contenido">
        {seccion === "dashboard" && <Dashboard {...props} />}
        {seccion === "manuales" && <Manuales {...props} />}
        {seccion === "historial" && <Historial {...props} />}
        {seccion === "alertas" && <Alertas {...props} />}
        {seccion === "config" && <Configuracion {...props} />}
      </section>
    </div>
  );
}

/* ------------------------------ Dashboard (CU-07) ------------------------------ */

function Dashboard({ manejarError, irA }) {
  const [k, setK] = useState(null);
  useEffect(() => { api.dashboard().then(setK).catch(manejarError); }, [manejarError]);
  if (!k) return <div className="cargando">Cargando…</div>;

  const pct = (x) => (x == null ? "—" : `${Math.round(x * 100)}%`);
  const tiempo = k.tiempo_promedio_ms < 1000 ? `${k.tiempo_promedio_ms} ms` : `${(k.tiempo_promedio_ms / 1000).toFixed(1)} s`;

  return (
    <>
      <div className="cab">
        <div>
          <h1>Dashboard</h1>
          <span className="sub">Modelo: {k.proveedor_llm} · {k.manuales_activos} manuales activos</span>
        </div>
        <button onClick={() => irA("manuales")}>Cargar nuevo manual (PDF)</button>
      </div>

      <div className="kpis">
        <Kpi t="Total de consultas" v={k.total_consultas} n={`${k.escalados} derivadas a Nivel 2`}
          ayuda="Tickets recibidos por el agente desde el inicio." />
        <Kpi t="Tasa de resolución IA" v={pct(k.tasa_resolucion_ia)} n={`${k.resueltos_ia} resueltas sin intervención humana`}
          ayuda="Porcentaje de tickets que el agente resolvió citando un manual." />
        <Kpi t="Tiempo de ahorro" v={`${k.horas_ahorradas_mes} h/mes`} n={`${k.horas_ahorradas_total} h en total`}
          ayuda="Horas de técnico que no se usaron: tickets resueltos por IA × minutos que toma resolverlos manualmente." />
        <Kpi t="Tiempo de respuesta" v={tiempo} n={k.reduccion_tiempo_respuesta != null ? `${pct(k.reduccion_tiempo_respuesta)} menos que el proceso manual` : "sin datos"}
          ayuda="Promedio desde que llega la consulta hasta la respuesta. Meta del proyecto: al menos 40% menos que el proceso manual." />
        <Kpi t="Satisfacción" v={pct(k.satisfaccion)} n={`${k.calificadas} calificaciones`}
          ayuda="Porcentaje de 👍 sobre el total de respuestas calificadas por los clientes." />
      </div>

      <div className="grid2">
        <div className="tarjeta">
          <h3>Consultas por semana</h3>
          <GraficoSemanas datos={k.consultas_por_semana} />
        </div>
        <div className="tarjeta">
          <h3>Tickets por urgencia</h3>
          <Urgencias datos={k.por_urgencia} />
          {k.pendientes_reintento > 0 && (
            <p className="nota">⚠ {k.pendientes_reintento} ticket(s) en cola de espera por falla del LLM.</p>
          )}
        </div>
      </div>
    </>
  );
}

function Kpi({ t, v, n, ayuda }) {
  return (
    <div className="kpi tarjeta" title={ayuda}>
      <span className="kpi-t">{t} <span className="ayuda" aria-label={ayuda}>?</span></span>
      <span className="kpi-v">{v}</span>
      <span className="kpi-n">{n}</span>
    </div>
  );
}

function GraficoSemanas({ datos }) {
  const max = Math.max(1, ...datos.flatMap((d) => [d.resueltas_ia, d.otras]));
  return (
    <div className="grafico">
      <div className="barras">
        {datos.map((d) => (
          <div key={d.semana} className="col">
            <div className="par">
              <div className="barra ia" style={{ height: `${(d.resueltas_ia / max) * 100}%` }}
                title={`${d.resueltas_ia} resueltas por IA`}><span>{d.resueltas_ia || ""}</span></div>
              <div className="barra otras" style={{ height: `${(d.otras / max) * 100}%` }}
                title={`${d.otras} derivadas o pendientes`}><span>{d.otras || ""}</span></div>
            </div>
            <span className="lbl">{d.semana.slice(5).split("-").reverse().join("/")}</span>
          </div>
        ))}
      </div>
      <div className="leyenda"><span><i className="ia" />Resueltas por IA</span><span><i className="otras" />Derivadas / pendientes</span></div>
    </div>
  );
}

function Urgencias({ datos }) {
  const total = Math.max(1, datos.alta + datos.media + datos.baja);
  return (
    <div className="urgencias">
      {["alta", "media", "baja"].map((u) => (
        <div key={u} className="urg-fila">
          <span className="urg-lbl">{u}</span>
          <div className="urg-barra"><div className={`urg-${u}`} style={{ width: `${(datos[u] / total) * 100}%` }} /></div>
          <span className="urg-num">{datos[u]}</span>
        </div>
      ))}
    </div>
  );
}

/* --------------------------- Gestión de manuales (CU-06) --------------------------- */

function Manuales({ manejarError }) {
  const [manuales, setManuales] = useState([]);
  const [archivo, setArchivo] = useState(null);
  const [estado, setEstado] = useState("");
  const [procesando, setProcesando] = useState(false);

  const cargar = useCallback(() => api.manuales().then(setManuales).catch(manejarError), [manejarError]);
  useEffect(() => { cargar(); }, [cargar]);

  async function subir(e) {
    e.preventDefault();
    if (!archivo) return;
    setProcesando(true);
    setEstado("Procesando, fragmentando y vectorizando el manual…");
    try {
      const m = await api.subirManual(archivo);
      setEstado(`✓ ${m.nombre} indexado: ${m.paginas} páginas, ${m.fragmentos_total} fragmentos.`);
      setArchivo(null);
      e.target.reset();
      cargar();
    } catch (err) {
      setEstado(`✗ ${err.message}`);
      manejarError(err);
    } finally {
      setProcesando(false);
    }
  }

  async function eliminar(m) {
    if (!window.confirm(`¿Eliminar "${m.nombre}" de la base de conocimiento?`)) return;
    await api.eliminarManual(m.id).catch(manejarError);
    cargar();
  }

  return (
    <>
      <div className="cab"><div><h1>Gestión de manuales</h1>
        <span className="sub">Base de conocimiento del agente (RAG) · {manuales.length} documentos activos</span></div></div>
      <div className="tarjeta">
        <form className="subida" onSubmit={subir}>
          <input type="file" accept="application/pdf,.pdf" onChange={(e) => setArchivo(e.target.files[0] || null)} />
          <button type="submit" disabled={!archivo || procesando}>Cargar nuevo manual (PDF)</button>
        </form>
        {estado && <div className="estado-subida">{estado}</div>}
      </div>
      <div className="tarjeta">
        <ul className="lista-manuales">
          {manuales.map((m) => (
            <li key={m.id}>
              <span>📄 <b>{m.nombre}</b> · {m.paginas} págs. · {m.fragmentos_total} fragmentos · {fecha(m.creado_en)}</span>
              <button className="sec peq" onClick={() => eliminar(m)}>Eliminar</button>
            </li>
          ))}
          {manuales.length === 0 && <li className="vacio">Aún no hay manuales. Sin ellos el agente derivará todas las consultas a Nivel 2.</li>}
        </ul>
      </div>
    </>
  );
}

/* --------------------------- Historial de consultas --------------------------- */

function Historial({ manejarError }) {
  const [filtros, setFiltros] = useState({ estado: "", urgencia: "" });
  const [tickets, setTickets] = useState([]);
  const [sel, setSel] = useState(null);

  const cargar = useCallback(() => api.tickets(filtros).then(setTickets).catch(manejarError), [filtros, manejarError]);
  useEffect(() => { cargar(); }, [cargar]);

  return (
    <>
      <div className="cab"><div><h1>Historial de consultas</h1></div>
        <div className="filtros">
          <select value={filtros.estado} onChange={(e) => setFiltros({ ...filtros, estado: e.target.value })} aria-label="Estado">
            <option value="">Todos los estados</option>
            {Object.entries(ESTADOS).map(([k, v]) => <option key={k} value={k}>{v.txt}</option>)}
          </select>
          <select value={filtros.urgencia} onChange={(e) => setFiltros({ ...filtros, urgencia: e.target.value })} aria-label="Urgencia">
            <option value="">Toda urgencia</option>
            <option value="alta">Alta</option><option value="media">Media</option><option value="baja">Baja</option>
          </select>
        </div>
      </div>
      <div className="tarjeta tabla-wrap">
        <table>
          <thead><tr><th>#</th><th>Fecha</th><th>Consulta</th><th>Urgencia</th><th>Estado</th><th>Tiempo</th><th>Calif.</th></tr></thead>
          <tbody>
            {tickets.map((t) => (
              <tr key={t.id} onClick={() => setSel(t)} className={sel?.id === t.id ? "sel" : ""}>
                <td>{t.id}</td>
                <td>{fecha(t.creado_en)}</td>
                <td className="consulta">{t.consulta}</td>
                <td><span className={`badge urg-${t.urgencia}`}>{t.urgencia}</span></td>
                <td><span className={`badge ${ESTADOS[t.estado]?.cls}`}>{ESTADOS[t.estado]?.txt || t.estado}</span></td>
                <td>{t.tiempo_respuesta_ms} ms</td>
                <td>{t.calificacion === 1 ? "👍" : t.calificacion === -1 ? "👎" : "—"}</td>
              </tr>
            ))}
            {tickets.length === 0 && <tr><td colSpan={7} className="vacio">Sin tickets</td></tr>}
          </tbody>
        </table>
      </div>
      {sel && <DetalleTicket ticket={sel} onCerrado={(t) => { setSel(t); cargar(); }} manejarError={manejarError} />}
    </>
  );
}

function DetalleTicket({ ticket: t, onCerrado, manejarError }) {
  const [traza, setTraza] = useState([]);
  const [nota, setNota] = useState("");
  const [error, setError] = useState("");

  useEffect(() => { api.trazabilidad(t.id).then(setTraza).catch(manejarError); }, [t, manejarError]);

  async function cerrar(e) {
    e.preventDefault();
    try { onCerrado(await api.cerrarTicket(t.id, nota)); setNota(""); }
    catch (err) { setError(err.message); }
  }

  return (
    <div className="tarjeta detalle">
      <h3>Ticket #{t.id} · {ESTADOS[t.estado]?.txt}</h3>
      <p className="consulta-full">“{t.consulta}”</p>
      <dl>
        <dt>Clasificación</dt><dd>Urgencia {t.urgencia}, área {t.area}, confianza {t.confianza_clasificacion?.toFixed(2) ?? "—"}</dd>
        <dt>Similitud máx.</dt><dd>{t.similitud_max?.toFixed(2) ?? "—"}</dd>
        <dt>Modelo</dt><dd>{t.modelo_llm || "—"} · intentos: {t.intentos}</dd>
        {t.motivo_escalamiento && <><dt>Motivo de derivación</dt><dd>{t.motivo_escalamiento}</dd></>}
        <dt>Respuesta</dt><dd className="pre">{t.respuesta}</dd>
        {t.nota_cierre && <><dt>Resolución Nivel 2</dt><dd className="pre">{t.nota_cierre}</dd></>}
      </dl>
      <div className="grid2 igual">
        <div>
          <h4>Puntos de control</h4>
          <ul className="cps-lista">
            {t.puntos_control?.map((cp) => <li key={cp.id} className={cp.ok ? "ok" : "fallo"}><b>{cp.id}</b> {cp.nombre}: {cp.detalle}</li>)}
          </ul>
        </div>
        <div>
          <h4>Trazabilidad</h4>
          <ul className="traza">
            {traza.map((r) => <li key={r.id}><span>{fecha(r.creado_en)}</span> {r.tipo.replaceAll("_", " ")}</li>)}
          </ul>
        </div>
      </div>
      {(t.estado === "escalado" || t.estado === "pendiente_reintento") && (
        <form className="cierre" onSubmit={cerrar}>
          <textarea rows={2} placeholder="Solución entregada por el especialista de Nivel 2…" value={nota} onChange={(e) => setNota(e.target.value)} />
          <button type="submit" disabled={nota.trim().length < 3}>Cerrar ticket</button>
          {error && <div className="aviso-error">{error}</div>}
        </form>
      )}
    </div>
  );
}

/* ------------------------------ Alertas (CP5) ------------------------------ */

function Alertas({ manejarError, setSinLeer }) {
  const [alertas, setAlertas] = useState([]);
  const cargar = useCallback(() => api.alertas().then(setAlertas).catch(manejarError), [manejarError]);
  useEffect(() => { cargar(); }, [cargar]);

  async function leerTodas() {
    await api.leerAlertas().catch(manejarError);
    setSinLeer(0);
    cargar();
  }

  return (
    <>
      <div className="cab"><div><h1>Alertas</h1><span className="sub">Punto de control CP5</span></div>
        <button className="sec" onClick={leerTodas}>Marcar todas como leídas</button></div>
      <div className="tarjeta">
        <ul className="alertas">
          {alertas.map((a) => (
            <li key={a.id} className={`nivel-${a.nivel} ${a.leida ? "leida" : ""}`}>
              <span className="punto" />
              <span className="msg">{a.mensaje}</span>
              <span className="cuando">{fecha(a.creado_en)}</span>
            </li>
          ))}
          {alertas.length === 0 && <li className="vacio">Sin alertas</li>}
        </ul>
      </div>
    </>
  );
}

/* ------------------------------ Configuración ------------------------------ */

const ETIQUETAS = {
  empresa: "Empresa", llm_principal: "Modelo LLM principal", llm_alternativo: "Modelo alternativo (R2)",
  llm_timeout_s: "Tiempo máximo de espera del LLM (s)", modelo_embeddings: "Modelo de embeddings",
  umbral_similitud_cp3: "Umbral de similitud (CP3)", fragmentos_top_k: "Fragmentos recuperados (k)",
  tamano_fragmento: "Tamaño de fragmento (caracteres)", solapamiento_fragmento: "Solapamiento (caracteres)",
  umbral_confianza_cp2: "Confianza mínima de clasificación (CP2)", largo_consulta: "Largo de consulta (CP1)",
  minutos_ticket_manual: "Minutos por ticket manual", minutos_respuesta_manual: "Minutos de respuesta manual (línea base)",
  limite_consultas_por_minuto: "Límite de consultas por minuto (R10)",
};

function Configuracion({ manejarError }) {
  const [cfg, setCfg] = useState(null);
  const [actual, setActual] = useState("");
  const [nueva, setNueva] = useState("");
  const [msg, setMsg] = useState("");

  useEffect(() => { api.configuracion().then(setCfg).catch(manejarError); }, [manejarError]);

  async function cambiar(e) {
    e.preventDefault();
    try { await api.cambiarPassword(actual, nueva); setMsg("✓ Contraseña actualizada"); setActual(""); setNueva(""); }
    catch (err) { setMsg(`✗ ${err.message}`); }
  }

  return (
    <>
      <div className="cab"><div><h1>Configuración</h1><span className="sub">Los parámetros se modifican en el archivo .env del servidor</span></div></div>
      <div className="grid2">
        <div className="tarjeta">
          <h3>Parámetros del agente</h3>
          <table className="tabla-cfg"><tbody>
            {cfg && Object.entries(cfg).map(([k, v]) => (
              <tr key={k}><th>{ETIQUETAS[k] || k}</th><td>{Array.isArray(v) ? v.join(" – ") : v ?? "—"}</td></tr>
            ))}
          </tbody></table>
        </div>
        <form className="tarjeta form-col" onSubmit={cambiar}>
          <h3>Cambiar contraseña</h3>
          <label>Contraseña actual<input type="password" value={actual} onChange={(e) => setActual(e.target.value)} required /></label>
          <label>Nueva contraseña (mín. 8)<input type="password" minLength={8} value={nueva} onChange={(e) => setNueva(e.target.value)} required /></label>
          <button type="submit">Guardar</button>
          {msg && <div className="estado-subida">{msg}</div>}
        </form>
      </div>
    </>
  );
}
