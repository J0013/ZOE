"""
Broker de modelos de ZOE. Ollama-only, local-first: aqui no entra ningun
proveedor cloud (ver directriz local-first del proyecto).

Implementa la politica de coste e inteligencia del sistema:
"usar el modelo mas barato posible que mantenga la calidad suficiente para esa tarea".

Tres piezas:
  - NIVELES: ligero / medio / profundo ("razonamiento de dios"). Cada nivel define
    QUE modelo lo sirve y CUANTOS hilos paralelos admite (peticiones simultaneas al
    mismo modelo, estilo subagentes). Se configura en data/modelos.json — editable
    tambien desde la pagina /modelos del backend, sin tocar codigo.
  - ROLES: rol de capa -> nivel. Los scripts piden un ROL, nunca un modelo.
    Mapa de capas del sistema a roles LLM — las capas que NO aparecen aqui son
    software a proposito (nervioso=coordinar, gobernanza=reglas):
      Memoria/preprocesado barato  -> preprocesador (ligero)
      Memoria/clasificador         -> clasificador  (ligero)
      Memoria/consolidacion (wiki) -> integrador    (medio)
      Cerebro (razonador diario)   -> cerebro       (medio; escala via route())
      Dios (estrategico, poca frecuencia, solo resumenes) -> dios (profundo)
      Directores (managers ligeros por dominio)           -> director (ligero)
      Agentes especializados (tareas estrechas)           -> agente (ligero)
  - route(): el router IA — un modelo que designamos clasifica una peticion en un
    nivel cuando nadie lo ha decidido explicitamente. Regla del sistema: lo explicito
    no se re-razona; el router es para peticiones abiertas.

Endpoint del daemon Ollama: http://localhost:11434 por defecto.
Override: variables de entorno OLLAMA_URL y ZOE_HILOS (fuerza hilos globales).

Nota hardware: un modelo que no cabe en la VRAM de la GPU hace offload parcial a
CPU y va lento (util solo para batch nocturno). En hardware con memoria unificada
grande va fluido.
"""

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")

_loopback_avisado = False


def _avisar_si_no_loopback():
    """Aviso (no bloqueo: hay despliegues remotos legitimos) si Ollama no es local."""
    global _loopback_avisado
    if _loopback_avisado:
        return
    _loopback_avisado = True
    from urllib.parse import urlparse
    host = urlparse(OLLAMA_URL).hostname or ""
    if host not in ("localhost", "127.0.0.1", "::1"):
        print(f"AVISO: OLLAMA_URL apunta fuera de loopback ({host}); asegúrate de que "
              "el canal es Tailscale/VPN, nunca un puerto expuesto", flush=True)

CONFIG_FILE = Path(__file__).parent / "data" / "modelos.json"
_DEFAULTS = {
    "router": "gemma4:latest",
    "niveles": {
        "ligero": {"model": "gemma4:latest", "hilos": 2},
        "medio": {"model": "gemma4:latest", "hilos": 2},
        "profundo": {"model": "gemma4:latest", "hilos": 1},
    },
    "roles": {"preprocesador": "ligero", "clasificador": "ligero", "integrador": "medio"},
}


def load_config() -> dict:
    """data/modelos.json sobre los defaults. Se relee en cada import/proceso;
    el worker de ingesta lanza un proceso por archivo, asi que los cambios de la
    pagina /modelos aplican a la siguiente ingesta sin reiniciar nada."""
    cfg = json.loads(json.dumps(_DEFAULTS))  # copia profunda
    if CONFIG_FILE.exists():
        try:
            user = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            cfg["router"] = user.get("router", cfg["router"])
            for k, v in user.get("niveles", {}).items():
                cfg["niveles"].setdefault(k, {}).update(v)
            cfg["roles"].update(user.get("roles", {}))
        except (json.JSONDecodeError, OSError) as e:
            print(f"models: config invalida, uso defaults ({e})")
    return cfg


_CFG = load_config()
NIVELES = _CFG["niveles"]
ROLES = _CFG["roles"]
ROUTER_MODEL = _CFG["router"]


def modelo_de(rol_o_nivel: str) -> str:
    nivel = ROLES.get(rol_o_nivel, rol_o_nivel)
    return NIVELES[nivel]["model"]


