"""
Dios v1 — capa estratégica superior de ZOE.

Interviene poco, con peso: lee el wiki COMPLETO (la capa razonada; nunca fuentes
brutas) con el rol `dios` (nivel profundo en /modelos) y escribe
`wiki-informe-estrategico.md`: contradicciones, riesgos, oportunidades, action
items huérfanos y recomendaciones de dirección, todo citando páginas del wiki.

Pensado como digestión nocturna (ritmos): en esta máquina el modelo profundo va
lento (CPU parcial) — da igual, es batch. En hardware grande es interactivo.

Uso (desde WSL):
  python3 dios.py                 # run normal con el rol dios (nocturno)
  python3 dios.py --rol cerebro   # mismo informe con un rol/nivel más ligero (pruebas)
  python3 dios.py --dry-run       # solo medir el wiki y estimar contexto

Cron nocturno (cuando toque activar ritmos):
  0 3 * * *  cd /ruta/al/repo && python3 dios.py >> dios.log 2>&1
"""

import argparse
import json
import subprocess
import time
from datetime import date
from pathlib import Path

from models import chat, modelo_de
from ingest_wiki import CONVENCIONES, MEMORY_DIR, COMPOSE_FILE, strip_md_fences

INFORME = "wiki-informe-estrategico.md"
LOGS_DIR = Path(__file__).parent / "data" / "logs"

SYSTEM = CONVENCIONES + """

Ahora actúas como la CAPA ESTRATÉGICA del sistema (baja frecuencia, alto valor).
Recibes el wiki completo — la capa razonada del conocimiento de la organización —
y devuelves un informe de dirección. No resumas por resumir: señala lo que un
buen jefe de gabinete señalaría. Cita siempre la página wiki de origen con
[[wiki-nombre]] (y conserva los locators (src-*, fecha) cuando cites hechos).
Los locators con marca ext provienen de fuentes externas a la organización;
pondera su fiabilidad en consecuencia y señálalo si un hallazgo clave depende
solo de ellas."""


def leer_wiki() -> tuple[str, list[str]]:
    parts, names = [], []
    for p in sorted(MEMORY_DIR.glob("wiki-*.md")):
        if p.name in ("wiki-log.md", INFORME):  # el log es ruido; el informe previo se pasa aparte
            continue
        parts.append(f'<pagina filename="{p.name}">\n{p.read_text(encoding="utf-8")}\n</pagina>')
        names.append(p.name)
    return "\n\n".join(parts), names


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rol", default="dios", help="rol del broker a usar (default: dios)")
    ap.add_argument("--dry-run", action="store_true", help="solo medir tamaño del wiki")
    args = ap.parse_args()

    wiki, names = leer_wiki()
    est_tokens = len(wiki) // 3  # estimación grosera para es/markdown
    print(f"wiki: {len(names)} páginas, {len(wiki)} chars (~{est_tokens} tokens) "
          f"| rol {args.rol} -> {modelo_de(args.rol)}", flush=True)
    if args.dry_run:
        return
    num_ctx = 49152
    if est_tokens > num_ctx - 8000:
        raise SystemExit(f"el wiki (~{est_tokens} tok) no cabe cómodo en {num_ctx} de contexto; "
                         "toca consolidar páginas antes de correr a Dios")

    hoy = date.today().isoformat()
    previo = (MEMORY_DIR / INFORME)
    previo_txt = previo.read_text(encoding="utf-8") if previo.exists() else "(no hay informe previo)"
    user = f"""FECHA DE HOY: {hoy}

WIKI COMPLETO DE LA ORGANIZACIÓN:

{wiki}

---

INFORME ESTRATÉGICO ANTERIOR (para detectar evolución; puede estar obsoleto):

{previo_txt}

---

Escribe el nuevo informe estratégico. Estructura obligatoria (markdown, conciso,
máximo ~120 líneas, cada afirmación con su [[wiki-página]] de origen):

# Informe estratégico — {hoy}
## Estado general (5-8 líneas: dónde está la organización hoy)
## Contradicciones detectadas (afirmaciones del wiki que chocan entre sí; cita ambas páginas; si no hay, dilo)
## Riesgos (ordenados por gravedad, con el porqué)
## Oportunidades (concretas, accionables)
## Action items huérfanos o vencidos (pendientes sin dueño claro o cuya fecha ya pasó a día de hoy)
## Recomendaciones de dirección (máximo 5, priorizadas)

SOLO el markdown del informe, sin comentarios."""

    t0 = time.time()
    out = strip_md_fences(chat(args.rol, SYSTEM, user, num_ctx=num_ctx, num_predict=4096,
                               timeout=5400))
    dur = round(time.time() - t0)
    if len(out) < 200 or not out.lstrip().startswith("#"):
        raise SystemExit(f"salida sospechosa ({len(out)} chars); no escribo el informe")

    (MEMORY_DIR / INFORME).write_text(out.rstrip() + "\n", encoding="utf-8")
    with open(MEMORY_DIR / "wiki-log.md", "a", encoding="utf-8") as f:
        f.write(f"- {hoy} (dios): informe estratégico regenerado ({len(names)} páginas leídas)\n")
    # trazabilidad (contrato light: execution_result)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    (LOGS_DIR / f"dios-{hoy}.json").write_text(json.dumps({
        "type": "execution_result", "source": "dios", "created_at": hoy,
        "rol": args.rol, "model": modelo_de(args.rol), "paginas_leidas": len(names),
        "chars_in": len(wiki), "chars_out": len(out), "duracion_s": dur, "success": True,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"escrito {INFORME} ({len(out)} chars) en {dur}s", flush=True)

    if COMPOSE_FILE:
        print("Reindexando memory...", flush=True)
        subprocess.run(["docker", "compose", "-f", COMPOSE_FILE, "exec", "-T", "openclaw-gateway",
                        "node", "dist/index.js", "memory", "index"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)
    print("Listo.", flush=True)


if __name__ == "__main__":
    main()
