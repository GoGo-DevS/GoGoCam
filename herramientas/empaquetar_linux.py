"""Arma GoGoCam para Linux: dist/GoGoCam-<versión>-linux.tar.gz.

    .\\.venv\\Scripts\\python.exe herramientas\\empaquetar_linux.py

Es el código fuente con su instalador: instalar.sh baja las librerías de Python que
correspondan al Python de cada distribución, así que el paquete se puede armar desde
Windows. Se encarga de lo que Windows rompe sin avisar: los saltos de línea (un .sh con
CRLF no corre: «bad interpreter») y el permiso de ejecución de los .sh.
"""
from __future__ import annotations

import hashlib
import io
import sys
import tarfile
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from gogocam import __version__  # noqa: E402

DIST = RAIZ / "dist"
CARPETA = f"GoGoCam-{__version__}-linux"
LINUX = RAIZ / "distribucion" / "linux"
SERVIDOR = RAIZ / "vendor" / "scrcpy-server-v5.0.1"
TEXTO = {".py", ".sh", ".txt", ".md", ""}  # "" = LICENSE


def archivos() -> list[tuple[Path, str]]:
    """(origen, ruta dentro de la carpeta del paquete)."""
    lista = [(p, f"gogocam/{p.name}") for p in sorted((RAIZ / "gogocam").glob("*.py"))]
    lista += [(SERVIDOR, f"vendor/{SERVIDOR.name}"),
              (RAIZ / "vendor" / "LICENSE-scrcpy.txt", "vendor/LICENSE-scrcpy.txt"),
              (RAIZ / "vendor" / "SHA256SUMS.txt", "vendor/SHA256SUMS.txt")]
    lista += [(p, f"recursos/{p.name}") for p in sorted((RAIZ / "recursos").glob("*.png"))]
    lista += [(RAIZ / "requirements-linux.txt", "requirements-linux.txt"), (RAIZ / "LICENSE", "LICENSE")]
    lista += [(LINUX / n, n) for n in ("instalar.sh", "desinstalar.sh", "LEEME.txt", "LICENCIAS.txt")]
    return lista


def contenido(origen: Path) -> bytes:
    datos = origen.read_bytes()
    if origen.suffix in TEXTO:
        datos = datos.replace(b"\r\n", b"\n")
    return datos


def verificar_servidor() -> None:
    sumas = (RAIZ / "vendor" / "SHA256SUMS.txt").read_text(encoding="utf-8")
    real = hashlib.sha256(SERVIDOR.read_bytes()).hexdigest()
    if f"{real}  {SERVIDOR.name}" not in sumas:
        raise SystemExit(f"{SERVIDOR.name} no coincide con vendor/SHA256SUMS.txt: no lo empaqueto.")


def armar(destino: Path) -> None:
    ahora = int(time.time())
    carpetas = set()
    with tarfile.open(destino, "w:gz", format=tarfile.PAX_FORMAT) as tar:
        for origen, ruta in archivos():
            if not origen.is_file():
                raise SystemExit(f"Falta {origen}: no armo un paquete incompleto.")
            partes = ruta.split("/")[:-1]
            for i in range(len(partes) + 1):
                carpeta = "/".join([CARPETA, *partes[:i]])
                if carpeta not in carpetas:
                    carpetas.add(carpeta)
                    info = tarfile.TarInfo(carpeta)
                    info.type, info.mode, info.mtime = tarfile.DIRTYPE, 0o755, ahora
                    tar.addfile(info)
            datos = contenido(origen)
            info = tarfile.TarInfo(f"{CARPETA}/{ruta}")
            info.size, info.mtime = len(datos), ahora
            info.mode = 0o755 if ruta.endswith(".sh") else 0o644
            tar.addfile(info, io.BytesIO(datos))


def revisar(paquete: Path) -> None:
    """Lee el .tar.gz armado y comprueba lo que en Linux rompería la instalación."""
    with tarfile.open(paquete, "r:gz") as tar:
        miembros = {m.name: m for m in tar.getmembers()}
        for nombre in ("instalar.sh", "desinstalar.sh"):
            m = miembros[f"{CARPETA}/{nombre}"]
            if m.mode & 0o111 != 0o111:
                raise SystemExit(f"{nombre} quedó sin permiso de ejecución.")
            if not tar.extractfile(m).read().startswith(b"#!/usr/bin/env bash\n"):
                raise SystemExit(f"{nombre} no empieza con #!/usr/bin/env bash y salto LF.")
        for m in miembros.values():
            if m.isfile() and Path(m.name).suffix in TEXTO and b"\r" in tar.extractfile(m).read():
                raise SystemExit(f"{m.name} tiene saltos de línea de Windows.")
        servidor = tar.extractfile(miembros[f"{CARPETA}/vendor/{SERVIDOR.name}"]).read()
        if hashlib.sha256(servidor).digest() != hashlib.sha256(SERVIDOR.read_bytes()).digest():
            raise SystemExit("El servidor de scrcpy dentro del paquete no es el original.")


def main() -> int:
    verificar_servidor()
    DIST.mkdir(exist_ok=True)
    destino = DIST / f"{CARPETA}.tar.gz"
    armar(destino)
    revisar(destino)
    print(f"Listo: {destino} ({destino.stat().st_size / 2**20:.1f} MB, {len(archivos())} archivos)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
