"""Prueba la cadena completa SIN teléfono: un "teléfono falso" local manda H.264
con el mismo protocolo de scrcpy v5, GoGoCam lo decodifica y lo publica en
«OBS Virtual Camera», y ffmpeg lee esa cámara de vuelta y guarda una captura.

    python herramientas/prueba_sin_telefono.py CARPETA_DE_SALIDA

Necesita ffmpeg en el PATH y OBS Virtual Camera instalada (con OBS cerrado o
sin su cámara virtual encendida). No usa adb ni toca ningún teléfono.
"""
from __future__ import annotations

import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import av  # noqa: E402

from gogocam.core import Ajustes, Transmision  # noqa: E402
from gogocam.protocolo import CODEC_H264, FLAG_CLAVE, FLAG_CONFIG  # noqa: E402

ANCHO, ALTO, FPS = 1280, 720, 30


def generar_h264(ffmpeg: str, destino: Path) -> bytes:
    subprocess.run(
        [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
         "-i", f"testsrc2=size={ANCHO}x{ALTO}:rate={FPS}", "-t", "4",
         "-c:v", "libx264", "-profile:v", "baseline", "-g", str(FPS), "-bf", "0",
         "-bsf:v", "h264_mp4toannexb", "-f", "h264", str(destino)],
        check=True,
    )
    return destino.read_bytes()


def separar_config(au: bytes) -> tuple[bytes, bytes]:
    """Divide una unidad de acceso en (SPS/PPS, resto), como lo entrega MediaCodec."""
    posiciones = []
    i = 0
    while (i := au.find(b"\x00\x00\x01", i)) != -1:
        inicio = i - 1 if i > 0 and au[i - 1] == 0 else i
        posiciones.append((inicio, au[i + 3] & 0x1F))
        i += 3
    config, resto = b"", b""
    for n, (inicio, tipo) in enumerate(posiciones):
        fin = posiciones[n + 1][0] if n + 1 < len(posiciones) else len(au)
        if tipo in (7, 8):
            config += au[inicio:fin]
        else:
            resto += au[inicio:fin]
    return config, resto


def _leer_control(conexion: socket.socket, recibido: bytearray) -> None:
    with conexion:
        while True:
            try:
                datos = conexion.recv(4096)
            except OSError:
                return
            if not datos:
                return
            recibido.extend(datos)


def telefono_falso(servidor: socket.socket, paquetes: list[tuple[bytes, bool]], parar: threading.Event,
                   control_recibido: bytearray | None = None):
    """Como el servidor real: acepta el video (y le manda el byte de prueba), después el
    control, y recién ahí manda video. Lo que llega por el control queda en control_recibido."""
    conexion, _ = servidor.accept()
    with conexion:
        conexion.sendall(b"\x00")
        control, _ = servidor.accept()
        threading.Thread(target=_leer_control, args=(control, control_recibido if control_recibido is not None
                                                     else bytearray()), daemon=True).start()
        conexion.sendall(struct.pack(">I", CODEC_H264) + struct.pack(">III", 0x80000000, ANCHO, ALTO))
        pts = 0
        try:
            while not parar.is_set():
                for datos, clave in paquetes:
                    if parar.is_set():
                        return
                    if clave:
                        config, datos = separar_config(datos)
                        if config:
                            conexion.sendall(struct.pack(">QI", FLAG_CONFIG, len(config)) + config)
                    flags = pts | (FLAG_CLAVE if clave else 0)
                    conexion.sendall(struct.pack(">QI", flags, len(datos)) + datos)
                    pts += 1_000_000 // FPS
                    time.sleep(1 / FPS)
        except OSError:
            return  # GoGoCam cerró la conexión: fin normal de la prueba


class TransmisionDePrueba(Transmision):
    puerto = 0

    def _preparar_telefono(self) -> int:
        self._avisar("info", "Teléfono falso listo.")
        return self.puerto


def capturar_camara_virtual(ffmpeg: str, destino: Path) -> bool:
    r = subprocess.run(
        [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-f", "dshow",
         "-i", "video=OBS Virtual Camera", "-frames:v", "1", str(destino)],
        capture_output=True, text=True, timeout=30,
    )
    if r.returncode != 0:
        print("ffmpeg no pudo leer la cámara virtual:", r.stderr.strip())
    return r.returncode == 0 and destino.is_file()


def correr(rotacion: int, salida: Path, ffmpeg: str, paquetes) -> bool:
    servidor = socket.create_server(("127.0.0.1", 0))
    parar = threading.Event()
    hilo = threading.Thread(target=telefono_falso, args=(servidor, paquetes, parar), daemon=True)
    hilo.start()

    t = TransmisionDePrueba(Ajustes(fps=FPS, rotacion=rotacion, vista_previa=True))
    t.puerto = servidor.getsockname()[1]
    t.iniciar()
    limite = time.monotonic() + 10
    while t.cuadros < FPS and time.monotonic() < limite and t.activa:
        time.sleep(0.1)
    captura = salida / f"camara_virtual_rot{rotacion}.png"
    leida = capturar_camara_virtual(ffmpeg, captura)
    time.sleep(1.2)
    cuadros, fps, dims, muestra = t.cuadros, t.fps, t.tamano_salida, t.vista_previa
    t.detener()
    parar.set()
    servidor.close()
    while not t.eventos.empty():
        print("  ", t.eventos.get())
    if muestra:
        (salida / f"vista_previa_rot{rotacion}.ppm").write_bytes(muestra)
    esperado = (ALTO, ANCHO) if rotacion in (90, 270) else (ANCHO, ALTO)
    ok = cuadros > FPS and dims == esperado and leida and not t.error
    print(f"rot={rotacion}: cuadros={cuadros} fps={fps:.1f} salida={dims} esperado={esperado} "
          f"captura={'OK ' + str(captura) if leida else 'FALLÓ'} error={t.error!r} -> {'OK' if ok else 'FALLA'}")
    return ok


def main() -> int:
    salida = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.mkdtemp(prefix="gogocam-"))
    salida.mkdir(parents=True, exist_ok=True)
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        print("Falta ffmpeg en el PATH.")
        return 2
    crudo = generar_h264(ffmpeg, salida / "prueba.h264")
    analizador = av.CodecContext.create("h264", "r")
    paquetes = [(bytes(p), bool(p.is_keyframe)) for p in analizador.parse(crudo)]
    print(f"{len(paquetes)} paquetes H.264 de prueba; salida en {salida}")
    resultados = [correr(rot, salida, ffmpeg, paquetes) for rot in (0, 90)]
    return 0 if all(resultados) else 1


if __name__ == "__main__":
    sys.exit(main())
