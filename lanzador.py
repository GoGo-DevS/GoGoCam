"""Punto de entrada de GoGoCam.exe. PyInstaller no corre paquetes con `-m`, así que
este archivo llama al mismo main() que `python -m gogocam`."""
import sys

from gogocam.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
