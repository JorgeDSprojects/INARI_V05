# INARI_V05

**Un sistema SCADA industrial construido como una arquitectura Unified Namespace (UNS)**: conecta máquinas, sensores y PLCs de una planta con un histórico completo, una capa de datos normalizada y limpia, y paneles de visualización en tiempo real — todo como servicios independientes que se despliegan y escalan por separado.

---

## Para quien evalúa el perfil (RRHH / no técnico)

Este proyecto es un sistema completo de monitorización industrial, del tipo que se usa en fábricas y plantas de energía para saber en todo momento qué está pasando con sus máquinas: temperaturas, velocidades, alarmas, consumos.

Lo que demuestra, más allá del dominio industrial concreto:

- **Diseño de sistemas distribuidos de principio a fin**: no es una app, son cuatro servicios independientes que se comunican entre sí, cada uno con su propia base de datos, su propio ciclo de vida, y la capacidad de arrancar solo o junto a los demás.
- **Ingeniería de datos real**: los datos crudos que llegan de las máquinas se transforman en varias capas hasta convertirse en información con significado (nombre, unidad, umbrales, versionado histórico) — el mismo patrón ("bronze → silver") que se usa en proyectos de datos a gran escala.
- **Backend, frontend, bases de datos e infraestructura**, todo en el mismo proyecto: APIs en Python (FastAPI), interfaces en React, bases de datos relacionales y de series temporales (PostgreSQL/TimescaleDB), mensajería en tiempo real (MQTT), todo empaquetado y orquestado con Docker.
- **Disciplina de ingeniería**: cada funcionalidad nueva se documenta primero (qué se va a construir y por qué), se implementa con pruebas automáticas, y se revisa antes de darse por terminada — no es código improvisado, hay un proceso detrás.
- **Capacidad de llevar un proyecto real hasta el final**: desde la primera línea de código hasta un sistema que arranca con un solo comando y funciona de verdad.

Si buscas a alguien capaz de diseñar, construir y mantener un sistema con estas piezas moviéndose a la vez, este proyecto es una muestra directa de ese trabajo.

---

## Para perfil técnico

### Arquitectura

Cuatro servicios independientes, cada uno con su propio `docker-compose.yml`, orquestados juntos por el `docker-compose.yml` de la raíz (que simplemente los incluye bajo una red Docker compartida):

```
                    ┌──────────────┐
   Sensores/PLCs →  │  UNS_MANAGER │  MQTT (EMQX) + Node-RED + API/panel propios
                    └──────┬───────┘
                           │ mensajes MQTT en crudo ("bronze")
                           ▼
                    ┌──────────────┐
                    │ UNS_HISTORIAN│  histórico completo, sin filtrar (TimescaleDB)
                    └──────┬───────┘
                           │
                           ▼
                    ┌──────────────┐
                    │  UNS_SILVER  │  normaliza: catálogo de señales versionado,
                    └──────────────┘  valores tipados, log de eventos/alarmas

                    ┌──────────────┐
                    │ UNS_DASHBOARD│  paneles con gráficas en tiempo real e históricas
                    └──────────────┘  (lee de UNS_HISTORIAN + su propia BBDD)
```

| Servicio | Responsabilidad | Stack | Puertos (host) |
|---|---|---|---|
| **UNS_MANAGER** | Punto de entrada: recibe MQTT de las máquinas, modela la jerarquía de activos (árbol ISA-95), automatización con Node-RED | EMQX (broker MQTT 5.0), Node-RED, FastAPI, React, PostgreSQL | Postgres 5433, MQTT 1883, panel EMQX 18083, API 8000, frontend 3001, Node-RED 1880 |
| **UNS_HISTORIAN** | Archiva **todos** los mensajes MQTT tal cual llegan — el histórico bruto, sin filtrar ("bronze") | TimescaleDB, pgAdmin, ingestor MQTT propio (deduplicación, buffer con flush por lotes, reconexión resiliente) | Postgres 5434, pgAdmin 5051 |
| **UNS_SILVER** | Transforma el histórico bruto en datos con significado: catálogo de señales versionado (con umbrales e histórico de cambios), lecturas tipadas, agregados continuos (1m/1h), log de eventos | TimescaleDB (continuous aggregates), pgAdmin, normalizador bronze→silver | Postgres 5436 |
| **UNS_DASHBOARD** | Paneles visuales: gráficas en tiempo real e históricas, CRUD completo de dashboards/gráficas, publicación de paneles | FastAPI + SQLAlchemy async, React + Vite + TypeScript, PostgreSQL, Redis (puente MQTT→Redis para datos en vivo de baja latencia) | Postgres 5435, backend 8001, frontend 3002 |

### Decisiones de diseño destacables

- **Patrón medallón (bronze → silver)** aplicado a series temporales industriales: `UNS_HISTORIAN` guarda el dato crudo sin ninguna interpretación (para no perder nunca información), `UNS_SILVER` es la única capa que decide qué significa cada señal — y lo hace con **versionado real**: cambiar la unidad o los umbrales de una señal no sobrescribe el histórico, lo cierra (`effective_until`) y abre una versión nueva.
- **Agregados continuos de TimescaleDB** (`silver_readings_1m`/`_1h`) para que consultar un rango histórico amplio no signifique escanear millones de filas crudas.
- **Redes Docker segmentadas por servicio**, con una red compartida (`uns_manager_net`) solo para lo que de verdad necesita cruzar servicios — cada `docker-compose.yml` sigue siendo válido de forma independiente.
- **Ingestor MQTT con deduplicación y buffer acotado**: evita duplicados en reconexiones y no deja crecer la memoria sin límite si Postgres se queda temporalmente inaccesible.

### Cómo arrancarlo

```bash
docker compose up -d        # los cuatro servicios juntos, desde la raíz
```

Cada servicio también arranca solo, desde su propia carpeta:

```bash
cd UNS_DASHBOARD && docker compose up -d
```

### Documentación

- **Specs de diseño y planes de implementación**, por funcionalidad: `<servicio>/docs/superpowers/specs/` y `<servicio>/docs/superpowers/plans/`
- **Reglas de desarrollo del repositorio**: [`AGENTS.md`](AGENTS.md)
- **Guías de verificación paso a paso**: [`manual/`](manual/) (español e inglés)
- **README propio de cada servicio**, con detalles de arranque y operación: `UNS_MANAGER/`, `UNS_HISTORIAN/README.md`, `UNS_SILVER/README.md`, `UNS_DASHBOARD/README.md`
