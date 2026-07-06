# Registro de versiones de modelos

Qué modelo hizo qué es parte de la trazabilidad: un wiki generado con un modelo
de 4B no merece la misma confianza que uno generado con un 70B.

## Dónde vive la configuración

`data/modelos.json` (sobre los defaults de `models.py`): define el router, los
tres niveles (ligero/medio/profundo → modelo + hilos) y el mapeo rol → nivel.
Editable en caliente desde la página `/modelos` — aplica a la siguiente ingesta
sin reiniciar.

```json
{
  "router": "gemma4:e4b",
  "niveles": {
    "ligero":   { "model": "gemma4:e4b",   "hilos": 2 },
    "medio":    { "model": "qwen2.5:14b",  "hilos": 2 },
    "profundo": { "model": "qwen2.5:14b",  "hilos": 1 }
  },
  "roles": { "preprocesador": "ligero", "clasificador": "ligero", "integrador": "medio" }
}
```

## Registro por ingesta

Cada entrada procesada anota en `memory/wiki-log.md` la fecha, la fuente, las
páginas tocadas y **los modelos usados por rol** en ese momento:

```text
- 2026-02-02 (src-reunion-02): pipeline local; modelos: preprocesador=gemma4:e4b,
  clasificador=gemma4:e4b, integrador=qwen2.5:14b; paginas: wiki-proyecto-campana.md
```

Así, ante cualquier página dudosa, se puede reconstruir qué modelo la escribió.

## Buenas prácticas

- **Pin de tags concretos** (`gemma4:e4b`, `qwen2.5:14b-instruct-q4_K_M`), nunca
  `:latest`: Ollama puede resolver `:latest` a pesos distintos en máquinas o fechas
  distintas, y la reproducibilidad se pierde.
- Al cambiar un modelo de nivel, el log lo refleja solo a partir de ese momento;
  si el cambio es relevante (p. ej. subir el tier profundo), considera re-ingerir
  el corpus para homogeneizar la calidad del wiki.
