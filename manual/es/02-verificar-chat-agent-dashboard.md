# Tutorial: comprobar el chat que crea dashboards (UNS_DASHBOARD + UNS_OLLAMA + UNS_MCP)

Esto verifica la pieza completa que se acaba de fusionar a `master`: un panel de chat dentro de UNS_DASHBOARD que crea/edita dashboards en borrador hablando en lenguaje natural, apoyado en un LLM local (Ollama) que consulta datos reales de UNS_SILVER a través de UNS_MCP.

## 0. Comprobar que todo está arriba

```bash
docker ps --format "table {{.Names}}\t{{.Status}}" | grep -E "ollama|mcp|dashboard|silver"
```

Deberías ver, todos `Up` (idealmente `healthy`):

- `uns_ollama`
- `uns_mcp_server`
- `uns_dashboard_backend`, `uns_dashboard_frontend`, `uns_dashboard_postgres`
- `uns_silver_postgres` (de donde vienen las señales reales)

Si `uns_ollama` no existe todavía, súbelo:

```bash
cd UNS_OLLAMA && docker compose up -d
```

## 1. Comprobar el estado del asistente por API

```bash
curl -s http://localhost:8001/chat/status
```

Resultado esperado:

```json
{"available":true,"provider_type":"openai_compatible","reason":null}
```

Si sale `"available":false`, mira el campo `reason` — normalmente es que Ollama no tiene el modelo descargado, o que `MCP_API_KEY`/`LLM_PROVIDER_TYPE` no están puestos en `UNS_DASHBOARD/.env`. Para dejarlo funcionando de forma permanente (no solo en el contenedor ya arrancado), añade a `UNS_DASHBOARD/.env`:

```
LLM_PROVIDER_TYPE=openai_compatible
MCP_API_KEY=changeme-local-dev-key
```

(la clave debe coincidir con `MCP_API_KEY` en `UNS_MCP/.env`) y reconstruye:

```bash
cd UNS_DASHBOARD && docker compose up -d --build dashboard_backend
```

## 2. Probarlo desde el navegador (la forma real de comprobarlo)

1. Abre `http://localhost:3002`
2. Entra en el editor de un dashboard (crea uno nuevo o abre uno en borrador)
3. Busca el panel de chat en el editor. Si el asistente está disponible verás un cuadro de texto habilitado; si no, verás un aviso "Asistente no disponible — …" y **no habrá cuadro de texto ni botón de enviar** (esto es a propósito: sin proveedor configurado, el chat se desactiva solo, nunca da error)
4. Escribe algo como:

   > Crea un dashboard llamado Prueba Manual y añade una gráfica con alguna señal que exista

5. Espera la respuesta (puede tardar unos segundos, el modelo corre en local). Debería confirmarte qué hizo, y si creó un dashboard nuevo la página debería llevarte a su editor

## 3. Confirmarlo por API (por si quieres la prueba "dura")

```bash
curl -s http://localhost:8001/dashboards/ | python -c "import sys,json; [print(d['id'], d['name'], d['status']) for d in json.load(sys.stdin)]"
```

Busca el dashboard que acabas de nombrar. Cógete su `id` y mira el detalle:

```bash
curl -s http://localhost:8001/dashboards/<el-id-de-arriba>
```

Deberías ver `"status":"draft"` y, si el chat encontró una señal real, un array `charts` con al menos un elemento.

## 4. Comprobar que respeta las reglas

- Pídele que **publique** el dashboard, y luego pídele que le añada otra gráfica o la borre → debe negarse explicando que ya está publicado (el chat solo edita borradores)
- Fíjate en que nunca te ofrece "borrar todo el dashboard" — esa capacidad no existe en el chat a propósito, solo borrar gráficas sueltas

## 5. Comprobar la degradación (apagar el LLM y ver que no rompe nada)

```bash
cd UNS_OLLAMA && docker compose stop
curl -s http://localhost:8001/chat/status
```

Esperado: `{"available":false,...}` con una razón. Recarga el editor en el navegador: el chat debe mostrarse desactivado, no roto. Luego reactívalo:

```bash
cd UNS_OLLAMA && docker compose start
```

## 6. Ver las conversaciones guardadas (pgAdmin)

En pgAdmin (`http://localhost:5051`, o el pgAdmin de UNS_DASHBOARD si tiene uno propio — si no, conecta con cualquier cliente Postgres a `localhost:5435`, usuario/clave en `UNS_DASHBOARD/.env`):

```
Databases → uns_dashboard → Schemas → public → Tables → chat_sessions / chat_messages
```

```sql
SELECT id, dashboard_id, created_at FROM chat_sessions ORDER BY created_at DESC LIMIT 5;

SELECT role, content, created_at
FROM chat_messages
WHERE session_id = '<el-id-de-la-sesión-de-arriba>'
ORDER BY created_at;
```

Deberías ver la conversación completa: tus mensajes (`role='user'`), las respuestas (`role='assistant'`) y, si el modelo llamó a alguna herramienta, filas `role='tool'` con el resultado de cada llamada.

## 7. Si algo no cuadra

```bash
docker logs uns_dashboard_backend --tail 50
docker logs uns_ollama --tail 30
docker logs uns_mcp_server --tail 30
```

Un fallo típico: el modelo confunde el nombre de una señal con el "prefijo de topic" y te dice que una señal no existe cuando sí existe — es un problema conocido del modelo (`qwen2.5:14b-instruct`), ya mitigado en el system prompt, pero puede seguir pasando ocasionalmente. No es un fallo del sistema, es el LLM equivocándose.
