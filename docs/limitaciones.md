# Limitaciones conocidas

Lista honesta, mantenida junto al código. Si encuentras una que no está aquí,
abre un issue.

## Del LLM

- **Atribución errónea posible.** Un modelo local pequeño puede atribuir una
  afirmación al tema equivocado (el caso más traicionero — pasajes que no nombran
  su tema — tiene un caso de regresión, pero una regresión no es una garantía).
  Mitigación de diseño: locators + supervisión humana.
- **La calidad depende del modelo configurado.** Con hardware modesto, el tier
  profundo trabaja con modelos de 7-14B; sus informes son un borrador razonado,
  no un análisis infalible (ver [hardware.md](hardware.md)).
- **Prompts optimizados para español.** Funciona en otros idiomas, pero sin tuning.

## Del pipeline

- **Sin OCR.** PDFs escaneados o basados en imagen no se extraen (la reserva
  técnica es docling; no está integrada).
- **El integrador reescribe la página completa.** La verificación de locators actúa
  como red de seguridad contra pérdidas; la edición por diff está en diseño.
- **Búsqueda literal en modo standalone.** `/search` usa FTS5 (prefijos, sin
  sinónimos ni semántica). La búsqueda híbrida BM25+vector está en diseño; en la
  instalación de referencia la aporta el runtime del agente.

## De la plataforma

- **Un solo nodo.** Sin alta disponibilidad ni failover; si la máquina cae, el
  servicio cae (los datos son archivos planos: sobreviven).
- **Sin cifrado en reposo propio.** Wiki e índice son markdown/SQLite planos;
  el cifrado se delega en el disco/OS (BitLocker, LUKS, FileVault).
- **Prototipo.** Sin auditoría de seguridad externa; el hardening existente
  (token, zip-bomb guard, rlimits, prompts anti-injection) está probado pero no
  certificado.
- **El aislamiento depende de que el token no se comparta.** Con SameSite=Strict,
  POST solo-por-header, bind a loopback y allowlist de Host, el navegador del
  operador ya no es vector de entrada; quien tenga el token sigue teniendo la
  puerta.
