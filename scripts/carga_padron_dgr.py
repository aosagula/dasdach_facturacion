#!/usr/bin/env python3
# pip install psycopg2-binary python-dotenv requests
import os, sys, psycopg2, time, requests
from datetime import datetime
from dotenv import load_dotenv

SQL_CREATE = """
DROP TABLE IF EXISTS padron_rgs_raw;

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

CREATE TABLE IF NOT EXISTS padron_log_ejecucion (
  id               serial       PRIMARY KEY,
  fecha_ejecucion  timestamp    NOT NULL DEFAULT NOW(),
  fecha_inicio     timestamp    NULL,
  fecha_fin        timestamp    NULL,
  tiempo_transcurrido interval  NULL,
  nombre_archivo   text         NOT NULL,
  total_registros  integer      NULL,
  registros_procesados integer  NULL,
  estado           varchar(20)  NOT NULL CHECK (estado IN ('INICIADO','COMPLETADO','ERROR')),
  mensaje_error    text         NULL,
  forzar_carga     boolean      NOT NULL DEFAULT false
);

CREATE INDEX IF NOT EXISTS idx_padron_cuit ON padron_rgs (cuit);
CREATE INDEX IF NOT EXISTS idx_padron_vig ON padron_rgs (vigencia_desde, vigencia_hasta);
CREATE INDEX IF NOT EXISTS idx_padron_alicuota_nonzero ON padron_rgs (alicuota) WHERE alicuota > 0;
CREATE INDEX IF NOT EXISTS idx_log_fecha ON padron_log_ejecucion (fecha_ejecucion);
"""

SQL_MERGE = """
INSERT INTO  padron_rgs (
  regimen, fecha_emision, vigencia_desde, vigencia_hasta, cuit,
  flag1, flag2, flag3, alicuota, codigo
)
SELECT
  col1,
  to_date(col2,  'DDMMYYYY'),
  to_date(col3,  'DDMMYYYY'),
  to_date(col4,  'DDMMYYYY'),
  lpad(regexp_replace(col5, '\\D', '', 'g'), 11, '0'),
  NULLIF(col6,''),
  NULLIF(col7,''),
  NULLIF(col8,''),
  NULLIF(REPLACE(col9, ',', '.'), '')::numeric(6,2),
  NULLIF(col10,'')::integer
FROM  padron_rgs_raw
WHERE col1 IN ('P','R')
  AND col5 ~ '^[0-9]{11}$'
  AND col2 ~ '^\\d{8}$' AND col3 ~ '^\\d{8}$' AND col4 ~ '^\\d{8}$'
ON CONFLICT (regimen, cuit, vigencia_desde, vigencia_hasta, fecha_emision)
DO UPDATE SET
  flag1    = EXCLUDED.flag1,
  flag2    = EXCLUDED.flag2,
  flag3    = EXCLUDED.flag3,
  alicuota = EXCLUDED.alicuota,
  codigo   = EXCLUDED.codigo;

TRUNCATE TABLE  padron_rgs_raw;
ANALYZE  padron_rgs;
"""

