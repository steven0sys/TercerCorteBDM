# Entregas UNIMINUTO

Prototipo que avisa a los estudiantes de UNIMINUTO sus entregas del aula virtual
**según cuánto valen en la nota**, no solo por fecha. Integra un datalake (MinIO),
una base relacional (MySQL) y una base distribuida (MongoDB replicado en 3 nodos regionales).

Diagramas de arquitectura y entidad-relación: [docs/diagramas.md](docs/diagramas.md)

## Requisitos

- Docker y Docker Compose (en Windows: Docker Desktop con WSL).
- Nada más: las librerías de Python se instalan solas dentro del contenedor.

## Cómo ejecutarlo

```bash
cp .env.example .env        # y llena tu URL del calendario y las claves (mínimo 8 caracteres)
docker compose up --build -d
docker compose ps           # todos deben estar "Up" (mongo-init termina con "Exited (0)")
```

Generar datos sintéticos de 6 sedes y 3.000 estudiantes:

```bash
docker compose exec api python generar_datos.py
```

Abrir la app: http://localhost:8000

- **Registrarme:** nombre, correo, sede y la URL del calendario del aula virtual. Las entregas se importan al instante.
- **Entrar:** con el correo. Los estudiantes sintéticos usan `est<N>@sintetico.uniminuto.test` (por ejemplo `est10@sintetico.uniminuto.test`).
- El ingestor actualiza a todos los estudiantes registrados cada `INTERVALO_MINUTOS`.

Documentación de la API: http://localhost:8000/docs

## Pruebas

```bash
docker compose exec api python pruebas/prueba_integridad.py    # relacional: regla del 100 % + rollback
docker compose exec api python pruebas/prueba_replicacion.py   # distribuida: retraso de réplica
docker compose exec api python pruebas/prueba_criterio.py      # criterio de éxito vs. Moodle
```

Prueba de tolerancia a fallos (apagar el nodo primario y ver que la app sigue):

```bash
docker compose stop mongo-bogota
curl http://localhost:8000/salud            # otro nodo pasa a ser primario
docker compose start mongo-bogota
```

Ver el datalake:

```bash
docker compose run --rm mc ls --recursive local/datalake
```

## Estructura

```
app/ingesta.py         pipeline de un estudiante: Moodle -> datalake -> MySQL + MongoDB
app/ingestor.py        proceso programado: corre el pipeline para todos los registrados
app/pagina.html        interfaz web (registro, entrada y lista de entregas)
app/api.py             API FastAPI + página web
app/procesamiento.py   limpieza de títulos, detección de peso, prioridad
app/generar_datos.py   datos sintéticos multisede
db/mysql/              esquema, trigger de integridad y datos base
pruebas/               scripts de prueba
docs/                  diagramas
```

## Problemas comunes

- `pull access denied for minio/minio`: MinIO retiró sus imágenes; usamos `cgr.dev/chainguard/minio`.
- MinIO se apaga solo: la clave de MinIO debe tener mínimo 8 caracteres.
- Cambié el esquema SQL y no se aplica: MySQL solo lo lee al crear el volumen.
  Borra todo con `docker compose down -v` (borra también los datos) y vuelve a levantar.
