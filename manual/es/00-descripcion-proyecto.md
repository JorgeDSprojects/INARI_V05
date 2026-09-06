# Descripción del proyecto: INARI_V05

## En una frase

INARI_V05 es un sistema que conecta las máquinas de una planta industrial con las personas que necesitan entenderlas — recoge lo que las máquinas van diciendo (sensores, alarmas, estados), lo guarda de forma ordenada, y deja que cualquiera —desde un operario hasta un ingeniero— lo consulte, lo visualice o incluso se lo pida en lenguaje natural a un asistente de IA.

## Para quien no es técnico

Imagina una fábrica con decenas de máquinas: motores, generadores, sensores de temperatura, presión, vibración... Cada una está constantemente "hablando" — diciendo su estado, su velocidad, si algo va mal. El problema de siempre en una planta es que esa información está dispersa: cada máquina en su propio sistema, con su propio formato, difícil de juntar y de consultar.

INARI_V05 resuelve esto en cuatro pasos:

1. **Escucha** — todo lo que las máquinas dicen llega a un único canal central (como una radio que todas sintonizan), así nada se pierde y todo queda en un solo sitio.
2. **Guarda** — ese torrente de mensajes se archiva de forma ordenada, como un histórico al que se puede volver meses después para ver qué pasó un día concreto.
3. **Limpia y traduce** — los datos crudos (números sueltos, códigos técnicos) se convierten en algo con significado: no solo "el valor es 1450", sino "la velocidad media del generador T01 es 1450 RPM", con sus unidades, su descripción y su histórico de cambios.
4. **Se deja preguntar** — sobre esos datos ya limpios se puede montar un panel visual (dashboards con gráficas), y desde hace poco, también se le puede simplemente *pedir* a un asistente de IA: "créame una gráfica con la velocidad del generador" — y el asistente busca la señal correcta, la añade al panel, y si no está seguro de cuál es, te ofrece opciones para elegir en vez de adivinar.

Todo el sistema corre en la propia red de la planta (nada sale a internet salvo que se configure explícitamente), organizado en piezas independientes que se pueden apagar, actualizar o sustituir una a una sin tirar abajo el resto.

## Arquitectura para quien sí es técnico

El sistema se organiza en **seis módulos independientes**, cada uno con su propio `docker-compose.yml`, que pueden arrancar solos o todos juntos (el `docker-compose.yml` de la raíz simplemente los incluye todos bajo una red compartida, `uns_manager_net`). Cada módulo es una carpeta con su propio nombre (`UNS_MANAGER`, `UNS_HISTORIAN`, etc.).

```
                    ┌──────────────┐
   Sensores/PLCs →  │  UNS_MANAGER │ → MQTT (EMQX) + Node-RED
                    └──────┬───────┘
                           │ mensajes MQTT en crudo ("bronze")
                           ▼
                    ┌──────────────┐
                    │ UNS_HISTORIAN│  histórico completo, sin filtrar
                    └──────┬───────┘
                           │
                           ▼
                    ┌──────────────┐
                    │  UNS_SILVER  │  normaliza: catálogo de señales,
                    └──────┬───────┘  valores tipados, alarmas
                           │
                           ▼
                    ┌──────────────┐
                    │   UNS_MCP    │  API de solo lectura sobre lo anterior
                    └──────┬───────┘
                           │
                           ▼
                    ┌──────────────┐      ┌────────────┐
                    │ UNS_DASHBOARD│ ───→ │ UNS_OLLAMA │ (LLM local)
                    │ (paneles+chat)│      └────────────┘
                    └──────────────┘
```

