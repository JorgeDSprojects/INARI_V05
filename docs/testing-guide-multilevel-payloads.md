# Testing Guide — Multi-Level Payloads + Collapsible Tree + `_informative`

> Branch: `feature/uns-manager-multilevel-payloads`  
> Date: 2026-09-01

---

## Prerequisitos

```bash
docker compose up --build -d
# Esperar a: Application startup complete.
docker compose logs backend --tail=5
```

Servicios:
| Servicio | URL |
|---|---|
| Frontend | http://localhost:3001 |
| Backend API | http://localhost:8000/docs |
| EMQX Dashboard | http://localhost:18083 (admin/public) |
| MQTT Explorer | localhost:1883, sin credenciales |

---

## 1. Árbol colapsable

**Objetivo:** Los nodos del árbol lateral deben poder expandirse/colapsarse individualmente.

| Paso | Acción | Resultado esperado |
|---|---|---|
| 1 | Abrir la app → panel izquierdo | Se ve el árbol con Sites, Areas, Lines, Cells, Assets |
| 2 | Clic en la flecha `▼` de un Site | El Site se colapsa — sus Areas desaparecen |
| 3 | Clic en la flecha `▶` del mismo Site | El Site se expande — sus Areas reaparecen |
| 4 | Colapsar un Area dentro de un Site expandido | Solo colapsa esa Area, el Site permanece expandido |
| 5 | Colapsar un Site que tiene una Area colapsada | Todo el subárbol desaparece |
| 6 | Expandir ese Site de nuevo | La Area vuelve en su estado anterior (colapsada) |

---

## 2. Enterprise seleccionable

**Objetivo:** El nombre de la Enterprise en el header del panel izquierdo es clickeable.

| Paso | Acción | Resultado esperado |
|---|---|---|
| 1 | Clic en el nombre de la Enterprise (header del panel) | El workspace central carga con level = ENTERPRISE |
| 2 | Observar el header del workspace | Badge `ENTERPRISE`, nombre correcto |
| 3 | Seleccionar un Site, luego volver a clicar la Enterprise | El workspace cambia de nivel |
| 4 | Observar el texto del nombre en el panel | Se resalta en color accent cuando está seleccionado |

---

## 3. `_descriptive` payload en todos los niveles

**Objetivo:** Los 6 niveles (Enterprise, Site, Area, Line, Cell, Asset) permiten editar y publicar `_descriptive`.

### 3.1 Verificar tab `_descriptive` en cada nivel

Para **cada nivel** (Enterprise → Site → Area → Line → Cell → Asset):

| Paso | Acción | Resultado esperado |
|---|---|---|
| 1 | Seleccionar un nodo del nivel | Workspace carga con tab `_descriptive` activo |
| 2 | Clic en `Edit node` | Editor JSON se habilita |
| 3 | Escribir JSON válido, p.ej. `{"test": true, "level": "site"}` | Indicador `Valid JSON ✓` en verde |
| 4 | Clic en `SAVE` | El payload se persiste (sin MQTT) |
| 5 | Seleccionar otro nodo y volver | El payload cargado refleja lo guardado |
| 6 | Clic en `SAVE & PUBLISH` | Indicador `PUBLISHED ✓` aparece 3 segundos |

### 3.2 Verificar en MQTT Explorer

Con MQTT Explorer conectado a `localhost:1883`:

| Nivel | Topic esperado |
|---|---|
| Enterprise `Acme Corp` | `Acme_Corp/_descriptive` |
| Site `Plant 1` | `Acme_Corp/Plant_1/_descriptive` |
| Area `Assembly` | `Acme_Corp/Plant_1/Assembly/_descriptive` |
| Line `Line A` | `Acme_Corp/Plant_1/Assembly/Line_A/_descriptive` |
| Cell `Cell 01` | `Acme_Corp/Plant_1/Assembly/Line_A/Cell_01/_descriptive` |
| Asset `Motor X` | `Acme_Corp/Plant_1/Assembly/Line_A/Cell_01/Motor_X/_descriptive` |

> ✅ Los espacios se convierten en `_`, las mayúsculas se preservan.  
> ✅ Los mensajes son **retained** (QoS 1) — persisten en el broker.

---

## 4. Tab `_informative` en todos los niveles

**Objetivo:** Tab `_informative` presente y funcional en los 6 niveles.

