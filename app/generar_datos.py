"""Genera datos sintéticos de varias sedes para probar el sistema a escala nacional.

Uso:  docker compose exec api python generar_datos.py [numero_de_estudiantes]

Se puede correr varias veces: primero borra los datos sintéticos anteriores.
"""

import random
import sys
from datetime import datetime, timedelta, timezone

from conexiones import esperar_todo, mongo_cliente, mysql_conexion

random.seed(42)  # misma semilla = mismos datos, para que las pruebas se puedan repetir

N_ESTUDIANTES = int(sys.argv[1]) if len(sys.argv) > 1 else 3000
CURSOS_POR_SEDE = 8
CURSOS_POR_ESTUDIANTE = 5
DOMINIO = "sintetico.uniminuto.test"

# Peso de cada sede en la población: las sedes no son del mismo tamaño
PROPORCION_SEDES = {1: 0.35, 2: 0.15, 3: 0.12, 4: 0.15, 5: 0.08, 6: 0.15}

# Plantilla de actividades de un curso: (título, peso). Suman 100 %.
PLANTILLA = [
    ("Foro de discusión", 5),
    ("Cuestionario U1", 10),
    ("Taller práctico", 15),
    ("Parcial", 20),
    ("Asistencia", 0),
    ("Proyecto final", 50),
]

NOMBRES = ["Ana", "Luis", "Camila", "Andrés", "Valentina", "Santiago", "Laura", "Juan",
           "Daniela", "Felipe", "Sofía", "Mateo", "Paula", "Sebastián", "Natalia", "David"]
APELLIDOS = ["Gómez", "Rodríguez", "Martínez", "López", "García", "Pérez", "Sánchez",
             "Ramírez", "Torres", "Díaz", "Moreno", "Rojas", "Vargas", "Castro"]


def limpiar_anteriores(cur, mongo):
    cur.execute("DELETE FROM cursos WHERE codigo LIKE 'SIM-%%'")  # borra en cascada actividades y matrículas
    cur.execute("DELETE FROM estudiantes WHERE correo LIKE %s", (f"%@{DOMINIO}",))
    mongo.entregas.entregas.delete_many({"origen": "sintetico"})


def main():
    esperar_todo()
    ahora = datetime.now(timezone.utc)
    mongo = mongo_cliente()
    conexion = mysql_conexion()
    cur = conexion.cursor()

    limpiar_anteriores(cur, mongo)
    conexion.commit()

    cur.execute("SELECT id, nombre, region FROM sedes")
    sedes = {s["id"]: s for s in cur.fetchall()}

    # 1. Cursos por sede
    cursos_por_sede = {}
    for sede_id in sedes:
        codigos = [f"SIM-{sede_id}-{n:02d}" for n in range(1, CURSOS_POR_SEDE + 1)]
        cursos_por_sede[sede_id] = codigos
        cur.executemany(
            "INSERT INTO cursos (codigo, nombre, sede_id) VALUES (%s, %s, %s)",
            [(c, f"Curso {c}", sede_id) for c in codigos],
        )
    conexion.commit()

    # 2. Actividades: cada curso en UNA transacción (o se guardan todas o ninguna)
    actividades = {}
    for codigos in cursos_por_sede.values():
        for codigo in codigos:
            lista = []
            for i, (titulo, peso) in enumerate(PLANTILLA):
                fecha = ahora + timedelta(hours=random.uniform(6, 30 * 24))
                uid = f"{codigo}-A{i}"
                cur.execute(
                    """INSERT INTO actividades (uid_moodle, curso_codigo, titulo, peso, fecha_entrega)
                       VALUES (%s, %s, %s, %s, %s)""",
                    (uid, codigo, titulo, peso, fecha.replace(tzinfo=None)),
                )
                lista.append((uid, titulo, peso, fecha))
            conexion.commit()
            actividades[codigo] = lista

    # 3. Estudiantes repartidos de forma desigual entre sedes
    ids_sede = list(PROPORCION_SEDES)
    sedes_elegidas = random.choices(ids_sede, weights=PROPORCION_SEDES.values(), k=N_ESTUDIANTES)
    filas = [
        (f"{random.choice(NOMBRES)} {random.choice(APELLIDOS)}", f"est{n}@{DOMINIO}", sede_id)
        for n, sede_id in enumerate(sedes_elegidas)
    ]
    cur.executemany("INSERT INTO estudiantes (nombre, correo, sede_id) VALUES (%s, %s, %s)", filas)
    conexion.commit()
    cur.execute("SELECT id, sede_id FROM estudiantes WHERE correo LIKE %s", (f"%@{DOMINIO}",))
    estudiantes = cur.fetchall()

    # 4. Matrículas (MySQL) y entregas (MongoDB)
    matriculas, documentos = [], []
    for est in estudiantes:
        sede = sedes[est["sede_id"]]
        for codigo in random.sample(cursos_por_sede[est["sede_id"]], CURSOS_POR_ESTUDIANTE):
            matriculas.append((est["id"], codigo))
            for uid, titulo, peso, fecha in actividades[codigo]:
                documentos.append({
                    "_id": f"{est['id']}:{uid}",
                    "estudiante_id": est["id"],
                    "sede": sede["nombre"],
                    "region": sede["region"],
                    "curso": codigo,
                    "uid": uid,
                    "titulo": titulo,
                    "peso": float(peso),
                    "fecha_entrega": fecha,
                    "estado": "pendiente",
                    "origen": "sintetico",
                })
    cur.executemany("INSERT INTO matriculas (estudiante_id, curso_codigo) VALUES (%s, %s)", matriculas)
    conexion.commit()
    conexion.close()

    coleccion = mongo.entregas.entregas
    for i in range(0, len(documentos), 5000):
        coleccion.insert_many(documentos[i:i + 5000], ordered=False)
    coleccion.create_index([("estudiante_id", 1), ("fecha_entrega", 1)])
    coleccion.create_index([("uid", 1)])

    print(f"Sedes: {len(sedes)} | Cursos: {sum(len(c) for c in cursos_por_sede.values())} | "
          f"Estudiantes: {len(estudiantes)} | Matrículas: {len(matriculas)} | "
          f"Entregas en MongoDB: {len(documentos)}")


if __name__ == "__main__":
    main()
