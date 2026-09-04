# Tutorial: verificar en pgAdmin que el historian está guardando datos del broker

## 1. Entra a pgAdmin
Abre `http://localhost:5051`, login con `admin@uns-historian.io` / `pgadminpassword` (o los valores que tengas en `UNS_HISTORIAN/.env`).

## 2. Conecta al servidor y navega hasta la tabla
En el árbol de la izquierda:

```
Servers → UNS Historian → Databases → uns_historian → Schemas → public → Tables → mqtt_messages
```

Si te pide contraseña de nuevo: `historianpassword` (la del usuario `historian` de Postgres, no la de pgAdmin).

## 3. Mira los datos con un clic
Clic derecho sobre `mqtt_messages` → **View/Edit Data** → **First 100 Rows**. Verás columnas:

| columna | qué es |
|---|---|
| `time` | timestamp del dato (del payload si lo trae, si no del momento de llegada) |
| `topic` | topic MQTT completo (ej. `UNS/enterprise1/site1/.../cell1_informative`) |
| `payload` | el JSON parseado |
| `raw_payload` | el string tal cual llegó (por si no era JSON válido) |
| `qos` / `retain` | flags MQTT del mensaje |

Si esto carga filas, el pipeline **broker → ingestor → TimescaleDB** ya está funcionando.

## 4. Comprobar que sigue guardando en vivo (no solo histórico viejo)
Esto es lo más fiable — usa el **Query Tool** en vez del editor de filas:

1. Clic derecho en `uns_historian` (la base, no la tabla) → **Query Tool**
2. Ejecuta:

```sql
SELECT count(*) FROM mqtt_messages;
```

3. Anota el número, espera ~10-15 segundos (deja que EMQX/Node-RED publique algo), vuelve a ejecutar la misma query. Si el número sube, se está guardando en tiempo real.

Más directo, ver solo lo llegado en el último minuto:

```sql
SELECT time, topic, payload
FROM mqtt_messages
WHERE time > now() - interval '1 minute'
ORDER BY time DESC;
```

Si esto devuelve filas, hay ingesta activa ahora mismo.

## 5. Filtrar por un topic concreto
Para comprobar que un asset/broker específico se está guardando:

```sql
SELECT time, payload
FROM mqtt_messages
WHERE topic LIKE '%<parte_del_topic>%'
ORDER BY time DESC
LIMIT 20;
```

Sustituye `<parte_del_topic>` por, por ejemplo, el nombre de tu cell o enterprise.

## 6. Si no ves nada
Antes de sospechar de pgAdmin, mira los logs del ingestor — es la fuente de verdad:

```bash
docker logs uns_historian_ingestor --tail 30
```

Deberías ver líneas `Flushed N row(s)` cada pocos segundos. Si no aparecen, el problema está en el ingestor/EMQX, no en pgAdmin.
