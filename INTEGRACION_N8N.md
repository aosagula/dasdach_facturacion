# Integración del Proceso de Facturación Finnegans con n8n

## Descripción General

El proceso de facturación de Finnegans se ha convertido en un servicio **asíncrono con notificación por webhook**. Esto significa que:

1. **n8n inicia el proceso** mediante un POST request
2. **La API responde inmediatamente** con un `job_id` (sin esperar que termine)
3. **El proceso se ejecuta en background** (puede tardar más de 30 minutos)
4. **Cuando finaliza**, la API envía los resultados a un **webhook de n8n** automáticamente

## Endpoints Disponibles

### 1. Iniciar Proceso de Facturación

**Endpoint:** `POST /finnegans/start`

**Body (JSON):**
```json
{
  "company": "Das Dach",
  "webhook_url": "https://tu-n8n.com/webhook/finnegans-result"
}
```

**Respuesta Inmediata:**
```json
{
  "job_id": "finn_20250117_123456_abc123",
  "status": "started",
  "message": "Proceso iniciado en background. Recibirás notificación en el webhook cuando finalice.",
  "company": "Das Dach",
  "webhook_url": "https://tu-n8n.com/webhook/finnegans-result"
}
```

### 2. Consultar Estado de un Job (Opcional)

**Endpoint:** `GET /finnegans/status/{job_id}`

**Respuesta:**
```json
{
  "job_id": "finn_20250117_123456_abc123",
  "status": "running",
  "company": "Das Dach",
  "started_at": "2025-01-17T12:34:56",
  "logs": []
}
```

### 3. Listar Todos los Jobs (Debug)

**Endpoint:** `GET /finnegans/jobs`

**Respuesta:**
```json
{
  "total": 5,
  "jobs": [
    {
      "job_id": "finn_20250117_123456_abc123",
      "status": "completed",
      "company": "Das Dach",
      "started_at": "2025-01-17T12:34:56",
      "finished_at": "2025-01-17T12:45:23",
      "success": true
    }
  ]
}
```

## Configuración en n8n

### Opción 1: Workflow con Webhook (Recomendado)

**Flujo:**
```
[Trigger/Schedule] → [Webhook] → [HTTP Request: Iniciar Proceso] → [Wait for Webhook] → [Procesar Resultado]
```

**Configuración de Nodos:**

#### Nodo 1: Webhook (Esperar Resultado)
- **Tipo:** Webhook
- **HTTP Method:** POST
- **Path:** `/webhook/finnegans-result` (o el que prefieras)
- **Wait for Webhook Response:** Activado
- **Guardar la URL** del webhook para usarla en el siguiente nodo

#### Nodo 2: HTTP Request (Iniciar Proceso)
- **Tipo:** HTTP Request
- **Method:** POST
- **URL:** `https://tu-servidor.com/finnegans/start`
- **Body Content Type:** JSON
- **Body:**
```json
{
  "company": "Das Dach",
  "webhook_url": "{{ $node["Webhook"].json["webhookUrl"] }}"
}
```

#### Nodo 3: Procesar Resultado
- **Tipo:** Code / Function / Lo que necesites
- **Input:** Datos del webhook que recibirás automáticamente

**Payload que recibirás en el webhook cuando finalice:**
```json
{
  "job_id": "finn_20250117_123456_abc123",
  "status": "completed",
  "company": "Das Dach",
  "started_at": "2025-01-17T12:34:56",
  "finished_at": "2025-01-17T12:45:23",
  "duration_seconds": 627.5,
  "success": true,
  "resumen": {
    "total_remitos": 15,
    "exitosos": 14,
    "fallidos": 1,
    "no_procesados": 0
  },
  "logs": [
    {
      "timestamp": "2025-01-17T12:34:56",
      "message": "Iniciando proceso..."
    }
  ],
  "log_completo": "... todo el log del proceso ..."
}
```

### Opción 2: Polling (Menos Eficiente)

Si no puedes usar webhooks, puedes hacer polling:

**Flujo:**
```
[Trigger] → [HTTP: Iniciar] → [Wait 2min] → [HTTP: Check Status] → [Loop hasta completar]
```

#### Nodo 1: Iniciar Proceso
```json
POST /finnegans/start
{
  "company": "Das Dach"
}
```

#### Nodo 2: Esperar
- Wait 2 minutes

#### Nodo 3: Verificar Estado
```
GET /finnegans/status/{{ $json["job_id"] }}
```

#### Nodo 4: Loop
- Si `status === "running"`, volver al Nodo 2
- Si `status === "completed" || "failed"`, continuar

### Opción 3: Schedule Simple

Para ejecutar automáticamente cada día:

**Flujo:**
```
[Schedule Trigger] → [HTTP Request: Iniciar] → [Done]
```

El resultado llegará al webhook que configures (puede ser otro workflow).

## Variables de Entorno

No se requieren nuevas variables de entorno. El endpoint usa la configuración existente del script `finnegans_login.py`.

## Ejemplo Completo de Workflow n8n

