"""Fixture de mock para la suite adversarial: ingest_wiki con chat falso
(configurable por test) y MEMORY_DIR temporal. Sin Ollama y sin red."""
import os
import re
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

# ANTES de cualquier import de app: que la suite nunca arranque el worker de
# bandeja (procesaria el data/inbox/ real y podria duplicar ingestas)
os.environ["ZOE_WORKER"] = "0"


@pytest.fixture
def wiki(tmp_path, monkeypatch):
    """ingest_wiki parcheado: MEMORY_DIR -> tmp_path (atributo del modulo, no la
    env: se lee a import) y chat -> fake por rol. Devuelve un namespace con:
      iw        el modulo parcheado
      memory    Path del memory temporal
      prompts   [(rol, user)] de todas las llamadas al fake
      handlers  dict rol -> callable(system, user) -> str, sobreescribible
    """
    import ingest_wiki as iw
    memdir = tmp_path / "memory"
    memdir.mkdir()
    monkeypatch.setattr(iw, "MEMORY_DIR", memdir)

    prompts = []

    def _preprocesador(system, user):
        if user.startswith("Slug:"):  # _linea_indice: rol ligero
            slug = user.split("\n", 1)[0].removeprefix("Slug:").strip()
            return f"- [[{slug}]] — resumen de prueba"
        return "## Hechos\n- hecho de prueba"

    handlers = {
        "preprocesador": _preprocesador,
        "clasificador": lambda s, u: '{"update": [], "create": ["wiki-proyecto-tema.md"]}',
        "integrador": lambda s, u: "# Tema\n\n- hecho de prueba\n",
    }

    def fake_chat(role, system, user, **kw):
        prompts.append((role, user))
        return handlers[role](system, user)

    monkeypatch.setattr(iw, "chat", fake_chat)
    return types.SimpleNamespace(iw=iw, memory=memdir, prompts=prompts, handlers=handlers)


def nonce_de(prompt: str) -> str:
    """Extrae el nonce de la etiqueta <fuente id="..."> de un prompt."""
    m = re.search(r'<fuente id="([0-9a-f]+)">', prompt)
    assert m, "el prompt no contiene <fuente id=...>"
    return m.group(1)
