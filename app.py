"""
ZOE mini-backend: expone la memoria del sistema (markdown + indice SQLite FTS5)
para que una UI web pueda guardar y recuperar texto.

Local-first. Sin cloud. El razonamiento (Ollama) NO interviene aqui: solo guardar/recuperar.

Latencia: /search consulta el FTS5 del indice directamente en read-only (~ms),
sin pagar el boot del CLI del runtime. Si se usa el runtime OpenClaw en contenedor
(opcional, ver ZOE_COMPOSE_FILE), la indexacion tras /ingest se lanza en background
(Popen, no bloquea la request).
"""

import json
import os
import re
import resource
import secrets
import shutil
import sqlite3
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, File, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel

# --- Configuracion por entorno (ver .env.example; todo local, single-machine) ---
# Compose del runtime OpenClaw (opcional). Vacio = sin contenedor: la indexacion
# background se desactiva y puedes indexar con examples/build_demo_index.py
COMPOSE_FILE = os.environ.get("ZOE_COMPOSE_FILE", "")
SERVICE = "openclaw-gateway"
# Directorio donde caen los .md de la memoria/wiki
MEMORY_DIR = os.environ.get("ZOE_MEMORY_DIR", "./memory")
# Indice SQLite (el backend lo lee en read-only: conteo de chunks y busqueda FTS5)
DB_PATH = os.environ.get("ZOE_DB_PATH", "./data/index.sqlite")
# En la tabla chunks el path se guarda relativo: "memory/<archivo>.md"
CHUNK_PREFIX = "memory/"

SEARCH_MAX_RESULTS = 20  # acota la cola
# ponytail: score = -bm25 (mas alto = mas relevante), escala distinta a la del motor
# (0.44-0.56). Sin embeddings tampoco habia umbral util (verificado 2026-07-02):
# lo que funciona es el RANKING. El filtrado absoluto llegara con el TODO(vector).

app = FastAPI(title="ZOE memory backend")
# CORS cerrado por defecto (same-origin). Solo si una UI corre en otro origen:
# ZOE_CORS_ORIGINS="https://ui.ejemplo.com,http://localhost:3000"
_cors = [o.strip() for o in os.environ.get("ZOE_CORS_ORIGINS", "").split(",") if o.strip()]
if _cors:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# Anti DNS-rebinding: un dominio hostil que resuelva a 127.0.0.1 llega con su
# Host original; solo atendemos los nuestros. Hostnames extra (p. ej. Tailscale)
# via ZOE_ALLOWED_HOSTS="mi-maquina.tail.ts.net:8900" (coma-separado).
_ALLOWED_HOSTS = {"localhost:8900", "127.0.0.1:8900"} | {
    h.strip() for h in os.environ.get("ZOE_ALLOWED_HOSTS", "").split(",") if h.strip()}


@app.middleware("http")
async def _host_guard(request: Request, call_next):
    if request.headers.get("host", "") not in _ALLOWED_HOSTS:
        return JSONResponse(status_code=403, content={"ok": False, "error": "host no permitido"})
    return await call_next(request)


class IngestBody(BaseModel):
    text: str
    source: str | None = None
    title: str | None = None


def _err(msg: str, status: int = 500):
    return JSONResponse(status_code=status, content={"ok": False, "error": msg})


_index_proc: subprocess.Popen | None = None


