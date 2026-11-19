"""API (FastAPI): lo que usa la interfaz web.

Rutas:
  GET  /                              página web para el estudiante
  POST /estudiantes                   registro (nombre, correo, sede, URL del calendario)
  GET  /estudiantes/buscar?correo=    entrar con el correo
  PUT  /estudiantes/{id}/calendario   cambiar la URL del calendario
  POST /estudiantes/{id}/sincronizar  traer el calendario ya mismo
  GET  /estudiantes/{id}/entregas     entregas ordenadas por prioridad
  PUT  /actividades/{uid}/peso        el estudiante indica cuánto vale una actividad
  GET  /sedes/resumen                 vista nacional: entregas críticas por sede
  GET  /docs                          documentación automática (la genera FastAPI)
"""

from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pymysql
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from pymongo import ReadPreference

from conexiones import esperar_todo, mongo_cliente, mysql_conexion
from ingesta import procesar_estudiante
from procesamiento import calcular_prioridad, dias_restantes, nivel_alerta


@asynccontextmanager
async def arranque(app):
    esperar_todo()  # espera a MySQL y MongoDB y aplica migraciones
    yield


app = FastAPI(title="Entregas UNIMINUTO", description="Avisos de entregas según su peso en la nota",
              lifespan=arranque)
mongo = mongo_cliente()
db = mongo.entregas


@app.get("/salud")
def salud():
    estado = mongo.admin.command("hello")
    return {"api": "ok", "mongo_primario": estado.get("primary"), "nodos": estado.get("hosts")}


@app.get("/estudiantes/{estudiante_id}/entregas")
def entregas_de_estudiante(estudiante_id: int, lectura: str = "primario"):
    """lectura=primario (siempre lo último) o cercano (más rápido, puede venir desactualizado)."""
    preferencia = ReadPreference.NEAREST if lectura == "cercano" else ReadPreference.PRIMARY
    coleccion = db.get_collection("entregas", read_preference=preferencia)
    ahora = datetime.now(timezone.utc)
    documentos = coleccion.find(
        {"estudiante_id": estudiante_id, "estado": "pendiente", "fecha_entrega": {"$gte": ahora}},
        {"_id": 0},
    )
    resultado = []
    for d in documentos:
        resultado.append({
            "titulo": d["titulo"],
            "curso": d["curso"],
            "uid": d["uid"],
            "peso": d["peso"],
            "fecha_entrega": d["fecha_entrega"].isoformat(),
            "dias_restantes": round(dias_restantes(d["fecha_entrega"], ahora), 1),
            "prioridad": calcular_prioridad(d["peso"], d["fecha_entrega"], ahora),
            "alerta": nivel_alerta(d["peso"], d["fecha_entrega"], ahora),
        })
    resultado.sort(key=lambda e: e["prioridad"], reverse=True)
    return resultado


class Peso(BaseModel):
    peso: float = Field(ge=0, le=100)


@app.put("/actividades/{uid}/peso")
def asignar_peso(uid: str, datos: Peso):
    """Guarda el peso en MySQL (respetando la regla del 100 %) y lo propaga a MongoDB."""
    conexion = mysql_conexion()
    try:
        with conexion.cursor() as cur:
            filas = cur.execute("UPDATE actividades SET peso = %s WHERE uid_moodle = %s", (datos.peso, uid))
            if filas == 0:
                cur.execute("SELECT 1 FROM actividades WHERE uid_moodle = %s", (uid,))
                if cur.fetchone() is None:
                    raise HTTPException(404, "Actividad no encontrada")
        conexion.commit()
    except pymysql.MySQLError as error:
        conexion.rollback()
        raise HTTPException(409, f"Rechazado por la base de datos: {error.args[1]}")
    finally:
        conexion.close()
    actualizadas = db.entregas.update_many({"uid": uid}, {"$set": {"peso": datos.peso}})
    return {"uid": uid, "peso": datos.peso, "entregas_actualizadas": actualizadas.modified_count}


@app.get("/sedes/resumen")
def resumen_por_sede(dias: int = 7):
    """Cuántas entregas críticas (≥ 20 %) vencen en los próximos N días en cada sede."""
    ahora = datetime.now(timezone.utc)
    tuberia = [
        {"$match": {"estado": "pendiente", "peso": {"$gte": 20},
                    "fecha_entrega": {"$gte": ahora, "$lte": ahora + timedelta(days=dias)}}},
        {"$group": {"_id": {"sede": "$sede", "region": "$region"}, "entregas_criticas": {"$sum": 1},
                    "estudiantes": {"$addToSet": "$estudiante_id"}}},
        {"$project": {"_id": 0, "sede": "$_id.sede", "region": "$_id.region", "entregas_criticas": 1,
                      "estudiantes_afectados": {"$size": "$estudiantes"}}},
        {"$sort": {"entregas_criticas": -1}},
    ]
    return list(db.entregas.aggregate(tuberia))



