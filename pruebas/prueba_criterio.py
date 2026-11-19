"""Prueba 3 (criterio de éxito): ¿la app resuelve el problema mejor que Moodle?

Criterio definido ANTES de construir:
  C1. Cobertura: al menos el 95 % de las entregas críticas (peso >= 20 % y vencen en <= 7 días)
      aparecen entre las 5 primeras de la lista que ve el estudiante.
      Se compara con el orden de Moodle (solo por fecha).
  C2. Rendimiento: la API responde la lista de un estudiante en <= 300 ms (percentil 95)
      con datos de 6 sedes y 3.000 estudiantes.

Uso: docker compose exec api python pruebas/prueba_criterio.py
"""

import random
import statistics
import time

import requests

from conexiones import mysql_conexion

API = "http://localhost:8000"
MUESTRA = 300
TOP = 5

conexion = mysql_conexion()
with conexion.cursor() as cur:
    cur.execute("SELECT id FROM estudiantes WHERE correo LIKE '%%@sintetico.uniminuto.test'")
    ids = [f["id"] for f in cur.fetchall()]
conexion.close()
random.seed(7)
muestra = random.sample(ids, min(MUESTRA, len(ids)))

criticas_total = criticas_top_app = criticas_top_moodle = 0
tiempos = []
for est in muestra:
    t0 = time.perf_counter()
    lista_app = requests.get(f"{API}/estudiantes/{est}/entregas", timeout=10).json()
    tiempos.append((time.perf_counter() - t0) * 1000)
    lista_moodle = sorted(lista_app, key=lambda e: e["fecha_entrega"])  # lo que hace Moodle hoy

    criticas = {e["uid"] for e in lista_app if (e["peso"] or 0) >= 20 and e["dias_restantes"] <= 7}
    criticas_total += len(criticas)
    criticas_top_app += len(criticas & {e["uid"] for e in lista_app[:TOP]})
    criticas_top_moodle += len(criticas & {e["uid"] for e in lista_moodle[:TOP]})

cobertura_app = 100 * criticas_top_app / criticas_total if criticas_total else 0
cobertura_moodle = 100 * criticas_top_moodle / criticas_total if criticas_total else 0
p95 = statistics.quantiles(tiempos, n=20)[18]

print(f"Estudiantes evaluados: {len(muestra)} | entregas críticas evaluadas: {criticas_total}\n")
print(f"{'Criterio':45} {'Meta':>10} {'Observado':>12}  Cumple")
print(f"{'C1 Cobertura top-5 (app, por prioridad)':45} {'>= 95 %':>10} {cobertura_app:>10.1f} %  "
      f"{'SÍ' if cobertura_app >= 95 else 'NO'}")
print(f"{'   Referencia: Moodle (orden por fecha)':45} {'-':>10} {cobertura_moodle:>10.1f} %")
print(f"{'C2 Tiempo de respuesta p95':45} {'<= 300 ms':>10} {p95:>9.1f} ms  {'SÍ' if p95 <= 300 else 'NO'}")
print(f"{'   Promedio':45} {'-':>10} {statistics.mean(tiempos):>9.1f} ms")