def print_with_timestamp(message):
    """Imprime un mensaje con timestamp"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}")

def contar_lineas_archivo(ruta):
    """Cuenta las líneas de un archivo de forma eficiente"""
    with open(ruta, 'r', encoding='utf-8') as f:
        return sum(1 for _ in f)

def mostrar_progreso(actual, total, inicio_tiempo):
    """Muestra el progreso de procesamiento"""
    porcentaje = (actual / total) * 100
    tiempo_transcurrido = time.time() - inicio_tiempo
    velocidad = actual / tiempo_transcurrido if tiempo_transcurrido > 0 else 0
    tiempo_estimado = (total - actual) / velocidad if velocidad > 0 else 0
    
    print_with_timestamp(f"Progreso: {actual:,}/{total:,} ({porcentaje:.1f}%) - {velocidad:.0f} reg/seg - ETA: {tiempo_estimado:.0f}s")

def enviar_evento(nombre_archivo, estado, mensaje=None, fecha_hora=None):
    """Envía evento a la URL de notificaciones"""
    try:
        if fecha_hora is None:
            fecha_hora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        body = {
            "nombre_archivo": nombre_archivo,
            "fecha_hora": fecha_hora,
            "estado": estado
        }
        
        if mensaje:
            body["mensaje"] = mensaje
        
        webhook_url = os.getenv('WEBHOOK_URL', 'https://primary-production-bixen.up.railway.app/webhook-test/event_info')
        response = requests.post(webhook_url, json=body, timeout=10)
        print_with_timestamp(f"Evento enviado: {estado} - Status: {response.status_code}")
        
    except Exception as e:
        print_with_timestamp(f"Error al enviar evento: {e}")
        # No interrumpir el proceso por fallos de notificación

def main():
    inicio_total = time.time()
    fecha_inicio = datetime.now()
    print_with_timestamp("=== INICIO DE CARGA DE PADRÓN ===")
    
    load_dotenv()
    
    # Variables para logging
    log_id = None
    conn = None
    cur = None
    
    # Construir DSN desde variables de entorno
    host = os.getenv('DB_HOST', 'localhost')
    port = os.getenv('DB_PORT', '5432')
    dbname = os.getenv('DB_NAME')
    user = os.getenv('DB_USER')
    password = os.getenv('DB_PASSWORD')
    
    if not all([dbname, user, password]):
        print_with_timestamp("Error: Faltan variables de entorno requeridas (DB_NAME, DB_USER, DB_PASSWORD)")
        sys.exit(1)
    
    dsn = f"host={host} port={port} dbname={dbname} user={user} password={password}"
    
    # Obtener parámetros
    forzar_carga = os.getenv('FORZAR_CARGA', 'N').upper() == 'S'
    
    if len(sys.argv) >= 2:
        ruta = sys.argv[1]
        # Verificar si hay parámetro forzar_carga en argumentos
        if len(sys.argv) >= 3 and sys.argv[2].upper() == 'S':
            forzar_carga = True
    else:
        ruta = os.getenv('PADRON_FILE', 'padron.txt')
        print_with_timestamp(f"Usando archivo por defecto: {ruta}")
        
    if not ruta:
        print_with_timestamp("Uso: carga_padron_arba.py <ruta_txt> [forzar_carga=S]")
        print_with_timestamp("Ej:  carga_padron_arba.py PadronRGSPerMMAAAA.txt")
        print_with_timestamp("     carga_padron_arba.py PadronRGSPerMMAAAA.txt S")
        print_with_timestamp("O definir PADRON_FILE y FORZAR_CARGA en .env")
        sys.exit(1)
    if not os.path.exists(ruta):
        print_with_timestamp(f"No existe: {ruta}")
        sys.exit(1)
    
    # Contar registros del archivo para progreso
    print_with_timestamp("Analizando archivo...")
    total_registros = contar_lineas_archivo(ruta)
    print_with_timestamp(f"Archivo contiene {total_registros:,} registros")

    try:
        conn = psycopg2.connect(dsn)
        conn.autocommit = False
        cur = conn.cursor()
        
        # Crear tablas si no existen
        for stmt in SQL_CREATE.split(";\n"):
            if stmt.strip():
                cur.execute(stmt + ";")
        
        # Verificar si el archivo ya fue procesado exitosamente antes
        nombre_archivo = os.path.basename(ruta)
        if not forzar_carga:
            cur.execute("""
                SELECT COUNT(*) FROM padron_log_ejecucion 
                WHERE nombre_archivo = %s AND estado = 'COMPLETADO'
            """, (nombre_archivo,))
            
            archivos_procesados = cur.fetchone()[0]
            
            if archivos_procesados > 0:
                print_with_timestamp(f"El archivo '{nombre_archivo}' ya fue procesado exitosamente anteriormente")
                print_with_timestamp("Use el parámetro 'S' o configure FORZAR_CARGA=S para forzar el reprocesamiento")
                conn.close()
                sys.exit(0)  # Salir exitosamente sin error
            else:
                print_with_timestamp(f"Verificación OK: El archivo '{nombre_archivo}' no ha sido procesado anteriormente")
        else:
            print_with_timestamp(f"FORZAR_CARGA=S: Procesando '{nombre_archivo}' aunque ya haya sido procesado")
        
        # Inicializar log de ejecución
        cur.execute("""
            INSERT INTO padron_log_ejecucion (fecha_inicio, nombre_archivo, total_registros, estado, forzar_carga)
            VALUES (%s, %s, %s, 'INICIADO', %s)
            RETURNING id
        """, (fecha_inicio, os.path.basename(ruta), total_registros, forzar_carga))
        
        log_id = cur.fetchone()[0]
        conn.commit()
        print_with_timestamp(f"Log de ejecución iniciado con ID: {log_id}")

    except Exception as e:
        print_with_timestamp(f"Error al conectar con la base de datos o crear log inicial: {e}")
        sys.exit(1)
    
    # Continuar con el proceso principal dentro de un try/except separado
    try:
        # Asegurar encoding compatible (muchos TXT vienen en LATIN1)
        cur.execute("SET client_encoding TO 'UTF8';")

        # Obtener fecha de emisión del archivo
        fecha_emision_archivo = None
        with open(ruta, "r", encoding="utf-8") as f:
            primera_linea = f.readline().strip()
            if primera_linea:
                campos = primera_linea.split(';')
                if len(campos) >= 2:
                    fecha_emision_archivo = campos[1]  # col2

        if not fecha_emision_archivo:
            # Actualizar log con error
            cur.execute("""
                UPDATE padron_log_ejecucion 
                SET fecha_fin = %s, estado = 'ERROR', mensaje_error = %s
                WHERE id = %s
            """, (datetime.now(), "No se pudo obtener la fecha de emisión del archivo", log_id))
            conn.commit()
            print_with_timestamp("Error: No se pudo obtener la fecha de emisión del archivo")
            conn.close()
            sys.exit(1)

        # Obtener la fecha de emisión más reciente de la tabla
        cur.execute("SELECT MAX(fecha_emision) FROM padron_rgs LIMIT 1")
        fecha_tabla_result = cur.fetchone()[0]
    
        # Convertir fecha del archivo a objeto datetime para comparar
        try:
            fecha_archivo_dt = datetime.strptime(fecha_emision_archivo, '%d%m%Y')
            
            if fecha_tabla_result:
                # Si la fecha del archivo es anterior a la fecha más reciente en la tabla, borrar toda la tabla
                if fecha_archivo_dt.date() > fecha_tabla_result:
                    print_with_timestamp(f"La fecha del archivo ({fecha_emision_archivo}) es mayor a la fecha más reciente en la tabla ({fecha_tabla_result})")
                    print_with_timestamp("Eliminando todos los registros de la tabla padron_rgs...")
                    cur.execute("DELETE FROM padron_rgs")
                    registros_eliminados = cur.rowcount
                    print_with_timestamp(f"Registros eliminados: {registros_eliminados}")
                else:
                    # Solo verificar/eliminar registros con la misma fecha si la fecha no es antigua
                    if not forzar_carga:
                        # Verificar si existen registros con esa fecha
                        cur.execute("""
                            SELECT COUNT(*) FROM padron_rgs 
                            WHERE fecha_emision = to_date(%s, 'DDMMYYYY')
                        """, (fecha_emision_archivo,))
                        
                        registros_existentes = cur.fetchone()[0]
                        
                        if registros_existentes > 0:
                            # Actualizar log con error
                            cur.execute("""
                                UPDATE padron_log_ejecucion 
                                SET fecha_fin = %s, estado = 'ERROR', mensaje_error = %s
                                WHERE id = %s
                            """, (datetime.now(), f"Ya existen {registros_existentes} registros con fecha {fecha_emision_archivo}", log_id))
                            conn.commit()
                            print_with_timestamp(f"Error: Ya existen {registros_existentes} registros con fecha de emisión {fecha_emision_archivo}")
                            print_with_timestamp("Use el parámetro 'S' o configure FORZAR_CARGA=S para forzar la carga")
                            conn.close()
                            sys.exit(1)
                        
                        print_with_timestamp(f"Verificación OK: No existen registros previos con fecha {fecha_emision_archivo}")
                    else:
                        # Si forzar_carga=S, verificar y eliminar registros existentes con la misma fecha
                        cur.execute("""
                            SELECT COUNT(*) FROM padron_rgs 
                            WHERE fecha_emision = to_date(%s, 'DDMMYYYY')
                        """, (fecha_emision_archivo,))
                        
                        registros_existentes = cur.fetchone()[0]
                        
                        if registros_existentes > 0:
                            print_with_timestamp(f"FORZAR_CARGA=S: Eliminando {registros_existentes} registros existentes con fecha {fecha_emision_archivo}")
                            cur.execute("""
                                DELETE FROM padron_rgs 
                                WHERE fecha_emision = to_date(%s, 'DDMMYYYY')
                            """, (fecha_emision_archivo,))
                            print_with_timestamp(f"Registros eliminados: {cur.rowcount}")
                        else:
                            print_with_timestamp(f"FORZAR_CARGA=S: No hay registros previos con fecha {fecha_emision_archivo}")
            else:
                # Si no hay registros en la tabla, proceder normalmente
                print_with_timestamp("La tabla está vacía, procediendo con la carga...")
        
        except ValueError:
            # Actualizar log con error
            cur.execute("""
                UPDATE padron_log_ejecucion 
                SET fecha_fin = %s, estado = 'ERROR', mensaje_error = %s
                WHERE id = %s
            """, (datetime.now(), f"Formato de fecha inválido: {fecha_emision_archivo}", log_id))
            conn.commit()
            print_with_timestamp(f"Error: Formato de fecha inválido en el archivo: {fecha_emision_archivo}")
            conn.close()
            sys.exit(1)

        # Carga masiva al staging con COPY
        inicio_carga = time.time()
        print_with_timestamp("Iniciando carga masiva a padron_rgs_raw...")
        
        # Enviar evento de inicio
        enviar_evento(
            nombre_archivo=os.path.basename(ruta),
            estado="INICIADO",
            fecha_hora=fecha_inicio.strftime("%Y-%m-%d %H:%M:%S")
        )
        
        try:
            with open(ruta, "r", encoding="utf-8", newline="") as f:
                cur.copy_expert(
                    "COPY  padron_rgs_raw FROM STDIN WITH (FORMAT csv, DELIMITER ';', HEADER false, NULL '')",
                    f
                )
        except Exception as copy_error:
            # Error específico en la carga COPY
            fecha_fin = datetime.now()
            mensaje_error = f"Error en COPY: {str(copy_error)}"
            
            print_with_timestamp(f"ERROR durante la carga masiva: {copy_error}")
            print_with_timestamp("Posibles causas: formato de archivo incorrecto, encoding no compatible, permisos insuficientes")
            
            # Enviar evento de error
            enviar_evento(
                nombre_archivo=os.path.basename(ruta),
                estado="ERROR",
                mensaje=mensaje_error,
                fecha_hora=fecha_fin.strftime("%Y-%m-%d %H:%M:%S")
            )
            
            # Hacer rollback para limpiar la transacción abortada
            conn.rollback()
            
            # Actualizar log con error específico de COPY
            cur.execute("""
                UPDATE padron_log_ejecucion 
                SET fecha_fin = %s, estado = 'ERROR', mensaje_error = %s
                WHERE id = %s
            """, (fecha_fin, mensaje_error, log_id))
            conn.commit()
            
            raise  # Re-lanzar la excepción para que sea capturada por el try principal
        
        fin_carga = time.time()
        tiempo_carga = fin_carga - inicio_carga
        print_with_timestamp(f"Carga completada en {tiempo_carga:.1f}s ({total_registros/tiempo_carga:.0f} reg/seg)")

        # Merge a final
        inicio_merge = time.time()
        print_with_timestamp("Iniciando normalización y actualización de tabla final...")
        
        try:
            cur.execute(SQL_MERGE)
        except Exception as merge_error:
            # Error específico en el MERGE
            fecha_fin = datetime.now()
            mensaje_error = f"Error en MERGE: {str(merge_error)}"
            
            print_with_timestamp(f"ERROR durante la normalización: {merge_error}")
            print_with_timestamp("Posibles causas: restricciones de integridad, tipos de datos incompatibles, claves duplicadas")
            
            # Enviar evento de error
            enviar_evento(
                nombre_archivo=os.path.basename(ruta),
                estado="ERROR",
                mensaje=mensaje_error,
                fecha_hora=fecha_fin.strftime("%Y-%m-%d %H:%M:%S")
            )
            
            # Hacer rollback para limpiar la transacción abortada
            conn.rollback()
            
            # Actualizar log con error específico de MERGE
            cur.execute("""
                UPDATE padron_log_ejecucion 
                SET fecha_fin = %s, estado = 'ERROR', mensaje_error = %s
                WHERE id = %s
            """, (fecha_fin, mensaje_error, log_id))
            conn.commit()
            
            raise  # Re-lanzar la excepción para que sea capturada por el try principal
        
        # Obtener el número real de registros procesados
        cur.execute("SELECT COUNT(*) FROM padron_rgs")
        registros_en_rgs = cur.fetchone()[0]
        
        fin_merge = time.time()
        tiempo_merge = fin_merge - inicio_merge
        registros_procesados = registros_en_rgs  # Usar el conteo real
        print_with_timestamp(f"Normalización completada en {tiempo_merge:.1f}s - {registros_procesados:,} registros procesados")

        # Verificar que los registros procesados coincidan con los del archivo
        fecha_fin = datetime.now()
        tiempo_total = fin_merge - inicio_total
        
        if registros_procesados != total_registros:
            # Hay diferencia en los registros - marcar como error
            diferencia = total_registros - registros_procesados
            mensaje_error = f"Diferencia en registros: Archivo={total_registros:,}, Procesados={registros_procesados:,}, Diferencia={diferencia:,}"
            
            print_with_timestamp(f"ERROR: {mensaje_error}")
            print_with_timestamp("Posibles causas: registros con formato inválido, fechas incorrectas, CUITs malformados")
            
            # Enviar evento de error por diferencia de registros
            enviar_evento(
                nombre_archivo=os.path.basename(ruta),
                estado="ERROR",
                mensaje=mensaje_error,
                fecha_hora=fecha_fin.strftime("%Y-%m-%d %H:%M:%S")
            )
            
            # Actualizar log con error
            cur.execute("""
                UPDATE padron_log_ejecucion 
                SET fecha_fin = %s, tiempo_transcurrido = %s, estado = 'ERROR', 
                    registros_procesados = %s, mensaje_error = %s
                WHERE id = %s
            """, (fecha_fin, f"{tiempo_total:.1f} seconds", registros_procesados, mensaje_error, log_id))
            
            conn.commit()
            cur.close()
            conn.close()
            
            print_with_timestamp("Proceso finalizado con errores. Revisar registros rechazados.")
            sys.exit(1)
        else:
            # Todo OK - registros coinciden
            print_with_timestamp(f"Verificación OK: {registros_procesados:,} registros procesados correctamente")
            
            # Enviar evento de completado exitoso
            enviar_evento(
                nombre_archivo=os.path.basename(ruta),
                estado="COMPLETADO",
                mensaje=f"Procesados {registros_procesados:,} registros en {tiempo_total:.1f}s",
                fecha_hora=fecha_fin.strftime("%Y-%m-%d %H:%M:%S")
            )
            
            # Actualizar log con éxito
            cur.execute("""
                UPDATE padron_log_ejecucion 
                SET fecha_fin = %s, tiempo_transcurrido = %s, estado = 'COMPLETADO', registros_procesados = %s
                WHERE id = %s
            """, (fecha_fin, f"{tiempo_total:.1f} seconds", registros_procesados, log_id))
        
        conn.commit()
        cur.close()
        conn.close()
        
        # Tiempo total
        print_with_timestamp(f"=== PROCESO COMPLETADO ===")
        print_with_timestamp(f"Tiempo total: {tiempo_total:.1f}s ({tiempo_total/60:.1f} min)")
        print_with_timestamp(f"Rendimiento promedio: {total_registros/tiempo_total:.0f} registros/segundo")
        print_with_timestamp("Proceso finalizado exitosamente.")

    except Exception as e:
        # Manejar errores generales
        fecha_fin = datetime.now()
        
        # Enviar evento de error general
        try:
            enviar_evento(
                nombre_archivo=os.path.basename(ruta) if 'ruta' in locals() else "archivo_desconocido",
                estado="ERROR",
                mensaje=f"Error general: {str(e)}",
                fecha_hora=fecha_fin.strftime("%Y-%m-%d %H:%M:%S")
            )
        except:
            pass  # No interrumpir por fallos de notificación
        
        if log_id and cur:
            try:
                cur.execute("""
                    UPDATE padron_log_ejecucion 
                    SET fecha_fin = %s, estado = 'ERROR', mensaje_error = %s
                    WHERE id = %s
                """, (fecha_fin, str(e), log_id))
                conn.commit()
            except:
                pass  # Si hay error al actualizar log, continuamos
        
        print_with_timestamp(f"Error durante la ejecución: {e}")
        if conn:
            conn.close()
        sys.exit(1)

if __name__ == "__main__":
    main()
