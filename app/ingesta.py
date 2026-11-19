"""Pipeline de un estudiante: Moodle -> datalake -> MySQL + MongoDB.

Lo usan dos piezas:
  - ingestor.py: lo repite para todos los estudiantes cada cierto tiempo.
  - api.py: lo ejecuta al instante cuando alguien se registra o cambia su URL.
"""

import io
import json
import os
from datetime import datetime, timezone

import pymysql
import requests
from icalendar import Calendar

from conexiones import minio_cliente, mongo_cliente, mysql_conexion
from procesamiento import extraer_peso, limpiar_titulo

BUCKET = os.getenv("MINIO_BUCKET", "datalake")
minio = minio_cliente()
mongo = mongo_cliente()


# --- Lectura del calendario ------------------------------------------------
def obtener_materia(evento):
    categoria = evento.get("CATEGORIES")
    if categoria is None:
        return "SIN-MATERIA"
    if isinstance(categoria, list):
        categoria = categoria[0]
    return str(categoria.cats[0])


def obtener_fecha(evento):
    fecha = evento.get("DTSTART").dt
    if not isinstance(fecha, datetime):  # evento de día completo
        fecha = datetime(fecha.year, fecha.month, fecha.day)
    if fecha.tzinfo is None:
        fecha = fecha.replace(tzinfo=timezone.utc)
    return fecha.astimezone(timezone.utc)


def extraer_entregas(contenido_ics: bytes):
    calendario = Calendar.from_ical(contenido_ics)
    ahora = datetime.now(timezone.utc)
    entregas = []
    for evento in calendario.walk("VEVENT"):
        fecha = obtener_fecha(evento)
        if fecha < ahora:
            continue
        titulo_original = str(evento.get("SUMMARY"))
        entregas.append({
            "uid": str(evento.get("UID")),
            "titulo": limpiar_titulo(titulo_original),
            "titulo_original": titulo_original,
            "curso": obtener_materia(evento),
            "peso_detectado": extraer_peso(titulo_original),
            "fecha_entrega": fecha.isoformat(),
        })
    entregas.sort(key=lambda e: e["fecha_entrega"])
    return entregas


# --- Escritura en cada capa --------------------------------------------------
def preparar_datalake():
    if not minio.bucket_exists(BUCKET):
        minio.make_bucket(BUCKET)


def guardar_en_datalake(ruta, contenido: bytes, tipo):
    minio.put_object(BUCKET, ruta, io.BytesIO(contenido), len(contenido), content_type=tipo)


def registrar_en_mysql(estudiante_id, entregas):
    """Crea cursos/actividades que no existan y devuelve el peso vigente de cada actividad."""
    pesos = {}
    conexion = mysql_conexion()
    try:
        with conexion.cursor() as cur:
            cur.execute(
                """SELECT e.sede_id, s.nombre, s.region FROM estudiantes e
                   JOIN sedes s ON s.id = e.sede_id WHERE e.id = %s""",
                (estudiante_id,),
            )
            sede = cur.fetchone()
            for e in entregas:
                cur.execute(
                    "INSERT IGNORE INTO cursos (codigo, nombre, sede_id) VALUES (%s, %s, %s)",
                    (e["curso"], e["curso"], sede["sede_id"]),
                )
                cur.execute(
                    "INSERT IGNORE INTO matriculas (estudiante_id, curso_codigo) VALUES (%s, %s)",
                    (estudiante_id, e["curso"]),
                )
                fecha = datetime.fromisoformat(e["fecha_entrega"]).replace(tzinfo=None)
                # Si la actividad ya existe se actualizan título y fecha (el profe pudo moverla),
                # pero NO el peso que el estudiante haya configurado.
                cur.execute(
                    """INSERT INTO actividades (uid_moodle, curso_codigo, titulo, peso, fecha_entrega)
                       VALUES (%s, %s, %s, NULL, %s)
                       ON DUPLICATE KEY UPDATE titulo = VALUES(titulo),
                                               fecha_entrega = VALUES(fecha_entrega)""",
                    (e["uid"], e["curso"], e["titulo"], fecha),
                )
                conexion.commit()
                if e["peso_detectado"] is not None:
                    try:
                        cur.execute(
                            "UPDATE actividades SET peso = %s WHERE uid_moodle = %s AND peso IS NULL",
                            (e["peso_detectado"], e["uid"]),
                        )
                        conexion.commit()
                    except pymysql.MySQLError as error:
                        conexion.rollback()  # la regla del 100 % lo rechazó
                        print(f"Peso rechazado para {e['titulo']}: {error}", flush=True)
                cur.execute("SELECT peso FROM actividades WHERE uid_moodle = %s", (e["uid"],))
                peso = cur.fetchone()["peso"]
                pesos[e["uid"]] = float(peso) if peso is not None else None
    finally:
        conexion.close()
    return pesos, sede


def guardar_en_mongo(estudiante_id, entregas, pesos, sede):
    coleccion = mongo.entregas.entregas
    for e in entregas:
        coleccion.update_one(
            {"_id": f"{estudiante_id}:{e['uid']}"},
            {
                "$set": {
                    "estudiante_id": estudiante_id,
                    "sede": sede["nombre"],
                    "region": sede["region"],
                    "curso": e["curso"],
                    "uid": e["uid"],
                    "titulo": e["titulo"],
                    "peso": pesos.get(e["uid"]),
                    "fecha_entrega": datetime.fromisoformat(e["fecha_entrega"]),
                    "origen": "moodle",
                },
                "$setOnInsert": {"estado": "pendiente"},
            },
            upsert=True,
        )


# --- Pipeline completo de un estudiante ----------------------------------------
def procesar_estudiante(estudiante_id: int, url: str) -> int:
    """Descarga el calendario del estudiante y lo lleva a las tres capas. Devuelve cuántas entregas encontró."""
    marca = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    respuesta = requests.get(url, timeout=30)
    respuesta.raise_for_status()
    if b"BEGIN:VCALENDAR" not in respuesta.content[:200]:
        raise ValueError("La URL no devolvió un calendario de Moodle")

    preparar_datalake()
    carpeta = f"estudiante_{estudiante_id}"
    guardar_en_datalake(f"raw/{carpeta}/calendario_{marca}.ics", respuesta.content, "text/calendar")

    entregas = extraer_entregas(respuesta.content)
    datos = json.dumps(entregas, ensure_ascii=False, indent=2).encode("utf-8")
    guardar_en_datalake(f"processed/{carpeta}/entregas_{marca}.json", datos, "application/json")

    pesos, sede = registrar_en_mysql(estudiante_id, entregas)
    guardar_en_mongo(estudiante_id, entregas, pesos, sede)
    return len(entregas)
