"""Ingestor: el proceso programado.

Cada cierto tiempo recorre TODOS los estudiantes que registraron su URL del
calendario y ejecuta el pipeline de cada uno (ver ingesta.py):
Moodle -> datalake (MinIO) -> MySQL + MongoDB.
"""

import os
import time

from conexiones import esperar, esperar_todo, mysql_conexion
from ingesta import preparar_datalake, procesar_estudiante

INTERVALO_MIN = int(os.getenv("INTERVALO_MINUTOS", "180"))


def migrar_url_del_env():
    """Compatibilidad: si el .env trae una URL, se la asigna al estudiante ESTUDIANTE_ID."""
    url = os.getenv("MOODLE_CALENDAR_URL", "")
    if not url.startswith("http"):
        return
    conexion = mysql_conexion()
    with conexion.cursor() as cur:
        cur.execute(
            "UPDATE estudiantes SET calendario_url = %s WHERE id = %s AND calendario_url IS NULL",
            (url, int(os.getenv("ESTUDIANTE_ID", "1"))),
        )
    conexion.commit()
    conexion.close()


def estudiantes_registrados():
    conexion = mysql_conexion()
    with conexion.cursor() as cur:
        cur.execute("SELECT id, calendario_url FROM estudiantes WHERE calendario_url IS NOT NULL")
        filas = cur.fetchall()
    conexion.close()
    return filas


def ejecutar_ciclo():
    estudiantes = estudiantes_registrados()
    total = 0
    for est in estudiantes:
        try:
            total += procesar_estudiante(est["id"], est["calendario_url"])
        except Exception as error:  # si falla un estudiante, seguimos con los demás
            print(f"Error con el estudiante {est['id']}: {error}", flush=True)
    print(f"Ciclo terminado: {len(estudiantes)} estudiantes, {total} entregas", flush=True)


if __name__ == "__main__":
    esperar("Datalake", preparar_datalake)
    esperar_todo()
    migrar_url_del_env()
    while True:
        ejecutar_ciclo()
        time.sleep(INTERVALO_MIN * 60)
