"""Integración con Windows: ícono, barra de título oscura, accesos directos y arranque."""
from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path

from .core import RAIZ, SIN_VENTANA

log = logging.getLogger("gogocam")

ICONO = RAIZ / "recursos" / "gogocam.ico"
ID_APLICACION = "GoGoDevS.GoGoCam"
CARPETA_INICIO = (Path(os.environ.get("APPDATA", Path.home())) / "Microsoft" / "Windows"
                  / "Start Menu" / "Programs" / "Startup")
ACCESO_INICIO = CARPETA_INICIO / "GoGoCam.lnk"


def iconos_png() -> list[Path]:
    """Ícono de la ventana en varios tamaños, del más grande al más chico."""
    rutas = [RAIZ / "recursos" / nombre
             for nombre in ("gogocam.png", "gogocam-48.png", "gogocam-32.png", "gogocam-16.png")]
    return [ruta for ruta in rutas if ruta.is_file()]


def identificar_aplicacion() -> None:
    """Sin esto Windows agrupa la ventana con Python y muestra el ícono de Python."""
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(ID_APLICACION)
    except (AttributeError, OSError):
        pass


def barra_titulo_oscura(ventana, oscura: bool) -> None:
    """Barra de título oscura de Windows 10/11 (DWMWA_USE_IMMERSIVE_DARK_MODE = 20)."""
    try:
        import ctypes

        ventana.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(ventana.winfo_id())
        valor = ctypes.c_int(1 if oscura else 0)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(valor), ctypes.sizeof(valor))
    except (AttributeError, OSError):
        pass


def pythonw() -> str:
    """El intérprete sin consola que corre a GoGoCam."""
    exe = Path(sys.executable)
    sin_consola = exe.with_name("pythonw.exe")
    return str(sin_consola if sin_consola.is_file() else exe)


def comando_gogocam(minimizada: bool = False) -> tuple[str, str, str]:
    """(ejecutable, argumentos, carpeta de trabajo) para abrir GoGoCam desde un acceso directo:
    el GoGoCam.exe si está empaquetada, o `pythonw -m gogocam` desde el código fuente."""
    extra = "--minimizada" if minimizada else ""
    if getattr(sys, "frozen", False):
        exe = Path(sys.executable)
        return str(exe), extra, str(exe.parent)
    return pythonw(), f"-m gogocam {extra}".strip(), str(RAIZ)


def crear_acceso(destino: Path, minimizada: bool = False) -> None:
    """Crea un acceso directo (.lnk) a GoGoCam con su ícono. Los valores van por variables
    de entorno para no pelear con comillas y espacios en las rutas."""
    script = (
        "$s=(New-Object -ComObject WScript.Shell).CreateShortcut($env:GOGO_LNK);"
        "$s.TargetPath=$env:GOGO_EXE;$s.Arguments=$env:GOGO_ARGS;"
        "$s.WorkingDirectory=$env:GOGO_DIR;$s.IconLocation=$env:GOGO_ICO;"
        "$s.Description='GoGoCam: la cámara del teléfono como cámara web';$s.Save()"
    )
    exe, argumentos, carpeta = comando_gogocam(minimizada)
    entorno = {**os.environ, "GOGO_LNK": str(destino), "GOGO_EXE": exe, "GOGO_ARGS": argumentos,
               "GOGO_DIR": carpeta, "GOGO_ICO": str(ICONO)}
    resultado = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        env=entorno, capture_output=True, text=True, timeout=30, creationflags=SIN_VENTANA,
    )
    if resultado.returncode != 0 or not destino.is_file():
        raise OSError(f"no pude crear el acceso directo {destino}: {resultado.stderr.strip()}")


def abre_con_windows() -> bool:
    return ACCESO_INICIO.is_file()


def abrir_con_windows(activar: bool) -> None:
    """Pone o quita GoGoCam del inicio de Windows (se abre minimizada)."""
    if activar:
        CARPETA_INICIO.mkdir(parents=True, exist_ok=True)
        crear_acceso(ACCESO_INICIO, minimizada=True)
        log.info("GoGoCam se abrirá con Windows: %s", ACCESO_INICIO)
    elif ACCESO_INICIO.exists():
        ACCESO_INICIO.unlink()
        log.info("GoGoCam ya no se abre con Windows")
