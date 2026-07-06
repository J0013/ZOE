# Hardware: qué hace falta para el 100%

El sistema escala con la máquina que tenga debajo — el broker asigna a cada rol el
mejor modelo que quepa, así que el mismo código rinde en un portátil y en una
workstation. Orientación:

| Nivel | Máquina | Qué da |
|---|---|---|
| **Demo** | CPU moderna, 16 GB RAM, sin GPU | Endpoints y búsqueda completos; ingesta lenta con modelos pequeños (3-4B) |
| **Funcional** | GPU de 12-16 GB VRAM (RTX 4070/5070), 32 GB RAM | Tiers ligero/medio fluidos (7-14B Q4); noche de razonamiento con un 14B; ~2 peticiones LLM en paralelo |
| **Óptimo (100%)** | 64-128 GB de memoria unificada (Mac Studio, Ryzen AI Max) o GPU ≥32 GB (RTX 5090) | Los tres tiers de verdad: día con varios modelos medios en paralelo, noche de razonamiento con un 70B Q4 sobre el wiki completo, operación 24/7 |

Dos variables mandan sobre todas las demás:

- **Memoria**: el tier profundo está limitado por la VRAM/memoria unificada
  disponible — un 70B Q4 ronda los 40 GB solo de pesos, y el paralelismo diurno
  necesita hueco adicional para los KV caches de cada petición concurrente.
- **Consumo sostenido**: la máquina trabaja de noche, todos los días. Un equipo de
  memoria unificada a 60-100 W frente a una torre con GPU dedicada a 400+ W se nota
  en la factura y en el ruido — para un aparato que vive encendido 24/7 en una
  oficina, es criterio de diseño, no un detalle.

Por eso el candidato ideal para una instalación seria es un equipo compacto de
memoria unificada dedicado en exclusiva: silencioso, eficiente y con memoria de
sobra para que la noche de razonamiento use un modelo que en una GPU de consumo
no cabe.
