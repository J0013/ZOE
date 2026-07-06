"""Suite de regresión adversarial: documentos hostiles contra la ingesta, con el
LLM mockeado (fixture `wiki` en conftest.py). Asserts MECÁNICOS: el fake devuelve
salidas controladas, no se juzga la salida de ningún modelo. Sin Ollama, sin red."""
import hashlib
import re
from pathlib import Path

ADV = Path(__file__).parent / "adversarial"
ROOT = Path(__file__).parent.parent


def _rec(wiki, doc: str, fecha: str = "2026-06-01"):
    return wiki.iw.file_record(str(ADV / doc), fecha, None)


def test_locator_fabricado_no_entra(wiki, capsys):
    """El fake integrador copia el locator fabricado del documento -> la página
    NO se escribe y sale el aviso."""
    wiki.handlers["integrador"] = lambda s, u: (
        "# Mercado\n\n- La competencia bajó precios un 12% (src-reunion-04, 2026-03-01)\n")
    wiki.iw.ingest_record(_rec(wiki, "locator_falso.txt"))
    assert not (wiki.memory / "wiki-proyecto-tema.md").exists()
    assert "locator ilegítimo" in capsys.readouterr().out


def test_locators_fuente_neutralizados(wiki):
    """Los locators que vienen dentro de la fuente llegan al LLM marcados como
    NO verificados, nunca intactos."""
    wiki.iw.ingest_record(_rec(wiki, "locator_falso.txt"))
    users = [u for _, u in wiki.prompts]
    assert any("[locator presente en la fuente, NO verificado" in u for u in users)
    assert not any("(src-reunion-04, 2026-03-01)" in u for u in users)
    assert not any("(src-doc-plan-inversion, 2026-04-15)" in u for u in users)


def test_fuente_inmutable_verbatim(wiki):
    """La neutralización es solo para el pipeline: el src-*.md guarda el
    original intacto mientras el LLM recibe los locators marcados."""
    rec = _rec(wiki, "locator_falso.txt")
    wiki.iw.ingest_record(rec)
    src = (wiki.memory / wiki.iw.source_filename(rec)).read_text(encoding="utf-8")
    assert "(src-reunion-04, 2026-03-01)" in src
    assert "[locator presente en la fuente, NO verificado" not in src
    assert any("[locator presente en la fuente, NO verificado" in u
               for _, u in wiki.prompts)


def test_neutralizacion_idempotente():
    """Neutralizar dos veces no re-marca, y el marcador no re-matchea como locator."""
    import ingest_wiki as iw
    x = "informe con (src-reunion-04, 2026-03-01) y (src-doc-plan, 2026-04-15, ext) dentro"
    una = iw.neutralizar_locators_fuente(x)
    assert iw.neutralizar_locators_fuente(una) == una
    assert not iw.LOCATOR_RE.search(una)


def test_nonce_en_prompt(wiki):
    """El cuerpo va envuelto en <fuente id=nonce> y el documento no puede
    conocer el nonce (no aparece en su contenido)."""
    wiki.iw.ingest_record(_rec(wiki, "inyeccion_directa.txt"))
    integ = [u for r, u in wiki.prompts if r == "integrador"]
    assert integ, "el integrador no llegó a ejecutarse"
    m = re.search(r'<fuente id="([0-9a-f]+)">', integ[0])
    assert m, "el prompt del integrador no contiene <fuente id=...>"
    doc = (ADV / "inyeccion_directa.txt").read_text(encoding="utf-8")
    assert m.group(1) not in doc


def test_paginas_ajenas_intactas(wiki):
    """Un documento que ordena borrar otra página no la toca: el pipeline solo
    escribe las páginas que el clasificador designó para SU tema."""
    ajena = wiki.memory / "wiki-cliente-demo-client.md"
    ajena.write_text("# Cliente demo\n\n- dato previo (src-reunion-01, 2026-01-12)\n",
                     encoding="utf-8")
    antes = hashlib.sha256(ajena.read_bytes()).hexdigest()
    rec = _rec(wiki, "reescritura_ajena.txt")
    wiki.handlers["clasificador"] = \
        lambda s, u: '{"update": [], "create": ["wiki-proyecto-faro.md"]}'
    wiki.handlers["integrador"] = lambda s, u: (
        f"# Faro\n\n- El piloto avanza según lo previsto {wiki.iw.locator(rec)}\n")
    wiki.iw.ingest_record(rec)
    assert (wiki.memory / "wiki-proyecto-faro.md").exists()
    assert hashlib.sha256(ajena.read_bytes()).hexdigest() == antes


def test_detector():
    """El detector de puerta caza los 4 documentos hostiles y no marca un acta limpia."""
    from detector import sospechoso
    from extract import extract
    for doc in ("inyeccion_directa.txt", "locator_falso.txt",
                "texto_oculto.txt", "reescritura_ajena.txt"):
        assert sospechoso(extract(ADV / doc)), f"{doc} no detectado"
    limpia = (ROOT / "examples" / "resumenes-demo.txt").read_text(encoding="utf-8")
    assert sospechoso(limpia) == []


def test_normalizacion():
    """El texto oculto con ancho cero se normaliza en la extracción y solo
    entonces el detector lo caza."""
    from detector import sospechoso
    from extract import extract
    crudo = (ADV / "texto_oculto.txt").read_text(encoding="utf-8")
    assert "\u200b" in crudo  # el fixture de verdad esconde la instrucción
    texto = extract(ADV / "texto_oculto.txt")
    assert "\u200b" not in texto
    assert sospechoso(texto)


# --- superficie del servidor (TestClient, sin arrancar uvicorn) --------------

def _client():
    from fastapi.testclient import TestClient
    import app as app_mod
    # base_url fija el Host a uno de la allowlist anti DNS-rebinding
    return TestClient(app_mod.app, base_url="http://localhost:8900"), app_mod


def test_extension_allowlist():
    client, app_mod = _client()
    r = client.post("/upload", headers={"X-Token": app_mod.UPLOAD_TOKEN},
                    files=[("files", ("malo.exe", b"MZ binario", "application/octet-stream"))])
    d = r.json()
    assert d["rechazados"][0]["error"] == "extensión no permitida"
    assert not list(app_mod.INBOX.glob("*malo*"))


def test_streaming_limit(monkeypatch):
    client, app_mod = _client()
    monkeypatch.setattr(app_mod, "MAX_UPLOAD_BYTES", 1024)
    r = client.post("/upload", headers={"X-Token": app_mod.UPLOAD_TOKEN},
                    files=[("files", ("grande.txt", b"x" * 4096, "text/plain"))])
    assert r.json()["rechazados"][0]["error"] == "supera 100 MB"
    assert not list(app_mod.INBOX.glob("*grande*"))
