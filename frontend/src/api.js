const SESION_KEY = "sesion_admin";

export const sesion = {
  get: () => {
    try { return JSON.parse(sessionStorage.getItem(SESION_KEY)) || null; } catch { return null; }
  },
  set: (s) => { try { sessionStorage.setItem(SESION_KEY, JSON.stringify(s)); } catch { /* sin storage */ } },
  clear: () => { try { sessionStorage.removeItem(SESION_KEY); } catch { /* sin storage */ } },
};

async function pedir(ruta, { auth = false, ...opts } = {}) {
  const headers = { ...(opts.headers || {}) };
  if (auth) headers.Authorization = `Bearer ${sesion.get()?.token || ""}`;
  const res = await fetch(ruta, { ...opts, headers });
  const datos = await res.json().catch(() => ({}));
  if (!res.ok) {
    const err = new Error(typeof datos.detail === "string" ? datos.detail : "Error del servidor");
    err.status = res.status;
    throw err;
  }
  return datos;
}

const post = (body) => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export const api = {
  salud: () => pedir("/api/salud"),

  // Cliente PYME
  crearTicket: (consulta) => pedir("/api/tickets", post({ consulta })),
  ticket: (id) => pedir(`/api/tickets/${id}`),
  reintentar: (id) => pedir(`/api/tickets/${id}/reintentar`, { method: "POST" }),
  calificar: (id, valor) => pedir(`/api/tickets/${id}/calificar`, post({ valor })),

  // Administrador técnico
  login: (email, password) => pedir("/api/auth/login", post({ email, password })),
  cambiarPassword: (actual, nueva) => pedir("/api/auth/cambiar-password", { auth: true, ...post({ actual, nueva }) }),
  dashboard: () => pedir("/api/dashboard", { auth: true }),
  tickets: (filtros = {}) => {
    const q = new URLSearchParams(Object.entries(filtros).filter(([, v]) => v)).toString();
    return pedir(`/api/dashboard/tickets${q ? `?${q}` : ""}`, { auth: true });
  },
  trazabilidad: (id) => pedir(`/api/dashboard/tickets/${id}/historial`, { auth: true }),
  cerrarTicket: (id, nota) => pedir(`/api/dashboard/tickets/${id}/cerrar`, { auth: true, ...post({ nota }) }),
  alertas: () => pedir("/api/dashboard/alertas", { auth: true }),
  leerAlertas: () => pedir("/api/dashboard/alertas/leer-todas", { auth: true, method: "POST" }),
  configuracion: () => pedir("/api/dashboard/configuracion", { auth: true }),
  manuales: () => pedir("/api/manuals", { auth: true }),
  subirManual: (archivo) => {
    const fd = new FormData();
    fd.append("archivo", archivo);
    return pedir("/api/manuals/upload", { auth: true, method: "POST", body: fd });
  },
  eliminarManual: (id) => pedir(`/api/manuals/${id}`, { auth: true, method: "DELETE" }),
};

export const ESTADOS = {
  resuelto_ia: { txt: "Resuelto por IA", cls: "ok" },
  escalado: { txt: "Derivado a Nivel 2", cls: "esc" },
  pendiente_reintento: { txt: "En cola de espera", cls: "pend" },
  cerrado_n2: { txt: "Cerrado por Nivel 2", cls: "neutro" },
};

export const fecha = (iso) =>
  new Date(iso).toLocaleString("es-CL", { dateStyle: "short", timeStyle: "short" });
