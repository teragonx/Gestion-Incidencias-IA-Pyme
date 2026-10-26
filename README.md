# Prototipo de sistema automatizado de gestión de incidencias basado en agentes IA para PYMES

Proyecto de título · Andrés Sebastián Latoja Cortez · Ingeniería en Computación e Informática (2026)

Sistema de soporte técnico de Nivel 1. El Cliente PYME escribe su problema en un chat, el agente
recupera la solución desde los manuales técnicos PDF de la empresa (RAG) y responde citando el
manual y la página. Si no encuentra contexto suficiente, deriva el ticket a soporte humano de Nivel 2.
El Administrador Técnico supervisa KPIs, alertas e historial, y carga nuevos manuales.

## Arquitectura (sección 4.3 del informe)

| Contenedor | Imagen | Función |
|---|---|---|
| `frontend` | `nginx:alpine` | Aplicación React compilada + proxy reverso hacia `/api` |
| `backend` | `python:3.11-slim` | Uvicorn + FastAPI + cadenas de LangChain; variables de entorno seguras |
| `db` | `pgvector/pgvector:pg16` | PostgreSQL relacional + índice vectorial, con volumen persistente |
| Servicio LLM | nube (HTTPS) | OpenAI por defecto; intercambiable por `.env` (R2) |

## Cómo ejecutarlo

Requisito: [Docker Desktop](https://www.docker.com/products/docker-desktop/).

```bash
copy .env.example .env      # Linux/Mac: cp .env.example .env
# Edita .env: OPENAI_API_KEY, SECRET_KEY y la contraseña del administrador
docker compose up --build
```

- Chat del cliente: http://localhost:8080
- Panel del administrador: http://localhost:8080/#/admin (usuario y clave de `ADMIN_EMAIL` / `ADMIN_PASSWORD`)

Sin API key puedes poner `LLM_PROVIDER=mock` para recorrer el flujo completo con respuestas simuladas.
La primera carga de un manual descarga el modelo de embeddings multilingüe (~120 MB), que queda en un volumen.

## Pruebas (Tabla N°9 del informe)

```bash
docker compose exec backend pytest -v                          # unitarias: CP1–CP6, CU-04, 8a, R4, seguridad
docker compose exec backend python -m app.evaluar_clasificacion   # métrica de precisión: 90% de acierto (CP2)
```

`evaluar_clasificacion` usa `tests/casos_clasificacion.json` (30 casos etiquetados) y el LLM
configurado; imprime el porcentaje de acierto, la matriz de confusión y los casos fallidos.
Conviene agregar consultas reales de la PYME a ese archivo.

## Desarrollo sin Docker (opcional)

```bash
cd backend
python -m venv .venv && .venv\Scripts\activate      # Linux/Mac: source .venv/bin/activate
pip install -r requirements.txt
set DATABASE_URL=postgresql+psycopg://soporte:clave@localhost:5432/incidencias
uvicorn app.main:app --reload                          # Swagger/OpenAPI en http://localhost:8000/docs

cd ../frontend && npm install && npm run dev           # http://localhost:5173
```

(Para usar la base de Docker desde tu equipo, agrega `ports: ["5432:5432"]` al servicio `db`.)

## Control de versiones (R6)

```bash
git init -b main && git add . && git commit -m "MVP inicial"
git checkout -b develop
```

## Trazabilidad con el informe

| Elemento del informe | Implementación |
|---|---|
| CU-01 Registrar consulta técnica | `POST /api/tickets` → `services/pipeline.py::procesar_ticket` |
| CU-02 Recuperar contexto semántico | `services/rag.py::recuperar` (distancia coseno en pgvector) |
| CU-03 Validar respuesta con citas | `pipeline.citas_validas` (CP4) |
| CU-04 Escalar ticket a soporte humano | `pipeline._escalar`; cierre por Nivel 2 en `POST /api/dashboard/tickets/{id}/cerrar` |
| CU-05 Calificar resolución | `POST /api/tickets/{id}/calificar` (👍/👎 en el chat) |
| CU-06 Cargar y vectorizar manuales PDF | `POST /api/manuals/upload` → `PyPDFLoader` + `RecursiveCharacterTextSplitter` (LangChain) |
| CU-07 Visualizar dashboard y KPIs | `GET /api/dashboard` + vista Dashboard |
| CU-01 flujo 6a (similitud insuficiente) | CP3 sin fragmentos sobre el umbral → no se llama al LLM, estado "Derivado a Nivel 2" |
| CU-01 flujo 8a (falla del LLM) | Estado `pendiente_reintento` (cola de espera), registro del incidente, alerta y botón **Reintentar** |
| CP1 Validar entrada | `pipeline.validar_entrada` (caracteres, longitud, sanitización) |
| CP2 Clasificar urgencia | `llm.clasificar` con confianza; casos ambiguos se escalan (R4) |
| CP3 Validar fuentes RAG | umbral `RAG_UMBRAL_SIMILITUD` |
| CP4 Controlar respuesta | cita obligatoria `[manual.pdf, pág. N]`; si falta, se bloquea (R5) |
| CP5 Registrar métricas y alertas | tiempo de respuesta + tabla `alertas` (urgencia alta, escalamiento, falla LLM) |
| CP6 Registrar KPI | tabla `registros_historicos` (evento `ticket_procesado`) |
| Modelo de datos (Sprint 2) | `usuarios`, `tickets`, `registros_historicos`, `alertas`, `manuales`, `fragmentos` |
| Sesión autenticada del administrador | `POST /api/auth/login`, contraseñas PBKDF2, token firmado HMAC |
| R2 Dependencia del proveedor IA | LangChain `init_chat_model` + variables de entorno + modelo alternativo |
| R3 Obsolescencia | Docker + versiones fijadas en `requirements.txt` y `package.json` |
| R9 Adopción del administrador | KPIs con ayuda contextual (?) |
| R10 Sobrecarga | límite de consultas por minuto por IP |
| Vista de interfaz (Fig. 4) | Chat con fuente (PDF y página), "Agente de IA analizando manuales…" y 👍/👎 |
| Vista de administrador (Fig. 5) | Menú Dashboard / Gestión de manuales / Historial de consultas / Configuración; KPIs Total de consultas, Tasa de resolución IA, Tiempo de ahorro (h/mes); gráfico de consultas por semana; botón "Cargar nuevo manual (PDF)" |
| Métricas del proyecto (2.4) | Tasa de resolución, reducción del tiempo de respuesta vs. línea base manual, script de precisión del 90% |
