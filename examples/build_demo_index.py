#!/usr/bin/env python3
"""Indexador demo: construye el indice SQLite FTS5 que consulta /search,
sin necesidad del runtime OpenClaw. Un chunk por archivo .md de la memoria.

Uso (desde la raiz del repo):  python3 examples/build_demo_index.py
Respeta ZOE_MEMORY_DIR (default ./memory) y ZOE_DB_PATH (default ./data/index.sqlite).
"""
import os
import sqlite3
from pathlib import Path

MEMORY_DIR = Path(os.environ.get("ZOE_MEMORY_DIR", "./memory"))
DB_PATH = Path(os.environ.get("ZOE_DB_PATH", "./data/index.sqlite"))

MEMORY_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

con = sqlite3.connect(DB_PATH)
con.executescript("""
    DROP TABLE IF EXISTS chunks;
    DROP TABLE IF EXISTS chunks_fts;
    CREATE TABLE chunks (path TEXT NOT NULL);
    CREATE VIRTUAL TABLE chunks_fts USING fts5(text, path);
""")
n = 0
for p in sorted(MEMORY_DIR.glob("*.md")):
    rel = f"memory/{p.name}"
    con.execute("INSERT INTO chunks (path) VALUES (?)", (rel,))
    con.execute("INSERT INTO chunks_fts (text, path) VALUES (?, ?)",
                (p.read_text(encoding="utf-8"), rel))
    n += 1
con.commit()
con.close()
print(f"indexados {n} documentos de {MEMORY_DIR} en {DB_PATH}")
