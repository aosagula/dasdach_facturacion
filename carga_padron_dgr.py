#!/usr/bin/env python3
# pip install psycopg2-binary python-dotenv
import os, sys, psycopg2
from dotenv import load_dotenv

SQL_CREATE = """
CREATE SCHEMA IF NOT EXISTS arba;
SET search_path TO arba, public;

CREATE TABLE IF NOT EXISTS padron_rgs_raw (
  col1  text, col2  text, col3  text, col4  text, col5  text,
  col6  text, col7  text, col8  text, col9  text, col10 text, col11 text
);

CREATE TABLE IF NOT EXISTS padron_rgs (
  regimen          char(1)      NOT NULL CHECK (regimen IN ('P','R')),
  fecha_emision    date         NOT NULL,
  vigencia_desde   date         NOT NULL,
  vigencia_hasta   date         NOT NULL,
  cuit             char(11)     NOT NULL CHECK (cuit ~ '^[0-9]{11}$'),
  flag1            char(1)      NULL  CHECK (flag1 IN ('C','D')),
  flag2            char(1)      NULL  CHECK (flag2 IN ('S','N')),
  flag3            char(1)      NULL  CHECK (flag3 IN ('S','N')),
  alicuota         numeric(6,2) NOT NULL DEFAULT 0,
  codigo           integer      NULL,
  CONSTRAINT padron_rgs_pk PRIMARY KEY
    (regimen, cuit, vigencia_desde, vigencia_hasta, fecha_emision)
);

CREATE INDEX IF NOT EXISTS idx_padron_cuit ON padron_rgs (cuit);
CREATE INDEX IF NOT EXISTS idx_padron_vig ON padron_rgs (vigencia_desde, vigencia_hasta);
CREATE INDEX IF NOT EXISTS idx_padron_alicuota_nonzero ON padron_rgs (alicuota) WHERE alicuota > 0;
"""

SQL_MERGE = """
INSERT INTO arba.padron_rgs (
  regimen, fecha_emision, vigencia_desde, vigencia_hasta, cuit,
  flag1, flag2, flag3, alicuota, codigo
)
SELECT
  col1,
  to_date(col2,  'DDMMYYYY'),
  to_date(col3,  'DDMMYYYY'),
  to_date(col4,  'DDMMYYYY'),
  lpad(regexp_replace(col5, '\D', '', 'g'), 11, '0'),
  NULLIF(col6,''),
  NULLIF(col7,''),
  NULLIF(col8,''),
  NULLIF(REPLACE(col9, ',', '.'), '')::numeric(6,2),
  NULLIF(col10,'')::integer
FROM arba.padron_rgs_raw
WHERE col1 IN ('P','R')
  AND col5 ~ '^[0-9]{11}$'
  AND col2 ~ '^\d{8}$' AND col3 ~ '^\d{8}$' AND col4 ~ '^\d{8}$'
ON CONFLICT (regimen, cuit, vigencia_desde, vigencia_hasta, fecha_emision)
DO UPDATE SET
  flag1    = EXCLUDED.flag1,
  flag2    = EXCLUDED.flag2,
  flag3    = EXCLUDED.flag3,
  alicuota = EXCLUDED.alicuota,
  codigo   = EXCLUDED.codigo;

TRUNCATE TABLE arba.padron_rgs_raw;
ANALYZE arba.padron_rgs;
"""

def main():
    load_dotenv()
    
    # Construir DSN desde variables de entorno
    host = os.getenv('DB_HOST', 'localhost')
    port = os.getenv('DB_PORT', '5432')
    dbname = os.getenv('DB_NAME')
    user = os.getenv('DB_USER')
    password = os.getenv('DB_PASSWORD')
    
    if not all([dbname, user, password]):
        print("Error: Faltan variables de entorno requeridas (DB_NAME, DB_USER, DB_PASSWORD)")
        sys.exit(1)
    
    dsn = f"host={host} port={port} dbname={dbname} user={user} password={password}"
    
    # Obtener ruta del archivo
    if len(sys.argv) >= 2:
        ruta = sys.argv[1]
    else:
        ruta = os.getenv('PADRON_FILE', 'padron.txt')
        print(f"Usando archivo por defecto: {ruta}")
        
    if not ruta:
        print("Uso: carga_padron_arba.py <ruta_txt>")
        print("Ej:  carga_padron_arba.py PadronRGSPerMMAAAA.txt")
        print("O definir PADRON_FILE en .env")
        sys.exit(1)
    if not os.path.exists(ruta):
        print(f"No existe: {ruta}")
        sys.exit(1)

    conn = psycopg2.connect(dsn)
    conn.autocommit = False
    cur = conn.cursor()

    # Asegurar encoding compatible (muchos TXT vienen en LATIN1)
    cur.execute("SET client_encoding TO 'UTF8';")

    # Crear objetos
    for stmt in SQL_CREATE.split(";\n"):
        if stmt.strip():
            cur.execute(stmt + ";")

    # Carga masiva al staging con COPY
    print("Cargando a arba.padron_rgs_raw...")
    with open(ruta, "r", encoding="utf-8", newline="") as f:
        cur.copy_expert(
            "COPY arba.padron_rgs_raw FROM STDIN WITH (FORMAT csv, DELIMITER ';', HEADER false, NULL '')",
            f
        )

    # Merge a final
    print("Normalizando y actualizando tabla final...")
    cur.execute(SQL_MERGE)

    conn.commit()
    cur.close()
    conn.close()
    print("OK.")

if __name__ == "__main__":
    main()