# ---------------- Registro y cuenta del estudiante ----------------
def validar_url(url: str):
    if not url.startswith("https://") or "export_execute.php" not in url:
        raise HTTPException(400, "Esa no parece la URL del calendario. En el aula virtual ve a "
                                 "Calendario > Importar o exportar > Exportar calendario > "
                                 "'Obtener URL del calendario' y copia el enlace completo.")


def sincronizar(estudiante_id: int, url: str) -> int:
    try:
        return procesar_estudiante(estudiante_id, url)
    except Exception as error:
        raise HTTPException(400, f"No se pudo leer el calendario: {error}")


@app.get("/sedes")
def listar_sedes():
    conexion = mysql_conexion()
    with conexion.cursor() as cur:
        cur.execute("SELECT id, nombre, region FROM sedes ORDER BY nombre")
        sedes = cur.fetchall()
    conexion.close()
    return sedes


class Registro(BaseModel):
    nombre: str = Field(min_length=2, max_length=120)
    correo: str = Field(min_length=5, max_length=120)
    sede_id: int
    calendario_url: str


@app.post("/estudiantes")
def registrar(datos: Registro):
    """Crea al estudiante e importa su calendario de inmediato."""
    validar_url(datos.calendario_url)
    conexion = mysql_conexion()
    try:
        with conexion.cursor() as cur:
            cur.execute(
                "INSERT INTO estudiantes (nombre, correo, sede_id, calendario_url) VALUES (%s, %s, %s, %s)",
                (datos.nombre, datos.correo.strip().lower(), datos.sede_id, datos.calendario_url),
            )
            nuevo_id = cur.lastrowid
        conexion.commit()
    except pymysql.err.IntegrityError as error:
        conexion.rollback()
        if error.args[0] == 1062:
            raise HTTPException(409, "Ese correo ya está registrado. Usa 'Entrar'.")
        raise HTTPException(400, "Sede no válida")
    finally:
        conexion.close()
    try:
        entregas = sincronizar(nuevo_id, datos.calendario_url)
    except HTTPException:
        # si el calendario no se pudo leer, deshacemos el registro
        conexion = mysql_conexion()
        with conexion.cursor() as cur:
            cur.execute("DELETE FROM estudiantes WHERE id = %s", (nuevo_id,))
        conexion.commit()
        conexion.close()
        raise
    return {"id": nuevo_id, "nombre": datos.nombre, "entregas_importadas": entregas}


@app.get("/estudiantes/buscar")
def buscar_por_correo(correo: str):
    conexion = mysql_conexion()
    with conexion.cursor() as cur:
        cur.execute("SELECT id, nombre FROM estudiantes WHERE correo = %s", (correo.strip().lower(),))
        estudiante = cur.fetchone()
    conexion.close()
    if estudiante is None:
        raise HTTPException(404, "No hay ningún estudiante con ese correo. Regístrate primero.")
    return estudiante


class Url(BaseModel):
    calendario_url: str


@app.put("/estudiantes/{estudiante_id}/calendario")
def cambiar_url(estudiante_id: int, datos: Url):
    validar_url(datos.calendario_url)
    entregas = sincronizar(estudiante_id, datos.calendario_url)  # primero comprobamos que funcione
    conexion = mysql_conexion()
    with conexion.cursor() as cur:
        cur.execute("UPDATE estudiantes SET calendario_url = %s WHERE id = %s",
                    (datos.calendario_url, estudiante_id))
    conexion.commit()
    conexion.close()
    return {"entregas_importadas": entregas}


@app.post("/estudiantes/{estudiante_id}/sincronizar")
def sincronizar_ahora(estudiante_id: int):
    conexion = mysql_conexion()
    with conexion.cursor() as cur:
        cur.execute("SELECT calendario_url FROM estudiantes WHERE id = %s", (estudiante_id,))
        fila = cur.fetchone()
    conexion.close()
    if not fila or not fila["calendario_url"]:
        raise HTTPException(400, "Este estudiante no tiene URL de calendario")
    return {"entregas_importadas": sincronizar(estudiante_id, fila["calendario_url"])}


PAGINA = (Path(__file__).parent / "pagina.html").read_text(encoding="utf-8")


@app.get("/", response_class=HTMLResponse)
def pagina():
    return PAGINA
