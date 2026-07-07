"""Tests de regresión de seguridad sobre el backend (app.py). Sin Ollama, sin red.
Cada test cubre un fix concreto de la auditoría; si el fix se revierte, falla."""
import os
import stat
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))


def _chmod_funciona(directorio: Path) -> bool:
    """En drvfs (/mnt/*) y Windows chmod es no-op: ahí no se puede medir el modo.
    En CI (Linux nativo) sí se verifica de verdad."""
    probe = directorio / ".perm_probe"
    probe.touch()
    probe.chmod(0o600)
    ok = stat.S_IMODE(os.stat(probe).st_mode) == 0o600
    probe.unlink()
    return ok


def test_token_file_permisos_0600():
    """data/upload_token.txt no debe ser legible por otros usuarios locales."""
    import app
    if not _chmod_funciona(app.TOKEN_FILE.parent):
        pytest.skip("el filesystem ignora chmod (drvfs/Windows); se verifica en CI")
    assert stat.S_IMODE(os.stat(app.TOKEN_FILE).st_mode) == 0o600


def test_token_no_ascii_no_peta():
    """Un token con bytes no-ASCII (headers llegan como latin-1) debe rechazarse
    limpio, no lanzar TypeError (que acababa en 500). A nivel de función porque
    httpx rechaza headers no-ASCII antes de enviarlos."""
    import app
    assert app._token_valido("ñoño") is False
    assert app._token_valido("") is False
    assert app._token_valido(app.UPLOAD_TOKEN) is True