| Módulo | Para qué sirve | Tecnología | Puertos (host) |
|---|---|---|---|
| **UNS_MANAGER** | Punto de entrada: recibe los mensajes MQTT de las máquinas, permite programar flujos de automatización (Node-RED) y expone una API/panel propios | EMQX (broker MQTT), Node-RED, FastAPI, React, Postgres | Postgres 5433, MQTT 1883, panel EMQX 18083, API 8000, frontend 3001, Node-RED 1880 |
| **UNS_HISTORIAN** | Archiva **todos** los mensajes MQTT tal cual llegan, sin filtrar — el histórico bruto ("bronze") | TimescaleDB (Postgres + series temporales), pgAdmin, un ingestor MQTT propio | Postgres 5434, pgAdmin 5051 |
| **UNS_SILVER** | Transforma ese histórico bruto en datos con significado: catálogo de señales (nombre, unidad, umbrales, versionado), valores ya tipados, log de eventos/alarmas | TimescaleDB, pgAdmin, un normalizador bronze→silver | Postgres 5436 |
| **UNS_MCP** | Expone lo anterior por HTTP, de solo lectura, mediante el protocolo MCP (Model Context Protocol) — pensado para que un LLM/agente lo consulte como una herramienta más | Servidor MCP en Python | 8095 |
| **UNS_DASHBOARD** | Los paneles visuales (dashboards con gráficas en tiempo real e históricas) y, la pieza más reciente, un **chat con IA** que crea y edita esos paneles hablando en lenguaje natural | FastAPI + SQLAlchemy async, React + Vite + TypeScript, Postgres, Redis (puente MQTT→Redis para baja latencia) | Postgres 5435, backend 8001, frontend 3002 |
| **UNS_OLLAMA** | Modelo de lenguaje (LLM) corriendo en local, en la propia máquina/red de la planta — nada de datos sale fuera | Ollama, con GPU si está disponible | 11434 |

### El chat con IA, en más detalle

Es la pieza construida más recientemente. Vive dentro de `UNS_DASHBOARD` y funciona así:

- El usuario escribe algo como *"añade una gráfica con el RPM del generador"* en un panel de chat dentro del editor de un dashboard.
- El sistema envía ese mensaje al modelo de lenguaje (`UNS_OLLAMA`, en local), junto con un conjunto de **herramientas** que el modelo puede usar: leer datos reales (a través de `UNS_MCP`, de solo lectura) y escribir cambios en el dashboard (crear/editar/borrar gráficas, publicar — siempre sobre borradores, nunca sobre un dashboard ya publicado).
- Si el modelo no está seguro de qué señal es la correcta, no adivina: puede ofrecer varias opciones como botones para que el usuario elija con un clic.
- Diseñado para poder cambiar de proveedor de LLM en el futuro (local con Ollama, o uno externo como OpenAI/Claude/OpenRouter) sin rediseñar nada — hoy solo Ollama está implementado.
- Si no hay ningún modelo configurado o disponible, el chat simplemente se desactiva (el cuadro de texto no aparece) — nunca da error, nunca rompe el resto del panel.

## Cómo verlo funcionando

Con Docker y Docker Compose instalados, desde la raíz del repositorio:

```bash
docker compose up -d
```

Esto levanta los seis módulos juntos. Cada uno también puede arrancarse por separado desde su propia carpeta (`cd UNS_DASHBOARD && docker compose up -d`, etc.) para trabajar en uno sin tocar los demás.

En `manual/es/` (esta misma carpeta) hay guías paso a paso para comprobar partes concretas del sistema — por ejemplo, `01-verificar-guardado-historian-pgadmin.md` para confirmar que el histórico se está guardando, o `02-verificar-chat-agent-dashboard.md` para probar el chat de principio a fin.

## Dónde está la documentación técnica

- **Specs de diseño** (arquitectura, decisiones): `<módulo>/docs/superpowers/specs/`
- **Planes de implementación** (tarea a tarea): `<módulo>/docs/superpowers/plans/`
- **Reglas de desarrollo del repositorio**: `AGENTS.md`, en la raíz

Cada módulo mantiene su propia documentación bajo su carpeta — no hay un `documents/` ni un `Plan/` centralizado como en versiones muy tempranas del proyecto; cada uno vive junto al código al que describe.
