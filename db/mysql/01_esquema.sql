SET NAMES utf8mb4;
-- Base relacional: datos estables que se relacionan entre sí.
-- MySQL ejecuta este archivo solo la primera vez que se crea el volumen.

CREATE TABLE sedes (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    nombre      VARCHAR(80)  NOT NULL UNIQUE,
    region      VARCHAR(60)  NOT NULL,
    nodo_mongo  VARCHAR(40)  NOT NULL   -- nodo de Mongo más cercano a la sede
);

CREATE TABLE estudiantes (
    id                INT AUTO_INCREMENT PRIMARY KEY,
    nombre            VARCHAR(120) NOT NULL,
    correo            VARCHAR(120) NOT NULL UNIQUE,
    sede_id           INT NOT NULL,
    telegram_chat_id  VARCHAR(40) NULL,
    calendario_url    VARCHAR(600) NULL,  -- URL personal de exportación de Moodle
    FOREIGN KEY (sede_id) REFERENCES sedes(id)
);

CREATE TABLE cursos (
    codigo   VARCHAR(20)  PRIMARY KEY,   -- el código que trae Moodle, ej. 60-83355
    nombre   VARCHAR(120) NOT NULL,
    sede_id  INT NOT NULL,
    FOREIGN KEY (sede_id) REFERENCES sedes(id)
);

CREATE TABLE matriculas (
    estudiante_id  INT NOT NULL,
    curso_codigo   VARCHAR(20) NOT NULL,
    PRIMARY KEY (estudiante_id, curso_codigo),
    FOREIGN KEY (estudiante_id) REFERENCES estudiantes(id) ON DELETE CASCADE,
    FOREIGN KEY (curso_codigo)  REFERENCES cursos(codigo)  ON DELETE CASCADE
);

CREATE TABLE actividades (
    uid_moodle     VARCHAR(100) PRIMARY KEY,  -- identificador único que da Moodle
    curso_codigo   VARCHAR(20)  NOT NULL,
    titulo         VARCHAR(200) NOT NULL,
    peso           DECIMAL(5,2) NULL,         -- % de la nota; NULL = aún no se sabe
    fecha_entrega  DATETIME     NOT NULL,     -- en UTC
    CONSTRAINT peso_valido CHECK (peso IS NULL OR (peso >= 0 AND peso <= 100)),
    FOREIGN KEY (curso_codigo) REFERENCES cursos(codigo) ON DELETE CASCADE
);

-- Regla de integridad: la suma de pesos de un curso no puede pasar de 100 %.
-- Un CHECK no puede mirar otras filas, por eso se usa un trigger.
DELIMITER $$

CREATE TRIGGER actividades_peso_insert BEFORE INSERT ON actividades
FOR EACH ROW
BEGIN
    IF NEW.peso IS NOT NULL AND
       (SELECT COALESCE(SUM(peso), 0) FROM actividades
         WHERE curso_codigo = NEW.curso_codigo) + NEW.peso > 100 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'La suma de pesos del curso supera el 100%';
    END IF;
END$$

CREATE TRIGGER actividades_peso_update BEFORE UPDATE ON actividades
FOR EACH ROW
BEGIN
    IF NEW.peso IS NOT NULL AND
       (SELECT COALESCE(SUM(peso), 0) FROM actividades
         WHERE curso_codigo = NEW.curso_codigo
           AND uid_moodle <> OLD.uid_moodle) + NEW.peso > 100 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'La suma de pesos del curso supera el 100%';
    END IF;
END$$

DELIMITER ;

-- Sedes (datos sintéticos que representan varias regiones)
INSERT INTO sedes (nombre, region, nodo_mongo) VALUES
    ('Bogotá Calle 80',   'Bogotá D.C.',  'mongo-bogota'),
    ('Bogotá Sur',        'Bogotá D.C.',  'mongo-bogota'),
    ('Soacha',            'Cundinamarca', 'mongo-bogota'),
    ('Bello',             'Antioquia',    'mongo-medellin'),
    ('Pereira',           'Eje Cafetero', 'mongo-medellin'),
    ('Cali',              'Valle',        'mongo-cali');

-- Estudiante 1: el dueño del calendario real de Moodle
INSERT INTO estudiantes (nombre, correo, sede_id)
VALUES ('Estudiante demo (calendario real)', 'demo@uniminuto.edu.co', 1);
