"""Mide la métrica de Precisión del proyecto: 90% de acierto en la clasificación de urgencia (CP2).

Uso (dentro del contenedor backend o con el entorno local):
    python -m app.evaluar_clasificacion                  # usa tests/casos_clasificacion.json
    python -m app.evaluar_clasificacion mis_casos.json

Cada caso: {"consulta": "...", "urgencia": "alta|media|baja"}.
Usa el proveedor configurado en LLM_PROVIDER. Si el LLM falla en algún caso (por ejemplo,
cuota agotada), ese caso se clasifica con la heurística de respaldo y se informa aparte:
la precisión del agente se calcula solo con los casos que clasificó el LLM.
"""
import json
import sys
import time
import warnings
from collections import Counter
from pathlib import Path

warnings.filterwarnings("ignore", category=FutureWarning)

from .services.llm import clasificar, es_mock, proveedor_activo  # noqa: E402

META = 0.90
NIVELES = ["alta", "media", "baja"]
PAUSA_S = 1.0  # evita superar el límite por minuto del nivel gratuito


def main(ruta: str) -> int:
    casos = json.loads(Path(ruta).read_text(encoding="utf-8"))
    print(f"Modelo: {proveedor_activo()}   Casos: {len(casos)}\n")
    matriz = Counter()
    fallos, respaldo = [], 0
    for i, c in enumerate(casos, 1):
        r = clasificar(c["consulta"])
        por_llm = es_mock() or r["metodo"] != "heuristica"
        marca = "✓" if r["urgencia"] == c["urgencia"] else "✗"
        print(f"  [{i:>2}/{len(casos)}] {marca} {c['urgencia']:>5} → {r['urgencia']:<5}"
              f"{'' if por_llm else '  (respaldo: el LLM no respondió)'}", flush=True)
        if not por_llm:
            respaldo += 1
            continue
        matriz[(c["urgencia"], r["urgencia"])] += 1
        if r["urgencia"] != c["urgencia"]:
            fallos.append((c["consulta"], c["urgencia"], r["urgencia"], r["confianza"]))
        if not es_mock():
            time.sleep(PAUSA_S)

    evaluados = sum(matriz.values())
    if evaluados == 0:
        print("\nEl LLM no respondió en ningún caso (¿cuota agotada o API key inválida?). "
              "Revisa: docker compose logs backend --tail 30")
        return 2
    aciertos = sum(v for (real, pred), v in matriz.items() if real == pred)
    precision = aciertos / evaluados
    print(f"\nAcierto: {aciertos}/{evaluados} = {precision:.1%}   (meta {META:.0%}) "
          f"→ {'CUMPLE' if precision >= META else 'NO CUMPLE'}")
    if respaldo:
        print(f"⚠ {respaldo} caso(s) no se evaluaron porque el LLM no respondió; "
              "vuelve a ejecutar más tarde para una medición completa.")
    print("\nMatriz de confusión (filas = real, columnas = predicho)")
    print("        " + "".join(f"{n:>7}" for n in NIVELES))
    for real in NIVELES:
        print(f"{real:>7} " + "".join(f"{matriz[(real, p)]:>7}" for p in NIVELES))
    if fallos:
        print("\nCasos mal clasificados:")
        for consulta, real, pred, conf in fallos:
            print(f" - [{real} → {pred}, conf {conf:.2f}] {consulta}")
    return 0 if precision >= META else 1


if __name__ == "__main__":
    defecto = Path(__file__).resolve().parent.parent / "tests" / "casos_clasificacion.json"
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else str(defecto)))
