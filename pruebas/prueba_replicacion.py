"""Prueba 2 (distribuida): consecuencia del diseño replicado.

Se escribe en el nodo primario y, de inmediato, se lee desde un nodo secundario
(como haría una sede que lee de su nodo regional más cercano).
Se mide:
  - cuántas lecturas inmediatas llegan DESACTUALIZADAS (el cambio aún no se ve)
  - cuánto tarda el cambio en aparecer en el secundario
con dos niveles de confirmación de escritura:
  w=1         -> responde apenas el primario guarda (rápido, menos garantías)
  w=majority  -> espera a que 2 de 3 nodos lo tengan (más lento, más seguro)

Uso: docker compose exec api python pruebas/prueba_replicacion.py
"""

import statistics
import time
import uuid

from pymongo import ReadPreference, WriteConcern

from conexiones import mongo_cliente

INTENTOS = 200
cliente = mongo_cliente()
base = cliente.entregas


def medir(nivel_escritura):
    escritura = base.get_collection("prueba_replicacion", write_concern=WriteConcern(w=nivel_escritura))
    lectura = base.get_collection("prueba_replicacion", read_preference=ReadPreference.SECONDARY)
    desactualizadas, retrasos, tiempos_escritura = 0, [], []
    for _ in range(INTENTOS):
        clave = str(uuid.uuid4())
        t0 = time.perf_counter()
        escritura.insert_one({"_id": clave, "peso": 80})
        t1 = time.perf_counter()
        tiempos_escritura.append((t1 - t0) * 1000)
        if lectura.find_one({"_id": clave}) is None:
            desactualizadas += 1
            while lectura.find_one({"_id": clave}) is None:  # esperar a que aparezca
                pass
        retrasos.append((time.perf_counter() - t1) * 1000)
    escritura.delete_many({})
    return {
        "escritura": str(nivel_escritura),
        "lecturas_desactualizadas_%": round(100 * desactualizadas / INTENTOS, 1),
        "retraso_visible_promedio_ms": round(statistics.mean(retrasos), 2),
        "retraso_visible_max_ms": round(max(retrasos), 2),
        "escritura_promedio_ms": round(statistics.mean(tiempos_escritura), 2),
    }


print(f"Primario actual: {cliente.admin.command('hello')['primary']}  ({INTENTOS} escrituras por modo)\n")
for resultado in (medir(1), medir("majority")):
    for clave, valor in resultado.items():
        print(f"  {clave:32} {valor}")
    print()
