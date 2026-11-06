"""Arma GoGoCam para compartir: dist/GoGoCam/ (GoGoCam.exe y todo lo que necesita) y
dist/GoGoCam-<versión>.zip. Quien lo recibe no necesita Python ni adb; solo OBS Studio.

    .\\.venv\\Scripts\\python.exe -m pip install -r requirements-empaquetar.txt
    .\\.venv\\Scripts\\python.exe herramientas\\empaquetar.py

adb sale de Android Platform Tools: GOGOCAM_PLATFORM_TOOLS, el adb del PATH o
%LOCALAPPDATA%\\Android\\Sdk\\platform-tools.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import zipfile
from importlib.metadata import distribution
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from gogocam import __version__  # noqa: E402
from gogocam.core import SERVIDOR_LOCAL  # noqa: E402

ARCHIVOS_ADB = ("adb.exe", "AdbWinApi.dll", "AdbWinUsbApi.dll")
DIST = RAIZ / "dist"
TRABAJO = RAIZ / "build"
APP = DIST / "GoGoCam"


def carpeta_platform_tools() -> Path:
    adb_path = shutil.which("adb")
    candidatos = [
        os.environ.get("GOGOCAM_PLATFORM_TOOLS"),
        str(Path(adb_path).parent) if adb_path else None,
        str(Path(os.environ.get("LOCALAPPDATA", "")) / "Android" / "Sdk" / "platform-tools"),
    ]
    for candidato in candidatos:
        if candidato and all((Path(candidato) / n).is_file() for n in ARCHIVOS_ADB):
            return Path(candidato)
    raise SystemExit(f"No encontré Platform Tools completo ({', '.join(ARCHIVOS_ADB)}). "
                     "Define GOGOCAM_PLATFORM_TOOLS con su carpeta.")


def verificar_servidor() -> None:
    sumas = (RAIZ / "vendor" / "SHA256SUMS.txt").read_text(encoding="utf-8")
    real = hashlib.sha256(SERVIDOR_LOCAL.read_bytes()).hexdigest()
    if f"{real}  {SERVIDOR_LOCAL.name}" not in sumas:
        raise SystemExit(f"{SERVIDOR_LOCAL.name} no coincide con vendor/SHA256SUMS.txt: no lo empaqueto.")


def correr_pyinstaller(platform_tools: Path) -> None:
    datos = [
        (SERVIDOR_LOCAL, "vendor"),
        (RAIZ / "vendor" / "SHA256SUMS.txt", "vendor"),
        (RAIZ / "recursos", "recursos"),
        # Como datos y no como binarios: así PyInstaller no los analiza ni los reparte.
        *[(platform_tools / n, "vendor") for n in ARCHIVOS_ADB],
    ]
    comando = [
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed", "--noupx",
        "--name", "GoGoCam", "--icon", str(RAIZ / "recursos" / "gogocam.ico"),
        "--distpath", str(DIST), "--workpath", str(TRABAJO / "pyinstaller"), "--specpath", str(TRABAJO),
    ]
    for origen, destino in datos:
        comando += ["--add-data", f"{origen}{os.pathsep}{destino}"]
    comando.append(str(RAIZ / "lanzador.py"))
    subprocess.run(comando, check=True, cwd=RAIZ)


def copiar_licencias(destino: Path, platform_tools: Path) -> None:
    destino.mkdir(parents=True, exist_ok=True)
    shutil.copy2(RAIZ / "distribucion" / "LICENCIAS.txt", destino / "LICENCIAS.txt")
    shutil.copy2(RAIZ / "vendor" / "LICENSE-scrcpy.txt", destino / "scrcpy-LICENSE.txt")
    shutil.copy2(platform_tools / "NOTICE.txt", destino / "adb-NOTICE.txt")
    for paquete in ("pyvirtualcam", "av", "numpy"):
        dist = distribution(paquete)
        for archivo in dist.files or []:
            partes = archivo.parts
            if (len(partes) > 2 and partes[0].endswith(".dist-info") and partes[1] == "licenses"
                    and "__pycache__" not in partes):
                salida = destino / paquete / Path(*partes[2:])
                salida.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(dist.locate_file(archivo), salida)


def zip_codigo_fuente(destino: Path) -> None:
    """Los archivos que sigue git, tal como están en disco (con cambios sin commitear)."""
    lista = subprocess.run(["git", "ls-files"], cwd=RAIZ, capture_output=True, text=True, check=True)
    with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for nombre in lista.stdout.splitlines():
            if (RAIZ / nombre).is_file():
                z.write(RAIZ / nombre, f"gogocam-{__version__}/{nombre}")


def comprimir(carpeta: Path, destino: Path) -> None:
    with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for archivo in sorted(carpeta.rglob("*")):
            if archivo.is_file():
                z.write(archivo, Path(carpeta.name) / archivo.relative_to(carpeta))


def main() -> int:
    verificar_servidor()
    platform_tools = carpeta_platform_tools()
    print(f"GoGoCam {__version__} · adb de {platform_tools}")
    correr_pyinstaller(platform_tools)

    shutil.copy2(RAIZ / "distribucion" / "LEEME.txt", APP / "LEEME.txt")
    copiar_licencias(APP / "licencias", platform_tools)
    zip_codigo_fuente(APP / "licencias" / "codigo-fuente-gogocam.zip")

    for nombre in ("GoGoCam.exe", "_internal/vendor/adb.exe", f"_internal/vendor/{SERVIDOR_LOCAL.name}",
                   "_internal/recursos/gogocam.ico", "LEEME.txt"):
        if not (APP / nombre).is_file():
            raise SystemExit(f"Falta {nombre} en {APP}: el paquete quedó incompleto.")

    destino = DIST / f"GoGoCam-{__version__}.zip"
    destino.unlink(missing_ok=True)
    comprimir(APP, destino)
    peso = sum(f.stat().st_size for f in APP.rglob("*") if f.is_file())
    print(f"Listo: {destino} ({destino.stat().st_size / 2**20:.0f} MB; {peso / 2**20:.0f} MB descomprimido)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
