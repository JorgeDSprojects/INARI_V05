# Tutorial: verify in pgAdmin that the historian is saving broker data

## 1. Log in to pgAdmin
Open `http://localhost:5051` and log in with `admin@uns-historian.io` / `pgadminpassword` (or whatever values you have in `UNS_HISTORIAN/.env`).

## 2. Connect to the server and browse to the table
In the left-hand tree:

```
Servers → UNS Historian → Databases → uns_historian → Schemas → public → Tables → mqtt_messages
```

If it asks for a password again: `historianpassword` (the Postgres `historian` user's password, not pgAdmin's own login password).

## 3. View the data with one click
Right-click `mqtt_messages` → **View/Edit Data** → **First 100 Rows**. You'll see these columns:

| column | what it is |
|---|---|
| `time` | the reading's timestamp (from the payload when present, otherwise arrival time) |
| `topic` | the full MQTT topic (e.g. `UNS/enterprise1/site1/.../cell1_informative`) |
| `payload` | the parsed JSON |
| `raw_payload` | the raw string as received (in case it wasn't valid JSON) |
| `qos` / `retain` | MQTT message flags |

If this loads rows, the **broker → ingestor → TimescaleDB** pipeline is already working.

## 4. Confirm it's still saving live (not just old history)
This is the most reliable check — use the **Query Tool** instead of the row editor:

1. Right-click `uns_historian` (the database, not the table) → **Query Tool**
2. Run:

```sql
SELECT count(*) FROM mqtt_messages;
```

3. Note the number, wait ~10-15 seconds (let EMQX/Node-RED publish something), then run the same query again. If the count went up, it's saving in real time.

More direct — see only what arrived in the last minute:

```sql
SELECT time, topic, payload
FROM mqtt_messages
WHERE time > now() - interval '1 minute'
ORDER BY time DESC;
```

If this returns rows, ingestion is active right now.

## 5. Filter by a specific topic
To confirm a specific asset/broker is being saved:

```sql
SELECT time, payload
FROM mqtt_messages
WHERE topic LIKE '%<part_of_the_topic>%'
ORDER BY time DESC
LIMIT 20;
```

Replace `<part_of_the_topic>` with, for example, your cell or enterprise name.

## 6. If you don't see anything
Before suspecting pgAdmin, check the ingestor's logs — that's the source of truth:

```bash
docker logs uns_historian_ingestor --tail 30
```

You should see `Flushed N row(s)` lines every few seconds. If they're not showing up, the problem is in the ingestor/EMQX, not in pgAdmin.
