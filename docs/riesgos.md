# Evaluación de riesgos

Evaluación para el uso previsto (memoria organizacional interna con supervisión
humana, ver [uso-responsable.md](uso-responsable.md)). Revisar si el uso cambia.

| Riesgo | Impacto | Mitigación en el sistema | Riesgo residual |
|---|---|---|---|
| El LLM afirma algo falso o lo atribuye al tema equivocado | Decisiones mal informadas | Locators verificables en cada dato · caso de regresión anti-atribución · fuentes inmutables · supervisión humana antes de actuar | **Medio-bajo**: verificar el locator antes de usar un dato en una decisión |
| Prompt injection desde un documento subido | Contenido manipulado entra al wiki | Detector de patrones en puerta + bandeja de revisión `data/revisar/` (aprobación manual) · spotlighting con nonce (la fuente va en `<fuente id=...>` que el documento no puede cerrar) · verificación mecánica de locators ilegítimos (un locator fabricado bloquea la escritura de la página) · neutralización de locators presentes en la fuente · normalización del texto (ancho cero, homoglifos, comentarios HTML) · niveles de confianza (las fuentes externas llevan marca `ext` en su locator) · límites de recursos · log de ingesta | **Medio-bajo**: no eliminable al 100%; revisar documentos de origen no confiable antes de aprobarlos |
| Fuga de información sensible | Exposición de datos de la organización | 100% local (cero llamadas externas, verificable en el código) · token en `/upload` y `/search` · sin telemetría | **Bajo-medio**: se desplaza a la seguridad del host (acceso físico, disco sin cifrar, exponer el puerto a internet) |
| Pérdida de conocimiento en una reescritura del wiki | Información borrada en silencio | Verificación mecánica de locators tras cada reescritura · fuentes inmutables (regenerable) | **Bajo** |
| Subida maliciosa (zip-bomb, archivo gigante) | Caída del servicio | Guard anti zip-bomb · rlimits · límite 100 MB por archivo · cola secuencial | **Bajo** |
| Sesgo del modelo en los informes estratégicos | Conclusiones sesgadas presentadas como análisis | Perfil por instancia (contexto correcto) · citas en el informe · el informe es borrador para revisión, no decisión | **Medio**: inherente al LLM; lo absorbe la supervisión humana |
| Dependencia de una sola máquina | Indisponibilidad temporal | Datos en archivos planos (backup trivial) · reconstrucción del índice mecánica | **Bajo**: definir política de backups en despliegues reales |
| Entrega remota de documentos vía navegador del operador (CSRF hacia localhost) | Documento hostil entra al pipeline de ingesta sin acción del usuario | Cookie SameSite=Strict · POST solo con token explícito por header (la cookie no vale) · bind a 127.0.0.1 · allowlist de Host (anti DNS-rebinding) | **Bajo** |

## Clasificación regulatoria (orientativa)

En su uso previsto, ZOE es un sistema de IA de **propósito interno e informativo**:
no toma decisiones automatizadas sobre personas ni opera en los ámbitos de alto
riesgo del Reglamento de IA (empleo, crédito, biometría, etc.). Le aplican
obligaciones de transparencia (los usuarios saben que el contenido lo genera IA —
el propio wiki lo declara con sus locators). **Si un despliegue cambia el uso**
(p. ej. evaluar empleados con él), la clasificación cambia y esta evaluación deja
de valer: re-evaluar antes.

*Esto no es asesoramiento jurídico; para despliegues reales, validar con un
especialista.*
