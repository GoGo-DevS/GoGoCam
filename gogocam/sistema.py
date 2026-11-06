"""Integración con el sistema: ícono, barra de título oscura, accesos directos y arranque.

En Windows el arranque es un acceso directo (.lnk) en la carpeta Inicio; en Linux, un
archivo .desktop en ~/.config/autostart (el estándar de freedesktop que siguen GNOME,
KDE, Cinnamon, XFCE y compañía).
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path

from .core import ES_WINDOWS, RAIZ, SIN_VENTANA

log = logging.getLogger("gogocam")

ICONO = RAIZ / "recursos" / "gogocam.ico"
ICONO_PNG = RAIZ / "recursos" / "gogocam.png"
ID_APLICACION = "GoGoDevS.GoGoCam"
# Linux: la clase de la ventana (WM_CLASS) une la ventana con su ícono del menú. Tk la deja
# con mayúscula inicial y el resto en minúsculas: "gogocam" queda "Gogocam".
CLASE_VENTANA = "gogocam"
CLASE_VENTANA_X11 = "Gogocam"
if ES_WINDOWS:
    ACCESO_INICIO = (Path(os.environ.get("APPDATA", Path.home())) / "Microsoft" / "Windows"
                     / "Start Menu" / "Programs" / "Startup" / "GoGoCam.lnk")
else:
    ACCESO_INICIO = (Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
                     / "autostart" / "gogocam.desktop")


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
    """El intérprete que corre a GoGoCam (en Windows, el que no abre consola)."""
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
    """Windows: crea un acceso directo (.lnk) a GoGoCam con su ícono. Los valores van por
    variables de entorno para no pelear con comillas y espacios en las rutas."""
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


def argumento_desktop(texto: str) -> str:
    """Un argumento para la línea Exec= de un .desktop: entre comillas si lleva espacios
    u otros caracteres reservados, escapando ", `, $ y \\ (especificación freedesktop)."""
    if texto and not any(c in texto for c in " \t\n\"'\\><~|&;$*?#()`"):
        return texto
    for especial in ("\\", '"', "`", "$"):
        texto = texto.replace(especial, "\\" + especial)
    return f'"{texto}"'


def escribir_desktop(destino: Path, minimizada: bool = False) -> None:
    """Linux: crea el .desktop que abre GoGoCam."""
    exe, argumentos, carpeta = comando_gogocam(minimizada)
    linea = " ".join([argumento_desktop(exe), *argumentos.split()])
    contenido = "\n".join([
        "[Desktop Entry]",
        "Type=Application",
        "Name=GoGoCam",
        "Comment=La cámara del teléfono como cámara web",
        f"Exec={linea}",
        f"Path={carpeta}",
        f"Icon={ICONO_PNG}",
        "Terminal=false",
        "Categories=AudioVideo;Video;",
        f"StartupWMClass={CLASE_VENTANA_X11}",
        "X-GNOME-Autostart-enabled=true",
        "",
    ])
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(contenido, encoding="utf-8")


def abre_al_encender() -> bool:
    return ACCESO_INICIO.is_file()


def abrir_al_encender(activar: bool) -> None:
    """Pone o quita GoGoCam del arranque de la sesión (se abre minimizada)."""
    if activar:
        ACCESO_INICIO.parent.mkdir(parents=True, exist_ok=True)
        if ES_WINDOWS:
            crear_acceso(ACCESO_INICIO, minimizada=True)
        else:
            escribir_desktop(ACCESO_INICIO, minimizada=True)
        log.info("GoGoCam se abrirá al encender: %s", ACCESO_INICIO)
    elif ACCESO_INICIO.exists():
        ACCESO_INICIO.unlink()
        log.info("GoGoCam ya no se abre al encender")
