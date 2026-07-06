"""Tests sin servidor ni Ollama: parseo, sanitizado y query-building puros."""
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from ingest_wiki import parse_records, source_filename, locator  # noqa: E402
from models import parse_json  # noqa: E402


def test_parse_records_dataset_demo():
    text = (ROOT / "examples" / "resumenes-demo.txt").read_text(encoding="utf-8")
    recs = parse_records(text)
    assert len(recs) == 3
    assert recs[0]["src"] == "src-reunion-01"
    assert recs[0]["fecha"] == "2026-01-12"
    assert "embalaje" in recs[0]["cuerpo"]
    assert source_filename(recs[0]) == "src-reunion-01-2026-01-12.md"
    assert locator(recs[0]) == "(src-reunion-01, 2026-01-12)"


def test_parse_records_texto_sin_cabeceras():
    assert parse_records("texto plano sin cabeceras =====") == []


def test_parse_json_tolerante():
    assert parse_json('```json\n{"n": [1, 2, 3]}\n```texto residual')["n"] == [1, 2, 3]
    assert parse_json('prefijo basura {"a": {"b": 1}} y cola')["a"]["b"] == 1


def test_fts_query():
    from app import _fts_query
    assert _fts_query("kiwi verde") == '"kiwi"* OR "verde"*'
    assert _fts_query("") == ""
    # los operadores/comillas del usuario no llegan crudos a FTS5
    assert _fts_query('"; DROP TABLE--') == '"DROP"* OR "TABLE"*'


def test_safe_name():
    from app import _safe_name
    n = _safe_name("../../etc/passwd.pdf")
    assert "/" not in n and ".." not in n
    assert n.endswith(".pdf")
    # timestamp UTC delante: siempre unico y ordenable
    assert n[:8].isdigit()
