"""Revisa que GoGoCam tenga todo lo que necesita, SIN tocar el teléfono.

    GoGoCam.exe --diagnostico            Windows, versión empaquetada
    gogocam --diagnostico                Linux, después de instalar.sh
    python -m gogocam --diagnostico      desde el código fuente

El resultado queda en gogocam.log (Windows: %LOCALAPPDATA%\\GoGoCam; Linux:
~/.local/share/gogocam) y el programa sale con código 0 si todo está bien. Sirve
para revisar un paquete recién armado y para que un amigo mande su registro
cuando algo no le funciona.
"""
from __future__ import annotations

import hashlib
import logging
import os
import platform
import subprocess
import sys
from pathlib import Path
from typing import Callable

from . import __version__
from .core import (
    ES_WINDOWS, FALTA_OBS, FALTA_V4L2, NOMBRE_CAMARA_VIRTUAL, RAIZ, SERVIDOR_LOCAL, SIN_PERMISO_V4L2,
    SIN_VENTANA, GoGoCamError, buscar_adb,
)

log = logging.getLogger("gogocam")


def _version() -> str:
    modo = "empaquetada" if getattr(sys, "frozen", False) else "código fuente"
    return (f"GoGoCam {__version__} ({modo}) · {platform.system()} {platform.release()} · "
            f"Python {platform.python_version()} · en {RAIZ}")


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


def _ventana() -> str:
    """Tk viene con Python en Windows; en Linux es un paquete aparte (python3-tk)."""
    try:
        import tkinter
    except ImportError as e:
        raise GoGoCamError("Falta Tk para Python: la ventana no puede abrir "
                           "(Ubuntu, Mint o Debian: sudo apt install python3-tk).") from e
    return f"Tk {tkinter.TkVersion}"


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


def camaras_v4l2loopback(carpeta: Path = Path("/sys/devices/virtual/video4linux"),
                         dev: Path = Path("/dev")) -> list[tuple[str, Path]]:
    """(nombre, /dev/videoN) de las cámaras virtuales de Linux. Las de v4l2loopback cuelgan de
    /sys/devices/virtual; las webcams reales, de su bus (USB, PCI)."""
    if not carpeta.is_dir():
        return []
    camaras = []
    for dispositivo in sorted(carpeta.glob("video*")):
        try:
            nombre = (dispositivo / "name").read_text(encoding="utf-8").strip()
        except OSError:
            nombre = ""
        camaras.append((nombre or dispositivo.name, dev / dispositivo.name))
    return camaras


def _camara_virtual() -> str:
    """La busca SIN abrirla: abrirla chocaría con una transmisión en curso, y el diagnóstico
    se tiene que poder correr en plena llamada."""
    if ES_WINDOWS:
        if "OBS Virtual Camera" in camaras_de_windows():
            return "instalada"
        raise GoGoCamError(FALTA_OBS)
    camaras = camaras_v4l2loopback()
    if not camaras:
        raise GoGoCamError(FALTA_V4L2)
    usables = [f"«{nombre}» ({ruta})" for nombre, ruta in camaras if os.access(ruta, os.W_OK)]
    if not usables:
        raise GoGoCamError(SIN_PERMISO_V4L2)
    return "lista: " + ", ".join(usables)


REVISIONES: list[tuple[str, Callable[[], str]]] = [
    ("versión", _version),
    ("servidor de scrcpy", _servidor),
    ("adb", _adb),
    ("decodificador H.264", _decodificador),
    ("ventana (Tk)", _ventana),
    (f"cámara virtual ({NOMBRE_CAMARA_VIRTUAL})", _camara_virtual),
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