```json
{
  "nodes": [
    {
      "name": "Schedule Trigger",
      "type": "n8n-nodes-base.scheduleTrigger",
      "position": [250, 300],
      "parameters": {
        "rule": {
          "interval": [
            {
              "field": "hours",
              "hoursInterval": 24
            }
          ]
        }
      }
    },
    {
      "name": "Webhook",
      "type": "n8n-nodes-base.webhook",
      "position": [450, 300],
      "parameters": {
        "httpMethod": "POST",
        "path": "finnegans-result",
        "responseMode": "lastNode",
        "options": {}
      },
      "webhookId": "auto-generated"
    },
    {
      "name": "Iniciar Facturación",
      "type": "n8n-nodes-base.httpRequest",
      "position": [650, 300],
      "parameters": {
        "method": "POST",
        "url": "https://tu-servidor.com/finnegans/start",
        "sendBody": true,
        "bodyParameters": {
          "parameters": [
            {
              "name": "company",
              "value": "Das Dach"
            },
            {
              "name": "webhook_url",
              "value": "={{ $node[\"Webhook\"].json[\"webhookUrl\"] }}"
            }
          ]
        },
        "options": {}
      }
    },
    {
      "name": "Procesar Resultado",
      "type": "n8n-nodes-base.function",
      "position": [850, 300],
      "parameters": {
        "functionCode": "// El webhook recibirá automáticamente el resultado\nconst resultado = items[0].json;\n\nif (resultado.success) {\n  console.log(`✅ Proceso exitoso: ${resultado.resumen.exitosos} facturas generadas`);\n} else {\n  console.log(`❌ Proceso falló: ${resultado.error}`);\n}\n\nreturn items;"
      }
    },
    {
      "name": "Enviar Email Resumen",
      "type": "n8n-nodes-base.emailSend",
      "position": [1050, 300],
      "parameters": {
        "fromEmail": "noreply@tudominio.com",
        "toEmail": "admin@tudominio.com",
        "subject": "Reporte de Facturación Finnegans",
        "text": "={{ $json.log_completo }}"
      }
    }
  ],
  "connections": {
    "Schedule Trigger": {
      "main": [[{ "node": "Webhook", "type": "main", "index": 0 }]]
    },
    "Webhook": {
      "main": [[{ "node": "Iniciar Facturación", "type": "main", "index": 0 }]]
    },
    "Iniciar Facturación": {
      "main": [[{ "node": "Procesar Resultado", "type": "main", "index": 0 }]]
    },
    "Procesar Resultado": {
      "main": [[{ "node": "Enviar Email Resumen", "type": "main", "index": 0 }]]
    }
  }
}
```

## Estados Posibles del Job

| Estado | Descripción |
|--------|-------------|
| `started` | Proceso iniciado, ejecutándose en background |
| `running` | Proceso en ejecución (si consultas status) |
| `completed` | Proceso finalizado exitosamente |
| `failed` | Proceso finalizado con errores |
| `timeout` | Proceso excedió el tiempo límite (30 min) |
| `error` | Error inesperado durante la ejecución |

## Estructura del Resumen

El campo `resumen` en el resultado contiene:

```json
{
  "total_remitos": 15,      // Total de remitos encontrados
  "exitosos": 14,           // Facturas generadas exitosamente
  "fallidos": 1,            // Facturas que fallaron
  "no_procesados": 0        // Remitos que no se procesaron (ej: monto 0)
}
```

## Logs

Los logs se entregan en dos formatos:

1. **`logs`**: Array estructurado con timestamp
```json
[
  {
    "timestamp": "2025-01-17T12:34:56.789",
    "message": "[2025-01-17 12:34:56.789] Iniciando proceso..."
  }
]
```

2. **`log_completo`**: String con todo el log (útil para emails o debugging)

## Manejo de Errores

### Error en el Proceso
Si el proceso falla, recibirás:
```json
{
  "status": "failed",
  "success": false,
  "resumen": { ... },
  "log_completo": "... logs con errores ..."
}
```

### Timeout
Si el proceso excede 30 minutos:
```json
{
  "status": "timeout",
  "error": "Proceso excedió el tiempo límite de 30 minutos",
  "duration_seconds": 1800
}
```

### Error de Webhook
Si falla el webhook, el job se completa igual y los datos quedan en el storage. Puedes consultarlos con `GET /finnegans/status/{job_id}`.

## Testing

### Test Local con curl

```bash
# Iniciar proceso
curl -X POST http://localhost:8000/finnegans/start \
  -H "Content-Type: application/json" \
  -d '{
    "company": "Das Dach",
    "webhook_url": "https://webhook.site/tu-unique-url"
  }'

# Consultar estado
curl http://localhost:8000/finnegans/status/finn_20250117_123456_abc123

# Listar jobs
curl http://localhost:8000/finnegans/jobs
```

### Test con Webhook.site

1. Ve a https://webhook.site
2. Copia tu URL única
3. Úsala como `webhook_url` al iniciar el proceso
4. Verás el resultado cuando el proceso finalice

## Notas Importantes

1. **El almacenamiento de jobs es en memoria**: Si reinicias el servidor, se pierden los jobs. Para producción, considera usar Redis.

2. **Timeout de 30 minutos**: Si el proceso tarda más, se marca como timeout.

3. **Threading vs AsyncIO**: Se usa threading porque el script `finnegans_login.py` es síncrono. Para mejor performance, considera refactorizar a async.

4. **Concurrencia**: Puedes ejecutar múltiples procesos en paralelo, pero ten cuidado con los recursos del servidor.

5. **Logs**: Los logs se capturan pero también se imprimen en consola para debugging.

## Próximos Pasos

- [ ] Implementar persistencia de jobs en PostgreSQL o Redis
- [ ] Agregar autenticación/API keys para los endpoints
- [ ] Implementar límite de jobs concurrentes
- [ ] Agregar métricas y monitoreo
- [ ] Webhook retry logic en caso de fallos

## Soporte

Para preguntas o issues, contacta al equipo de desarrollo.
