"""Reglas de negocio: limpiar títulos, detectar el peso y calcular la prioridad."""

import re
from datetime import datetime, timezone

# "Vencimiento de 60% Entrega..." -> 60
PATRON_PESO = re.compile(r"(\d{1,3}(?:[.,]\d+)?)\s*%")
# Ruido que Moodle agrega al título
PREFIJOS = re.compile(r"^(vencimiento de|se cierra|se abre|abre)\s+", re.IGNORECASE)
SUFIJOS = re.compile(r"\s+(cierra|vence|abre)$", re.IGNORECASE)
# Eventos que no dan nota
SIN_NOTA = re.compile(r"attendance|asistencia|acuerdo pedag", re.IGNORECASE)

PESO_POR_DEFECTO = 10  # si no sabemos cuánto vale, asumimos 10 %


def limpiar_titulo(titulo: str) -> str:
    titulo = PREFIJOS.sub("", titulo.strip())
    return SUFIJOS.sub("", titulo)


def extraer_peso(titulo: str):
    """Devuelve el % si viene en el título, 0 si no da nota, o None si no se sabe."""
    if SIN_NOTA.search(titulo):
        return 0.0
    coincidencia = PATRON_PESO.search(titulo)
    if coincidencia:
        return float(coincidencia.group(1).replace(",", "."))
    return None


def dias_restantes(fecha: datetime, ahora: datetime = None) -> float:
    ahora = ahora or datetime.now(timezone.utc)
    return (fecha - ahora).total_seconds() / 86400


def calcular_prioridad(peso, fecha: datetime, ahora: datetime = None) -> float:
    """prioridad = peso / días que faltan.
    Menos de 6 horas cuenta como 6 horas, para no dividir entre casi cero."""
    dias = max(dias_restantes(fecha, ahora), 0.25)
    peso = PESO_POR_DEFECTO if peso is None else float(peso)
    return round(peso / dias, 2)


def nivel_alerta(peso, fecha: datetime, ahora: datetime = None) -> str:
    dias = dias_restantes(fecha, ahora)
    if peso is not None and float(peso) == 0:
        return "INFO"  # no da nota
    peso = PESO_POR_DEFECTO if peso is None else float(peso)
    if peso >= 20 and dias <= 3:
        return "ALTA"
    if peso >= 10 and dias <= 7:
        return "MEDIA"
    return "BAJA"