def hilos_de(rol_o_nivel: str) -> int:
    if os.environ.get("ZOE_HILOS"):
        return int(os.environ["ZOE_HILOS"])
    nivel = ROLES.get(rol_o_nivel, rol_o_nivel)
    return int(NIVELES[nivel].get("hilos", 1))


def chat(role: str, system: str, user: str, schema: dict | None = None,
         num_ctx: int = 16384, num_predict: int = 16384, timeout: int = 600) -> str:
    """Llamada unica a Ollama en el rol (o nivel) dado. Devuelve el texto.

    Nota: en esta build (ollama 0.20.2 + gemma4) el parametro format/grammar NO se
    aplica (el modelo devuelve fences ```json igualmente). Se envia igual por si un
    modelo futuro lo respeta, pero el contrato real es: parsear con parse_json().
    """
    _avisar_si_no_loopback()
    body = {
        "model": modelo_de(role),
        "stream": False,
        # gemma4 es modelo thinking: sin esto quema num_predict en el canal thinking
        "think": False,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "options": {"num_ctx": num_ctx, "num_predict": num_predict, "temperature": 0},
    }
    if schema is not None:
        body["format"] = schema
    req = urllib.request.Request(
        f"{OLLAMA_URL}/api/chat",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    # el runner CUDA se cae a veces a mitad de generacion (error 500); Ollama lo
    # relanza en la siguiente peticion -> reintentar es la recuperacion correcta
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = json.load(r)
            break
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as e:
            if attempt == 2:
                raise
            print(f"  ollama fallo ({e}); reintento {attempt + 1}/2 en 15s...", flush=True)
            time.sleep(15)
    msg = data.get("message", {})
    if data.get("done_reason") == "length":
        raise RuntimeError(f"salida truncada (num_predict={num_predict}); acotar la tarea")
    return msg.get("content", "")


def route(peticion: str) -> str:
    """Router IA: clasifica una peticion abierta en un nivel.
    ligero = mecanico/simple · medio = razonamiento normal · profundo = "dios"
    (analisis estrategico, cruzar mucho contexto, decisiones de peso)."""
    cfg = load_config()  # config caliente: el backend vive dias; /modelos debe aplicar sin reiniciar
    system = ("Eres el router de un sistema de IA. Clasifica la peticion del usuario "
              "en UN nivel de razonamiento y responde SOLO esa palabra:\n"
              "ligero  — tarea mecanica o simple: extraer, formatear, resumir corto, si/no\n"
              "medio   — razonamiento normal: redactar, integrar, responder con contexto\n"
              "profundo — razonamiento estrategico: analisis global, cruzar mucho contexto, "
              "detectar patrones, decisiones de peso o revision de direccion")
    body = {
        "model": cfg["router"], "stream": False, "think": False,
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": peticion[:2000]}],
        "options": {"num_ctx": 4096, "num_predict": 8, "temperature": 0},
    }
    req = urllib.request.Request(f"{OLLAMA_URL}/api/chat", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        out = json.load(r).get("message", {}).get("content", "").strip().lower()
    for nivel in cfg["niveles"]:
        if nivel in out:
            return nivel
    return "medio"  # ponytail: ante duda del router, nivel intermedio


def parse_json(text: str) -> dict:
    """json.loads tolerante: quita fences ```json y recorta al primer {...} balanceado."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text
        text = text.rsplit("```", 1)[0]
    start = text.find("{")
    if start > 0:
        text = text[start:]
    obj, _ = json.JSONDecoder().raw_decode(text.strip())  # tolera texto residual detras
    return obj


if __name__ == "__main__":
    # self-check: config, resolucion rol->modelo, parse tolerante y router
    _avisar_si_no_loopback()
    assert modelo_de("preprocesador") == NIVELES["ligero"]["model"]
    assert hilos_de("integrador") >= 1
    assert parse_json('```json\n{"n": [1,2,3]}\n```texto residual')["n"] == [1, 2, 3]
    print("config OK:", {n: v["model"] for n, v in NIVELES.items()}, "| router:", ROUTER_MODEL)
    try:
        for p in ["pon esta fecha en formato ISO: 3 de mayo",
                  "redacta un resumen de la reunion de ayer para el equipo",
                  "analiza los ultimos tres meses de reuniones y dime si estamos desviandonos de la estrategia"]:
            print(f"  route({p[:50]!r}...) ->", route(p))
    except (urllib.error.URLError, TimeoutError):
        print("  router: Ollama no disponible; self-check del router saltado (CI)")
