"""Conexiones a las tres capas de datos: MinIO, MySQL y MongoDB."""

import os
import time

import pymysql
from dotenv import load_dotenv
from minio import Minio
from pymongo import MongoClient

load_dotenv()  # con venv lee el .env; con Docker no hace nada

# MongoDB: replica set de 3 nodos, uno por región
MONGO_URI = os.getenv(
    "MONGO_URI",
    "mongodb://mongo-bogota:27017,mongo-medellin:27017,mongo-cali:27017/?replicaSet=rs0",
)


def mongo_cliente(**opciones):
    # tz_aware=True: las fechas vuelven con zona horaria (UTC)
    return MongoClient(MONGO_URI, tz_aware=True, serverSelectionTimeoutMS=5000, **opciones)


def mysql_conexion():
    return pymysql.connect(
        host=os.getenv("MYSQL_HOST", "mysql"),
        user=os.getenv("MYSQL_USER", "app"),
        password=os.environ["MYSQL_PASSWORD"],
        database=os.getenv("MYSQL_DATABASE", "entregas"),
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,  # nosotros decidimos cuándo confirmar (transacciones)
    )


def minio_cliente():
    return Minio(
        os.getenv("MINIO_ENDPOINT", "minio:9000"),
        access_key=os.environ["MINIO_ROOT_USER"],
        secret_key=os.environ["MINIO_ROOT_PASSWORD"],
        secure=False,
    )


def esperar(nombre, prueba):
    """Reintenta `prueba` hasta que el servicio responda (los contenedores tardan en arrancar)."""
    while True:
        try:
            prueba()
            print(f"{nombre} listo", flush=True)
            return
        except Exception as error:
            print(f"Esperando a {nombre}... ({str(error)[:120]})", flush=True)
            time.sleep(3)


def esperar_todo():
    esperar("MySQL", lambda: mysql_conexion().close())
    esperar("MongoDB", lambda: mongo_cliente().admin.command("ping"))
    asegurar_esquema()


def asegurar_esquema():
    """Migración: agrega la columna de la URL del calendario si la base es de una versión anterior."""
    conexion = mysql_conexion()
    try:
        with conexion.cursor() as cur:
            cur.execute(
                """SELECT COUNT(*) AS n FROM information_schema.COLUMNS
                   WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'estudiantes'
                     AND COLUMN_NAME = 'calendario_url'"""
            )
            if cur.fetchone()["n"] == 0:
                try:
                    cur.execute("ALTER TABLE estudiantes ADD COLUMN calendario_url VARCHAR(600) NULL")
                    print("Migración: columna calendario_url agregada", flush=True)
                except pymysql.MySQLError as error:
                    if error.args[0] != 1060:  # 1060 = otro proceso ya la creó
                        raise
        conexion.commit()
    finally:
        conexion.close()
