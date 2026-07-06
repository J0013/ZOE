# La visión: un sistema que trabaja solo

ZOE no es un chatbot. Un chatbot espera a que le preguntes; ZOE está diseñado para
funcionar como el **turno de noche de la organización**: el producto son los outputs
autónomos (informes, conclusiones, alertas al amanecer), y el chat es solo una puerta
de entrada más.

De ahí que la orquestación tenga una dimensión temporal: los modelos no se eligen
solo por rol, también por **franja horaria**.

| Franja | Qué pasa | Modelos |
|---|---|---|
| **Día — servicio** | Consultas interactivas; los reportes ya están preparados cuando empieza la jornada | Ágiles (ligero/medio) |
| **Noche — digestión** | Si hay backlog sin procesar (reuniones, documentos subidos), ingesta batch al wiki | Medios, en paralelo |
| **Noche — razonamiento** | Con el corpus al día, el modelo más profundo digiere el wiki completo y amanece como informe de dirección | El más grande que quepa en la GPU |

La GPU libre de noche es la única franja donde el modelo grande cabe en hardware
modesto: es el mismo principio local-first, exprimido en el tiempo además de en el
coste. Y el plan no es un simple cron — es un **scheduler consciente de la carga**
(cola de tareas + uso de GPU) que detecta huecos de baja actividad y adelanta trabajo
en ellos.

Estado de esta visión: las piezas de ejecución ya existen (la capa profunda es
`dios.py`, el broker por niveles es `models.py`); el planificador de ritmos es la
tercera pata del broker — hoy tiene registry de modelos + asignación rol→nivel,
la matriz *tipo de tarea × franja × tier autorizado* está en diseño.
