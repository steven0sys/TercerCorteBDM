"""Prueba 1 (relacional): una operación que debe preservar la integridad.

Escenario: un curso ya tiene actividades que suman 100 %. En UNA transacción
se intenta agregar una actividad nueva (10 %) y además modificar otra.
El trigger rechaza la suma > 100 % y la transacción completa se deshace:
no queda guardado ningún cambio a medias.

Uso: docker compose exec api python pruebas/prueba_integridad.py
"""

import pymysql

from conexiones import mysql_conexion

CURSO = "SIM-1-01"

conexion = mysql_conexion()
cur = conexion.cursor()


def estado():
    cur.execute("SELECT COUNT(*) AS n, SUM(peso) AS total FROM actividades WHERE curso_codigo = %s", (CURSO,))
    fila = cur.fetchone()
    cur.execute("SELECT titulo FROM actividades WHERE uid_moodle = %s", (f"{CURSO}-A0",))
    return fila["n"], float(fila["total"] or 0), cur.fetchone()["titulo"]


antes = estado()
print(f"ANTES   -> actividades: {antes[0]}, suma de pesos: {antes[1]} %, título A0: '{antes[2]}'")

try:
    # Cambio 1 (válido por sí solo): renombrar una actividad
    cur.execute("UPDATE actividades SET titulo = 'Foro MODIFICADO' WHERE uid_moodle = %s", (f"{CURSO}-A0",))
    # Cambio 2 (inválido): la suma pasaría a 110 %
    cur.execute(
        """INSERT INTO actividades (uid_moodle, curso_codigo, titulo, peso, fecha_entrega)
           VALUES (%s, %s, 'Actividad extra', 10, NOW())""",
        (f"{CURSO}-EXTRA", CURSO),
    )
    conexion.commit()
    print("Transacción confirmada (NO debería pasar)")
except pymysql.MySQLError as error:
    conexion.rollback()
    print(f"RECHAZO -> {error.args[1]}  => ROLLBACK de toda la transacción")

despues = estado()
print(f"DESPUÉS -> actividades: {despues[0]}, suma de pesos: {despues[1]} %, título A0: '{despues[2]}'")
print("RESULTADO:", "OK, integridad preservada" if antes == despues else "FALLO, quedaron cambios a medias")
conexion.close()
