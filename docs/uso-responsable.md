# Política de uso responsable

## Uso previsto

ZOE es una memoria organizacional **interna**: procesa información propia de la
organización que lo despliega (reuniones, actas, documentos de trabajo) para
producir un wiki consultable y informes de dirección, siempre con la fuente citada.

Condición de partida: los participantes de las reuniones procesadas deben estar
informados de que se graban y se tratan. Sin eso, no despliegues ZOE sobre ese
material (ver [privacidad-rgpd.md](privacidad-rgpd.md)).

## Usos no aceptables

- **Decisiones automatizadas sobre personas.** La salida de ZOE es informativa;
  no debe ser la base única de decisiones con efectos legales o significativos
  (contratación, despido, crédito, sanciones). Un humano decide, ZOE documenta.
- **Vigilancia encubierta** de empleados o terceros.
- **Tratar la salida del LLM como hecho verificado.** Cada afirmación lleva su
  locator precisamente para que se compruebe contra la fuente antes de actuar.
- Procesar información de terceros sin base legal para hacerlo.

## Supervisión humana

La supervisión humana no es un aviso en un manual: está integrada en el diseño.

1. **Trazabilidad verificable.** Cada dato del wiki lleva un locator
   `(src-reunion-NN, fecha)`; la fuente inmutable permite comprobar en segundos si
   el sistema dijo la verdad. La verificación mecánica de locators impide que una
   reescritura pierda referencias en silencio.
2. **Fuentes inmutables.** El pipeline nunca modifica el material original; ante
   cualquier duda, el original manda.
3. **Bandeja revisable.** Los documentos subidos pasan por una cola (`/inbox`)
   visible antes y después de procesarse; el log de ingesta
   (`memory/wiki-log.md`) registra qué entró, cuándo y con qué modelos.
4. **Salida legible y editable.** El wiki es markdown plano: un humano puede leer,
   corregir o borrar cualquier página con un editor de texto, sin herramientas
   especiales.
5. **El sistema no actúa sobre el mundo.** Produce texto (wiki, informes); no
   envía correos, no ejecuta acciones, no toma decisiones. El bucle lo cierra
   siempre una persona.

Restricción de diseño para integraciones futuras: si un agente con herramientas
consume esta memoria, todo contenido del wiki debe tratarse como entrada NO
confiable (puede derivar de documentos externos), y cualquier acción con efectos
requiere confirmación humana. Esta restricción no debe relajarse sin re-evaluar
[docs/riesgos.md](riesgos.md).