| Paso | Acción | Resultado esperado |
|---|---|---|
| 1 | Seleccionar cualquier nodo | Workspace carga |
| 2 | Clic en tab `_informative` | Editor JSON vacío, read-only |
| 3 | Clic en `Edit node` | Editor se habilita para `_informative` |
| 4 | Editar payload, p.ej. `{"description": "informative data", "unit": "rpm"}` | `Valid JSON ✓` |
| 5 | Clic en `SAVE` | Persiste sin publicar |
| 6 | Cambiar al tab `_descriptive` | El editor `_descriptive` NO está en modo edición (estados independientes) |
| 7 | Volver a `_informative`, clic `SAVE & PUBLISH` | `PUBLISHED ✓` aparece |
| 8 | Verificar en MQTT Explorer | Topic `…/_informative` con el payload correcto |

### 4.1 Verificar topics `_informative` en MQTT Explorer

| Nivel | Topic esperado |
|---|---|
| Site `Plant 1` | `Acme_Corp/Plant_1/_informative` |
| Asset `Motor X` | `Acme_Corp/Plant_1/…/Motor_X/_informative` |

> El topic `_informative` es la misma ruta que `_descriptive` con el sufijo cambiado.

---

## 5. Independencia de estados entre tabs

**Objetivo:** Editar `_descriptive` no afecta `_informative` y viceversa.

| Paso | Acción | Resultado esperado |
|---|---|---|
| 1 | Seleccionar un nodo con ambos payloads | Ambos tabs muestran dot verde |
| 2 | Activar edición en `_descriptive`, editar algo | Botones SAVE/PUBLISH visibles |
| 3 | Cambiar a tab `_informative` | Botones desaparecen (infoEditMode = false) |
| 4 | Clic `Edit node` en `_informative` | Botones aparecen para `_informative` |
| 5 | Cambiar a `_descriptive` | Los botones de `_descriptive` siguen activos |

---

## 6. Publish no auto-publica en SAVE

**Objetivo:** `SAVE` solo persiste en DB; `SAVE & PUBLISH` publica en MQTT.

| Paso | Acción | Resultado esperado |
|---|---|---|
| 1 | Seleccionar un Asset con `descriptive_payload` ya publicado | `SYNCED` badge verde |
| 2 | Editar el payload (añadir un campo nuevo) | Badge cambia a `UNSYNCED` |
| 3 | Clic en `SAVE` (sin publicar) | El badge permanece `UNSYNCED` — el payload en MQTT no cambió |
| 4 | Clic en `SAVE & PUBLISH` | Badge vuelve a `SYNCED` |

---

## 7. Verificación de API directa

```bash
# Obtener enterprise con nuevos campos
curl -s http://localhost:8000/enterprises/ | python -m json.tool

# Publicar un site (sustituir IDs reales)
ENTERPRISE_ID="..."
SITE_ID="..."

# Actualizar payload de un site
curl -s -X PATCH http://localhost:8000/enterprises/$ENTERPRISE_ID/sites/$SITE_ID \
  -H "Content-Type: application/json" \
  -d '{"descriptive_payload": {"test": true}, "informative_payload": {"unit": "rpm"}}' \
  | python -m json.tool

# Publicar el site (publica ambos topics)
curl -s -X POST http://localhost:8000/enterprises/$ENTERPRISE_ID/sites/$SITE_ID/publish \
  | python -m json.tool
# Respuesta debe incluir last_published_at con timestamp
```

---

## 8. Resumen de endpoints nuevos

| Método | Endpoint | Descripción |
|---|---|---|
| `POST` | `/enterprises/{id}/publish` | Publica `_descriptive` e `_informative` |
| `POST` | `/enterprises/{eid}/sites/{sid}/publish` | Ídem para Site |
| `POST` | `/sites/{sid}/areas/{aid}/publish` | Ídem para Area |
| `POST` | `/areas/{aid}/lines/{lid}/publish` | Ídem para Line |
| `POST` | `/lines/{lid}/cells/{cid}/publish` | Ídem para Cell |
| `POST` | `/cells/{cid}/assets/{aid}/publish` | Ídem para Asset (+ sync status) |

> Todos los endpoints de publish son tolerantes a fallos MQTT — si el broker no está disponible, devuelven `200` con `last_published_at` actualizado igualmente.

---

## Checklist rápido

- [ ] Árbol colapsable en todos los niveles
- [ ] Enterprise seleccionable en el header
- [ ] Tab `_descriptive` funcional en los 6 niveles
- [ ] Tab `_informative` funcional en los 6 niveles
- [ ] Topics MQTT con formato correcto (mayúsculas preservadas, espacios→`_`)
- [ ] `SAVE` no publica, `SAVE & PUBLISH` sí publica
- [ ] Estados de edición independientes por tab
- [ ] Badge SYNCED/UNSYNCED funciona correctamente en Assets
