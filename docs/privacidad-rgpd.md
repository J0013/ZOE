# Privacidad y RGPD en despliegues reales

ZOE es **software self-hosted, no un servicio**: no hay servidor del autor, no hay
cuenta, no hay telemetría. Eso simplifica mucho el cumplimiento — pero no lo
elimina, porque las reuniones y documentos de una empresa contienen datos
personales (de empleados, clientes, proveedores).

## Reparto de roles

- **La organización que despliega ZOE es la responsable del tratamiento.**
- No hay encargado del tratamiento externo: los modelos son de Ollama y corren en
  la misma máquina. **No hay transferencias internacionales** — no sale un solo
  byte, y es verificable leyendo el código.

## Antes de desplegar

1. **Informar a los afectados** (arts. 13/14 RGPD): los participantes de reuniones
   grabadas deben saber que se graban y para qué se tratan.
2. **Base jurídica**: para memoria interna de trabajo, lo habitual es interés
   legítimo (art. 6.1.f) con su ponderación documentada. Con datos de categorías
   especiales, pedir criterio experto antes.
3. **Minimización**: sube lo que aporte a la memoria organizacional, no todo lo
   que exista. `data/perfil.txt` define el dominio; el corpus lo eliges tú.
4. **Retención**: define cuánto tiempo se conservan las fuentes.

## Ejercicio de derechos

La arquitectura de fuentes inmutables + wiki derivado hace los derechos ejercibles
de forma mecánica:

- **Acceso**: `/search` por el nombre de la persona localiza sus menciones (con
  locator a la fuente exacta).
- **Rectificación / supresión**: se corrige o borra la **fuente** en `memory/` y se
  re-ingiere; el wiki se regenera sin ese contenido. El log de ingesta
  (`memory/wiki-log.md`) sirve de registro básico de tratamientos.

## Medidas de seguridad (art. 32)

Incluidas: token de acceso en los endpoints sensibles, procesamiento 100% local,
guards de recursos en la ingesta. A añadir en un despliegue real: cifrado de disco
(los datos en reposo son archivos planos), backups cifrados, control de acceso al
host, y **no exponer el puerto 8900 a internet** sin TLS y autenticación adicional
delante. Para correr el backend como servicio con usuario dedicado y sandboxing
(NoNewPrivileges, ProtectSystem, permisos 700/600 en `data/` y `memory/`), usa la
unidad de referencia [`deploy/zoe.service.example`](../deploy/zoe.service.example).

---

*Este documento orienta, no sustituye asesoramiento jurídico. Para un despliegue
con datos reales, pásalo por tu DPO o abogado.*
