import os
import threading
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv
from util import datetime, print_with_time
import datetime

from util import print_with_time, timestamp
DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': os.getenv('DB_PORT', '5432'),
    'database': os.getenv('DB_NAME', 'railway'),
    'user': os.getenv('DB_USER', 'postgres'),
    'password': os.getenv('DB_PASSWORD', '')
}
def get_db_config() -> dict:
    """Carga .env y retorna la configuración de conexión a Postgres."""
    load_dotenv()
    return {
        'host': os.getenv('DB_HOST', DB_CONFIG.get('host')),
        'port': os.getenv('DB_PORT', DB_CONFIG.get('port')),
        'database': os.getenv('DB_NAME', DB_CONFIG.get('database')),
        'user': os.getenv('DB_USER', DB_CONFIG.get('user')),
        'password': os.getenv('DB_PASSWORD', DB_CONFIG.get('password')),
    }

_FACT_TABLE_INITED = False
_FACT_LOCK = threading.Lock()

def _ensure_facturas_table():
    global _FACT_TABLE_INITED
    if _FACT_TABLE_INITED:
        return
    with _FACT_LOCK:
        if _FACT_TABLE_INITED:
            return
        conn = None
        try:
            conn = psycopg2.connect(**get_db_config())
            cur = conn.cursor()
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS facturas_generadas (
                    id SERIAL PRIMARY KEY,
                    fecha_hora TIMESTAMP NOT NULL,
                    comprobante VARCHAR(100) NOT NULL,
                    cuit VARCHAR(20),
                    empresa VARCHAR(200),
                    provincia_destino VARCHAR(100),
                    alicuota NUMERIC(10,4),
                    numero_factura VARCHAR(100),
                    nro_cae VARCHAR(100),
                    estado VARCHAR(30) NOT NULL DEFAULT 'Generado',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            # Ensure column exists for existing installations
            cur.execute("ALTER TABLE facturas_generadas ADD COLUMN IF NOT EXISTS nro_cae VARCHAR(100)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_facturas_estado ON facturas_generadas(estado)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_facturas_comprobante ON facturas_generadas(comprobante)")
            conn.commit()
            _FACT_TABLE_INITED = True
            print_with_time("Tabla facturas_generadas creada/verificada")
        except Exception as e:
            print_with_time(f"Error creando/verificando tabla facturas_generadas: {e}")
        finally:
            if conn:
                conn.close()

def guardar_factura_generada(
    fecha_hora: datetime,
    comprobante: str,
    cuit: str | None,
    empresa: str | None,
    provincia_destino: str | None,
    alicuota: float | None,
    numero_factura: str | None,
    nro_cae: str | None,
    estado: str = 'Generado'
):
    _ensure_facturas_table()
    conn = None
    try:
        #print_with_time(DB_CONFIG)
        conn = psycopg2.connect(**get_db_config())
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO facturas_generadas
            (fecha_hora, comprobante, cuit, empresa, provincia_destino, alicuota, numero_factura, nro_cae, estado)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                fecha_hora,
                comprobante,
                cuit,
                empresa,
                provincia_destino,
                alicuota,
                numero_factura,
                nro_cae,
                estado,
            )
        )
        conn.commit()
        print_with_time("Factura registrada en PostgreSQL con estado Generado")
    except Exception as e:
        print_with_time(f"Error registrando factura en PostgreSQL: {e}")
    finally:
        if conn:
            conn.close()


def get_facturas_envio_pendiente() -> list[dict]:
    conn = None
    try:
        conn = psycopg2.connect(**get_db_config())
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, fecha_hora, comprobante, cuit, empresa, provincia_destino,
                       alicuota, numero_factura, nro_cae, estado, created_at, docnroint
                FROM facturas_generadas
                WHERE empresa = %s
                  AND estado = %s
                  AND nro_cae IS NOT NULL
                  AND nro_cae <> ''
                """,
                ('Das Dach', 'Generado'),
            )
            return cur.fetchall()
    except Exception as e:
        print_with_time(f"Error obteniendo facturas pendientes de envio: {e}")
        return []
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


def update_factura_estado(factura_id: int | None, comprobante: str | None, estado: str = 'Enviado') -> None:
    _ensure_facturas_table()
    conn = None
    try:
        conn = psycopg2.connect(**get_db_config())
        with conn.cursor() as cur:
            if factura_id is not None:
                cur.execute(
                    """
                    UPDATE facturas_generadas
                    SET estado = %s
                    WHERE id = %s
                    """,
                    (estado, factura_id),
                )
            elif comprobante:
                cur.execute(
                    """
                    UPDATE facturas_generadas
                    SET estado = %s
                    WHERE comprobante = %s
                    """,
                    (estado, comprobante),
                )
            else:
                return
        conn.commit()
        print_with_time(f"Factura actualizada a estado {estado}")
    except Exception as e:
        print_with_time(f"Error actualizando estado de factura: {e}")
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass
