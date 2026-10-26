import { useEffect, useState } from "react";
import Chat from "./pages/Chat.jsx";
import Admin from "./pages/Admin.jsx";
import { api } from "./api.js";

const ruta = () => (window.location.hash.startsWith("#/admin") ? "admin" : "chat");

export default function App() {
  const [vista, setVista] = useState(ruta());
  const [empresa, setEmpresa] = useState("");

  useEffect(() => {
    const f = () => setVista(ruta());
    window.addEventListener("hashchange", f);
    api.salud().then((s) => setEmpresa(s.empresa)).catch(() => {});
    return () => window.removeEventListener("hashchange", f);
  }, []);

  return (
    <div className="app">
      <header className="topbar">
        <div className="marca">
          <span className="logo">◆</span>
          <span>Soporte IT Inteligente {empresa}</span>
        </div>
        <nav>
          <a href="#/" className={vista === "chat" ? "activo" : ""}>Soporte</a>
          <a href="#/admin" className={vista === "admin" ? "activo" : ""}>Administración</a>
        </nav>
      </header>
      <main>{vista === "admin" ? <Admin /> : <Chat />}</main>
    </div>
  );
}
