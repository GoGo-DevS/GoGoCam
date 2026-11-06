"""Arranque de GoGoCam.

    pythonw -m gogocam                  abre la ventana
    python  -m gogocam --prueba 10      transmite 10 s sin ventana e informa
    python  -m gogocam --diagnostico    revisa que no falte nada, sin tocar el teléfono

En el .exe empaquetado son los mismos argumentos: GoGoCam.exe --diagnostico.
En Linux, instalar.sh deja el comando `gogocam` (gogocam --diagnostico).
"""
from __future__ import annotations

import argparse
import logging
import logging.handlers
import os
import sys
import time
from pathlib import Path

if sys.platform == "win32":
    CARPETA_DATOS = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "GoGoCam"
else:  # Linux: donde instalar.sh deja la app (estándar XDG)
    CARPETA_DATOS = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share") / "gogocam"


def configurar_registro() -> Path:
    CARPETA_DATOS.mkdir(parents=True, exist_ok=True)
    archivo = CARPETA_DATOS / "gogocam.log"
    manejador = logging.handlers.RotatingFileHandler(archivo, maxBytes=1_000_000, backupCount=2, encoding="utf-8")
    manejador.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    raiz = logging.getLogger()
    raiz.setLevel(logging.INFO)
    raiz.addHandler(manejador)
    return archivo


def prueba_sin_ventana(segundos: float, rotacion: int, camara: str, tamano: str) -> int:
    from .core import Ajustes, Transmision

    t = Transmision(Ajustes(camara=camara, tamano=tamano, rotacion=rotacion, vista_previa=False))
    t.iniciar()
    inicio = None
    while t.activa:
        while not t.eventos.empty():
            tipo, texto = t.eventos.get()
            print(f"[{tipo}] {texto}", flush=True)
            if tipo == "ok" and inicio is None:
                inicio = time.monotonic()
        if inicio is not None and time.monotonic() - inicio >= segundos:
            break
        time.sleep(0.1)
    cuadros, fps, dims = t.cuadros, t.fps, t.tamano_salida
    t.detener()
    while not t.eventos.empty():
        tipo, texto = t.eventos.get()
        print(f"[{tipo}] {texto}", flush=True)
    print(f"RESULTADO cuadros={cuadros} fps={fps:.1f} salida={dims[0]}x{dims[1]} error={t.error!r}")
    return 0 if cuadros > 0 and not t.error else 1


def main() -> int:
    parser = argparse.ArgumentParser(prog="gogocam", description="La cámara del teléfono como cámara web.")
    parser.add_argument("--prueba", type=float, metavar="SEGUNDOS", help="transmitir sin ventana y salir")
    parser.add_argument("--rotacion", type=int, default=0, choices=(0, 90, 180, 270))
    parser.add_argument("--camara", default="back", choices=("back", "front"))
    parser.add_argument("--tamano", default="1920x1080")
    parser.add_argument("--minimizada", action="store_true", help="abrir la ventana minimizada")
    parser.add_argument("--diagnostico", action="store_true", help="revisar que no falte nada (no toca el teléfono)")
    args = parser.parse_args()

    archivo = configurar_registro()
    if args.diagnostico:
        from .diagnostico import revisar

        resultados = revisar()
        for nombre, ok, detalle in resultados:
            print(f"{'OK   ' if ok else 'FALLA'} {nombre}: {detalle}")
        print(f"registro: {archivo}")
        return 0 if all(ok for _, ok, _ in resultados) else 1
    if args.prueba:
        print(f"registro: {archivo}")
        return prueba_sin_ventana(args.prueba, args.rotacion, args.camara, args.tamano)

    from .ui import ejecutar

    ejecutar(CARPETA_DATOS, minimizada=args.minimizada)
    return 0


if __name__ == "__main__":
    sys.exit(main())