def _kick_background_index():
    """Lanza `memory index` en el contenedor SIN bloquear (el boot del CLI es lento).
    Si ya hay una indexacion en curso, no lanza otra."""
    global _index_proc
    if not COMPOSE_FILE:
        return "disabled"  # sin runtime OpenClaw: indexar con examples/build_demo_index.py
    if _index_proc is not None and _index_proc.poll() is None:
        return "already-running"
    try:
        _index_proc = subprocess.Popen(
            ["docker", "compose", "-f", COMPOSE_FILE, "exec", "-T", SERVICE,
             "node", "dist/index.js", "memory", "index"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        return "started"
    except FileNotFoundError:
        return "docker-not-found"


def _slugify(s: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s.lower()).strip("-")
    return (s or "nota")[:40]


def _ro_conn():
    return sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)


def _count_chunks(rel_path: str):
    """Cuenta chunks del archivo recien indexado. None si no se puede leer el store."""
    try:
        con = _ro_conn()
        try:
            return con.execute(
                "SELECT count(*) FROM chunks WHERE path = ?", (rel_path,)
            ).fetchone()[0]
        finally:
            con.close()
    except Exception:
        return None


def _fts_query(q: str) -> str:
    """Query de usuario -> sintaxis FTS5 segura: tokens entrecomillados con * (prefijo)
    unidos por OR. El prefijo cubre plurales/derivados ("kiwi" -> "kiwis") porque FTS5
    no hace stemming; BM25 ordena y OR prioriza recall como el motor."""
    tokens = re.findall(r"\w+", q, re.UNICODE)
    return " OR ".join(f'"{t}"*' for t in tokens)


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/ingest")
def ingest(body: IngestBody, request: Request):
    if not _auth_token(request):
        return _err("token invalido", 403)
    if not body.text.strip():
        return _err("text vacio", 400)

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    slug = _slugify(body.title or body.source or "nota")
    filename = f"{ts}-{slug}.md"
    host_path = os.path.join(MEMORY_DIR, filename)

    content = (f"# {body.title}\n\n" if body.title else "") + body.text.rstrip() + "\n"
    try:
        os.makedirs(MEMORY_DIR, exist_ok=True)
        with open(host_path, "w", encoding="utf-8") as f:
            f.write(content)
    except OSError as e:
        return _err(f"no se pudo escribir el .md: {e}")

    # Indexacion en background: la request vuelve en ms y la nota es buscable
    # cuando el CLI termina (~25s). Antes: lazy sync-on-search (aparecia en la
    # 2a busqueda del motor); ahora /search lee el FTS directo y no dispara sync,
    # asi que la disparamos nosotros aqui.
    indexing = _kick_background_index()
    chunks = _count_chunks(CHUNK_PREFIX + filename)  # 0 hasta que termine el index
    return {"ok": True, "stored_as": filename, "chunks_indexed": chunks,
            "indexing": f"background-{indexing}"}


@app.get("/search")
def search(q: str, request: Request):
    if not _auth_token(request):
        return _err("token invalido", 403)
    if not q.strip():
        return _err("query (q) vacio", 400)
    match = _fts_query(q)
    if not match:
        return _err("query sin tokens buscables", 400)
    try:
        con = _ro_conn()
        try:
            rows = con.execute(
                "SELECT snippet(chunks_fts, 0, '', '', '…', 24), bm25(chunks_fts), path"
                " FROM chunks_fts WHERE chunks_fts MATCH ?"
                " ORDER BY bm25(chunks_fts) LIMIT ?",
                (match, SEARCH_MAX_RESULTS),
            ).fetchall()
        finally:
            con.close()
    except sqlite3.Error as e:
        return _err(f"error consultando el indice: {e}")

    results = [
        {"text": text, "score": round(-bm, 3), "source": path}
        for (text, bm, path) in rows
    ]
    return {"ok": True, "query": q, "results": results}

# --- Subida de documentos + bandeja de ingesta automatica -------------------
# Flujo: POST /upload (o el formulario GET /subir) deja el archivo en data/inbox/;
# un worker secuencial (la GPU no admite dos ingestas a la vez) lo pasa por
# ingest_wiki.py --file y lo mueve a data/hecho/ o data/error/ (log por archivo).

BASE_DIR = Path(__file__).parent
INBOX = BASE_DIR / "data" / "inbox"
HECHO = BASE_DIR / "data" / "hecho"
ERROR = BASE_DIR / "data" / "error"
# Cuarentena del detector de inyeccion: el archivo espera aprobacion humana aqui,
# con un <nombre>.motivo.txt al lado. Aprobar = moverlo de vuelta a data/inbox/
# (el worker ve su .motivo.txt, se salta el detector esa vez y borra el motivo).
REVISAR = BASE_DIR / "data" / "revisar"
INGEST_LOGS = BASE_DIR / "data" / "logs"
TOKEN_FILE = BASE_DIR / "data" / "upload_token.txt"
MAX_UPLOAD_BYTES = 100 * 1024 * 1024  # 100 MB por archivo
# Allowlist en la puerta: solo formatos que la ingesta sabe tratar. Todo lo demas
# (.exe, .zip, .html...) se rechaza antes de tocar disco.
EXTENSIONES_PERMITIDAS = {".pdf", ".docx", ".xlsx", ".pptx", ".txt", ".md", ".csv"}

for d in (INBOX, HECHO, ERROR, REVISAR, INGEST_LOGS):
    d.mkdir(parents=True, exist_ok=True)
if not TOKEN_FILE.exists():
    TOKEN_FILE.touch(mode=0o600)  # solo el dueño: el token no es legible por otros usuarios
    TOKEN_FILE.write_text(secrets.token_urlsafe(24), encoding="utf-8")
TOKEN_FILE.chmod(0o600)  # repara instalaciones previas que lo crearon con 644
UPLOAD_TOKEN = TOKEN_FILE.read_text(encoding="utf-8").strip()


def _token_valido(candidato: str) -> bool:
    """compare_digest peta con no-ASCII (uvicorn decodifica headers como latin-1);
    un token hostil debe dar 403 limpio, nunca 500."""
    return bool(candidato) and candidato.isascii() \
        and secrets.compare_digest(candidato, UPLOAD_TOKEN)


def _header_token(request: Request) -> str:
    """Token explicito por header: Authorization: Bearer o X-Token. Nunca por
    query string (acabaria en access logs, historial y Referer)."""
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return request.headers.get("x-token") or ""


def _auth_token(request: Request) -> bool:
    """Auth de la API y de TODOS los POST: solo token por header. La cookie NO
    vale aqui: un form-POST cross-site desde una web hostil viajaria con la
    cookie puesta (CSRF hacia localhost); el header solo lo pone nuestro JS o
    un cliente deliberado."""
    return _token_valido(_header_token(request))


def _auth_page(request: Request) -> bool:
    """Auth de los GET de paginas (/subir, /modelos, /inbox, /token-propio):
    cookie de sesion o token por header."""
    if _auth_token(request):
        return True
    return _token_valido(request.cookies.get("zoe_token") or "")


def _page_auth(request: Request):
    """Bootstrap de paginas HTML. El query token se acepta SOLO aqui y una vez
    (el bookmark del movil): se canjea por cookie y se redirige a la URL limpia,
    para que el token no viva en la barra de direcciones ni en el historial.
    Devuelve una Response que corta la peticion, o None si ya viene autenticada."""
    if _auth_page(request):
        return None
    if _token_valido(request.query_params.get("token", "")):
        resp = RedirectResponse(request.url.path, status_code=303)
        # Strict: la cookie no viaja en NINGUNA peticion iniciada por otro sitio.
        # secure=False: despliegue local por http; detras de TLS, activar secure
        resp.set_cookie("zoe_token", UPLOAD_TOKEN, httponly=True, samesite="strict")
        return resp
    return _err("token invalido", 403)


def _safe_name(original: str) -> str:
    stem = _slugify(Path(original).stem)
    ext = re.sub(r"[^a-zA-Z0-9.]", "", Path(original).suffix.lower())
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{ts}-{stem}{ext}"


def _ingest_rlimits():
    """Limites duros para el subproceso de ingesta: un archivo hostil que
    desboque un parser (pdf/docx malformado) muere aqui, no tumba la maquina."""
    resource.setrlimit(resource.RLIMIT_AS, (4 * 2**30, 4 * 2**30))   # 4 GB memoria virtual
    resource.setrlimit(resource.RLIMIT_CPU, (600, 600))              # 10 min de CPU (no cuenta la espera a Ollama)


def _worker():
    """Procesa la bandeja en serie, para siempre. Un archivo cada vez.
    El detector de inyeccion corre DENTRO del subproceso de ingesta (rlimits,
    extraccion unica): exit 3 = sospechoso -> cuarentena en data/revisar/ con su
    .motivo.txt. Aprobar = devolver el archivo a data/inbox/; mientras su
    .motivo.txt siga en revisar/, esa pasada va con --sin-detector."""
    while True:
        pendientes = sorted(p for p in INBOX.iterdir() if p.is_file())
        if not pendientes:
            time.sleep(5)
            continue
        f = pendientes[0]
        log = INGEST_LOGS / (f.name + ".log")
        motivo = REVISAR / (f.name + ".motivo.txt")
        aprobado = motivo.exists()  # un humano lo devolvio a inbox
        cmd = ["python3", str(BASE_DIR / "ingest_wiki.py"), "--file", str(f)]
        if aprobado:
            cmd.append("--sin-detector")
        try:
            with open(log, "w", encoding="utf-8") as lf:
                r = subprocess.run(cmd, stdout=lf, stderr=subprocess.STDOUT,
                                   timeout=3600, cwd=BASE_DIR, preexec_fn=_ingest_rlimits)
            if r.returncode == 3:  # detector: a cuarentena, no es un error
                linea = next((l for l in log.read_text(encoding="utf-8").splitlines()
                              if l.startswith("DETECTOR:")), "")
                patrones = [p.strip() for p in linea.removeprefix("DETECTOR:").split(" | ")
                            if p.strip()]
                motivo.write_text("Patrones de posible prompt injection detectados:\n"
                                  + "\n".join(f"- {p}" for p in patrones) + "\n",
                                  encoding="utf-8")
                if f.exists():
                    shutil.move(str(f), REVISAR / f.name)
                print(f"ingest-worker: {f.name} -> data/revisar/ (patrones: {len(patrones)}); "
                      f"aprobar = moverlo de vuelta a data/inbox/", flush=True)
                continue
            dest = HECHO if r.returncode == 0 else ERROR
            if aprobado:
                motivo.unlink(missing_ok=True)  # aprobacion consumida
        except Exception as e:
            with open(log, "a", encoding="utf-8") as lf:
                lf.write(f"\nworker: {e}\n")
            dest = ERROR
        if f.exists():  # puede haberse borrado a mano (= cancelar); no matar el hilo
            shutil.move(str(f), dest / f.name)


# ZOE_WORKER=0 desactiva el worker (tests que importan app sin querer procesar
# la bandeja real; evita dobles ingestas si hay un backend vivo al lado)
if os.environ.get("ZOE_WORKER", "1") != "0":
    threading.Thread(target=_worker, daemon=True, name="ingest-worker").start()


SUBIR_HTML = """<!doctype html><html lang="es"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ZOE — subir documentos</title>
<body style="font-family:system-ui;max-width:34rem;margin:3rem auto;padding:0 1rem">
<h1>Subir documentos</h1>
<p>PDF, Word, Excel, PowerPoint, texto… El sistema los lee y los integra solo.</p>
<form id="f">
  <input type="file" name="files" multiple required style="display:block;margin:1rem 0">
  <button type="submit" style="padding:.5rem 1.5rem">Subir</button>
</form>
<p id="estado" style="color:#555"></p>
<script>
// El POST va por fetch con X-Token (los POST no aceptan cookie: anti-CSRF).
// El token lo da /token-propio (autenticado por cookie) y no se incrusta en el HTML.
const $ = id => document.getElementById(id);
let TOKEN = null;
async function token() {
  if (!TOKEN) TOKEN = (await (await fetch('/token-propio')).json()).token;
  return TOKEN;
}
async function estado() {
  const d = await (await fetch('/inbox')).json();
  $('estado').textContent =
    'En cola: ' + d.pendientes.length + ' · Procesados: ' + d.hechos + ' · Con error: ' + d.errores;
}
$('f').addEventListener('submit', async e => {
  e.preventDefault();
  const r = await fetch('/upload', {method: 'POST',
    headers: {'X-Token': await token()}, body: new FormData($('f'))});
  const d = await r.json();
  $('estado').textContent = d.ok
    ? 'Subidos: ' + d.aceptados.length + ' · rechazados: ' + d.rechazados.length
    : 'Error: ' + d.error;
  setTimeout(estado, 1500);
});
estado();
</script>
</body></html>"""


@app.get("/subir")
def subir(request: Request):
    resp = _page_auth(request)
    if resp is not None:
        return resp
    return HTMLResponse(SUBIR_HTML)


@app.get("/token-propio")
def token_propio(request: Request):
    """Da el token al JS de las paginas propias (autenticado por cookie de sesion).
    Asi el token nunca viaja incrustado en HTML ni en URLs."""
    if not _auth_page(request):
        return _err("token invalido", 403)
    return {"ok": True, "token": UPLOAD_TOKEN}


@app.post("/upload")
async def upload(request: Request, files: list[UploadFile] = File(...)):
    """Sube documentos a la bandeja de ingesta (data/inbox/).

    Solo se aceptan extensiones de EXTENSIONES_PERMITIDAS
    (.pdf .docx .xlsx .pptx .txt .md .csv) y hasta MAX_UPLOAD_BYTES (100 MB)
    por archivo; el limite se aplica en streaming (nunca se carga en RAM mas
    del limite ni se escribe nada en INBOX de un archivo rechazado)."""
    if not _auth_token(request):  # POST: solo header, la cookie no vale (CSRF)
        return _err("token invalido", 403)
    aceptados, rechazados = [], []
    for uf in files:
        name = _safe_name(uf.filename or "archivo")
        if Path(name).suffix not in EXTENSIONES_PERMITIDAS:
            rechazados.append({"file": uf.filename, "error": "extensión no permitida"})
            continue
        # Lectura en chunks: si supera el limite se corta aqui, sin cargar el
        # body entero en RAM (antes el check llegaba DESPUES de leerlo todo).
        data = bytearray()
        while chunk := await uf.read(1024 * 1024):
            data.extend(chunk)
            if len(data) > MAX_UPLOAD_BYTES:
                break
        if len(data) > MAX_UPLOAD_BYTES:
            rechazados.append({"file": uf.filename, "error": "supera 100 MB"})
            continue
        if not data:
            rechazados.append({"file": uf.filename, "error": "vacio"})
            continue
        (INBOX / name).write_bytes(data)
        aceptados.append({"file": uf.filename, "en_cola_como": name})
    return {"ok": True, "aceptados": aceptados, "rechazados": rechazados,
            "nota": "se procesan en serie; estado en /inbox"}


@app.get("/inbox")
def inbox(request: Request):
    if not _auth_page(request):
        return _err("token invalido", 403)
    en_revision = sorted(p.name for p in REVISAR.iterdir()
                         if p.is_file() and not p.name.endswith(".motivo.txt"))
    return {
        "ok": True,
        "pendientes": sorted(p.name for p in INBOX.iterdir() if p.is_file()),
        "hechos": sum(1 for p in HECHO.iterdir() if p.is_file()),
        "errores": sum(1 for p in ERROR.iterdir() if p.is_file()),
        "ultimos_errores": sorted(p.name for p in ERROR.iterdir() if p.is_file())[-5:],
        "en_revision": len(en_revision),
        "revisar": en_revision,
    }

# --- Configuracion de modelos por niveles (pagina /modelos) -----------------
# Niveles de razonamiento (ligero/medio/profundo) -> modelo + hilos, y el modelo
# router que clasifica peticiones abiertas. Persiste en data/modelos.json; la
# ingesta lo relee en cada archivo (proceso nuevo), sin reiniciar nada.

import urllib.request as _url

MODELOS_FILE = BASE_DIR / "data" / "modelos.json"
NIVEL_DESC = {
    "ligero": "peticiones simples y mecanicas (extraer, formatear, clasificar)",
    "medio": "razonamiento normal (redactar, integrar, responder con contexto)",
    "profundo": "razonamiento profundo — analisis estrategico, mucho contexto",
}
# Capas del sistema -> rol LLM. Las capas software no llevan modelo a proposito.
CAPA_ROL = [
    ("Memoria · preprocesado barato", "preprocesador"),
    ("Memoria · clasificador", "clasificador"),
    ("Memoria · consolidación (wiki)", "integrador"),
    ("Cerebro — razonador diario", "cerebro"),
    ("Dios — estratégico, baja frecuencia", "dios"),
    ("Directores — managers por dominio", "director"),
    ("Agentes especializados", "agente"),
]
CAPAS_SOFTWARE = [
    ("Entrada e ingesta", "upload + extract.py"),
    ("Sistema nervioso", "worker de bandeja + router de niveles"),
    ("Gobernanza", "token, límites de recursos, guards"),
    ("Feedback y estado", "logs, wiki-log, /inbox"),
]


def _ollama_tags() -> list[str]:
    try:
        with _url.urlopen("http://localhost:11434/api/tags", timeout=5) as r:
            return sorted(m["name"] for m in json.load(r)["models"])
    except Exception:
        return []


@app.get("/modelos")
def modelos_page(request: Request):
    resp = _page_auth(request)
    if resp is not None:
        return resp
    import models as _m
    cfg = _m.load_config()
    tags = _ollama_tags() or sorted({v["model"] for v in cfg["niveles"].values()})
    opts = lambda sel: "".join(
        f'<option value="{t}"{" selected" if t == sel else ""}>{t}</option>' for t in tags)
    filas = "".join(
        f'<tr><td><b>{n}</b><br><small>{NIVEL_DESC.get(n, "")}</small></td>'
        f'<td><select name="model_{n}">{opts(v["model"])}</select></td>'
        f'<td><input type="number" name="hilos_{n}" value="{v.get("hilos", 1)}" min="1" max="16" style="width:4rem"></td></tr>'
        for n, v in cfg["niveles"].items())
    niv_opts = lambda sel: "".join(
        f'<option value="{n}"{" selected" if n == sel else ""}>{n}</option>' for n in cfg["niveles"])
    filas_roles = "".join(
        f'<tr><td>{capa}<br><small>rol: {rol}</small></td>'
        f'<td><select name="rol_{rol}">{niv_opts(cfg["roles"].get(rol, "medio"))}</select></td></tr>'
        for capa, rol in CAPA_ROL)
    capas_sw = " · ".join(f"<b>{c}</b>: {que}" for c, que in CAPAS_SOFTWARE)
    html = f"""<!doctype html><html lang="es"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ZOE — modelos</title>
<body style="font-family:system-ui;max-width:40rem;margin:3rem auto;padding:0 1rem">
<h1>Modelos por nivel</h1>
<p>Cada nivel de razonamiento usa el modelo y los hilos que definas aqui.
El <b>router</b> es la IA que clasifica cada peticion abierta en un nivel.</p>
<form method="post" action="/modelos">
<table border="0" cellpadding="6">
<tr><th align="left">Nivel</th><th align="left">Modelo</th><th align="left">Hilos</th></tr>
{filas}
<tr><td><b>router</b><br><small>clasifica peticiones en niveles</small></td>
<td><select name="router">{opts(cfg["router"])}</select></td><td></td></tr>
</table>
<h2>Capas con IA</h2>
<table border="0" cellpadding="6">
<tr><th align="left">Capa</th><th align="left">Nivel</th></tr>
{filas_roles}
</table>
<p><button type="submit" style="padding:.5rem 1.5rem">Guardar</button></p>
</form>
<h2>Capas sin IA (software, a propósito)</h2>
<p><small>{capas_sw}</small></p>
<script>
// POST via fetch con X-Token (los POST no aceptan cookie: anti-CSRF)
document.querySelector('form').addEventListener('submit', async e => {{
  e.preventDefault();
  const t = (await (await fetch('/token-propio')).json()).token;
  const r = await fetch('/modelos', {{method: 'POST', headers: {{'X-Token': t}},
    body: new URLSearchParams(new FormData(e.target))}});
  if ((await r.json()).ok) location.reload(); else alert('Error al guardar');
}});
</script>
</body></html>"""
    return HTMLResponse(html)


@app.post("/modelos")
async def modelos_save(request: Request):
    if not _auth_token(request):  # POST: solo header, la cookie no vale (CSRF)
        return _err("token invalido", 403)
    import models as _m
    form = await request.form()
    cfg = _m.load_config()
    for n in cfg["niveles"]:
        if form.get(f"model_{n}"):
            cfg["niveles"][n]["model"] = str(form[f"model_{n}"])
        if form.get(f"hilos_{n}"):
            cfg["niveles"][n]["hilos"] = max(1, min(16, int(form[f"hilos_{n}"])))
    if form.get("router"):
        cfg["router"] = str(form["router"])
    for _, rol in CAPA_ROL:
        if form.get(f"rol_{rol}") in cfg["niveles"]:
            cfg["roles"][rol] = str(form[f"rol_{rol}"])
    MODELOS_FILE.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"ok": True}


@app.post("/route")
def route_endpoint(q: str, request: Request):
    """Clasifica una peticion en un nivel (router IA). Para integraciones y pruebas."""
    if not _auth_token(request):
        return _err("token invalido", 403)
    import models as _m
    cfg = _m.load_config()  # config caliente: un cambio en /modelos aplica ya, sin reiniciar
    nivel = _m.route(q)
    return {"ok": True, "nivel": nivel, "modelo": cfg["niveles"][nivel]["model"],
            "hilos": cfg["niveles"][nivel].get("hilos", 1)}

# TODO(vector): el /search de esta API sigue en keyword/BM25 puro (la busqueda
# hibrida con embeddings ya esta activa en el memory_search nativo de Zoe).
