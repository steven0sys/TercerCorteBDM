# Diagramas

GitHub dibuja estos diagramas automáticamente.

## Arquitectura

```mermaid
flowchart LR
    M[Aula virtual Moodle<br/>calendario .ics] -->|cada 3 h| I[Ingestor<br/>Python]
    I -->|raw/ y processed/| D[(Datalake<br/>MinIO)]
    I -->|cursos, actividades, pesos| R[(MySQL<br/>relacional)]
    I -->|entregas por estudiante| RS
    subgraph RS[MongoDB replica set rs0]
        B[(mongo-bogota<br/>primario)] -.replica.-> MD[(mongo-medellin)]
        B -.replica.-> C[(mongo-cali)]
    end
    A[API FastAPI] --> RS
    A --> R
    W[Página web<br/>estudiante] --> A
```

## Modelo entidad-relación (MySQL)

```mermaid
erDiagram
    SEDES ||--o{ ESTUDIANTES : "tiene"
    SEDES ||--o{ CURSOS : "ofrece"
    ESTUDIANTES ||--o{ MATRICULAS : "se inscribe"
    CURSOS ||--o{ MATRICULAS : "recibe"
    CURSOS ||--o{ ACTIVIDADES : "incluye"

    SEDES {
        int id PK
        varchar nombre UK
        varchar region
        varchar nodo_mongo
    }
    ESTUDIANTES {
        int id PK
        varchar nombre
        varchar correo UK
        int sede_id FK
        varchar telegram_chat_id
    }
    CURSOS {
        varchar codigo PK
        varchar nombre
        int sede_id FK
    }
    MATRICULAS {
        int estudiante_id PK,FK
        varchar curso_codigo PK,FK
    }
    ACTIVIDADES {
        varchar uid_moodle PK
        varchar curso_codigo FK
        varchar titulo
        decimal peso "0 a 100, suma por curso <= 100"
        datetime fecha_entrega
    }
```

## Documento en MongoDB (colección `entregas`)

```json
{
  "_id": "1:545858@presencial.aulasuniminuto.edu.co",
  "estudiante_id": 1,
  "sede": "Bogotá Calle 80",
  "region": "Bogotá D.C.",
  "curso": "60-83355",
  "uid": "545858@presencial.aulasuniminuto.edu.co",
  "titulo": "60% Entrega proyecta final",
  "peso": 60,
  "fecha_entrega": "2026-11-19T04:00:00Z",
  "estado": "pendiente",
  "origen": "moodle"
}
```
