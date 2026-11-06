"""Revisa que GoGoCam tenga todo lo que necesita, SIN tocar el teléfono.

    GoGoCam.exe --diagnostico            (o: python -m gogocam --diagnostico)

El resultado queda en gogocam.log (carpeta %LOCALAPPDATA%\\GoGoCam) y el programa
sale con código 0 si todo está bien. Sirve para revisar un .exe recién armado y
para que un amigo mande su registro cuando algo no le funciona.
"""
from __future__ import annotations

import hashlib
import logging
import subprocess
import sys
from typing import Callable

from . import __version__
from .core import FALTA_OBS, RAIZ, SERVIDOR_LOCAL, SIN_VENTANA, GoGoCamError, buscar_adb

log = logging.getLogger("gogocam")


def _version() -> str:
    modo = "empaquetada" if getattr(sys, "frozen", False) else "código fuente"
    return f"GoGoCam {__version__} ({modo}) en {RAIZ}"


def _servidor() -> str:
    esperado = None
    for linea in (RAIZ / "vendor" / "SHA256SUMS.txt").read_text(encoding="utf-8").splitlines():
        partes = linea.split()
        if len(partes) == 2 and partes[1] == SERVIDOR_LOCAL.name:
            esperado = partes[0]
    real = hashlib.sha256(SERVIDOR_LOCAL.read_bytes()).hexdigest()
    if real != esperado:
        raise GoGoCamError(f"{SERVIDOR_LOCAL.name} no coincide con SHA256SUMS.txt")
    return f"{SERVIDOR_LOCAL.name} íntegro"


def _adb() -> str:
    exe = buscar_adb()
    # `adb version` responde solo: no arranca el servidor de adb ni le habla al teléfono.
    r = subprocess.run([exe, "version"], capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=15, creationflags=SIN_VENTANA)
    if r.returncode != 0:
        raise GoGoCamError(f"adb version falló: {(r.stderr or r.stdout).strip()}")
    return f"{r.stdout.splitlines()[0]} ({exe})"


def _decodificador() -> str:
    import av

    av.CodecContext.create("h264", "r")
    return f"PyAV {av.__version__}"


CATEGORIA_CAMARAS = r"CLSID\{860BB310-5D01-11D0-BD3B-00A0C911CE86}\Instance"  # cámaras DirectShow


def camaras_de_windows() -> list[str]:
    """Nombres de las cámaras que ven Meet, Zoom y compañía (las registradas en DirectShow)."""
    import winreg

    nombres = []
    with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, CATEGORIA_CAMARAS) as instancias:
        for i in range(winreg.QueryInfoKey(instancias)[0]):
            with winreg.OpenKey(instancias, winreg.EnumKey(instancias, i)) as camara:
                try:
                    nombres.append(winreg.QueryValueEx(camara, "FriendlyName")[0])
                except OSError:
                    continue
    return nombres


def _camara_virtual() -> str:
    """La busca SIN abrirla: abrirla chocaría con una transmisión en curso, y el diagnóstico
    se tiene que poder correr en plena llamada."""
    if "OBS Virtual Camera" in camaras_de_windows():
        return "instalada"
    raise GoGoCamError(FALTA_OBS)


REVISIONES: list[tuple[str, Callable[[], str]]] = [
    ("versión", _version),
    ("servidor de scrcpy", _servidor),
    ("adb", _adb),
    ("decodificador H.264", _decodificador),
    ("OBS Virtual Camera", _camara_virtual),
]


def revisar(revisiones: list[tuple[str, Callable[[], str]]] = REVISIONES) -> list[tuple[str, bool, str]]:
    """Corre todas las revisiones aunque alguna falle, y las deja en el registro."""
    resultados = []
    for nombre, revision in revisiones:
        try:
            ok, detalle = True, revision()
        except Exception as e:  # noqa: BLE001 — el diagnóstico informa la falla, no se cae
            ok, detalle = False, str(e) or type(e).__name__
        log.info("diagnóstico · %s: %s · %s", nombre, "OK" if ok else "FALLA", detalle)
        resultados.append((nombre, ok, detalle))
    return resultados
