"""Lectura del flujo de video del servidor de scrcpy v5.0.1.

Verificado contra el código del servidor (Streamer.java y DesktopConnection.java
de la etiqueta v5.0.1). Con túnel "forward", en el socket de video llegan:

1. un byte de prueba (lo lee quien conecta, antes de crear el LectorVideo);
2. el id del códec (u32), o 0 / 1 si el teléfono desactivó el video o falló;
3. paquetes de 12 bytes de cabecera, distinguidos por el bit más alto:
   - sesión (bit 63 = 1): [flags u32][ancho u32][alto u32];
   - medio  (bit 63 = 0): [pts y flags u64][tamaño u32] + datos.
     Bit 62 = paquete de configuración (SPS/PPS), bit 61 = cuadro clave.

Todo en big-endian.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass

CODEC_H264 = 0x68323634  # "h264"
FLAG_SESION = 1 << 63
FLAG_CONFIG = 1 << 62
FLAG_CLAVE = 1 << 61
MASCARA_PTS = FLAG_CLAVE - 1
TAMANO_MAXIMO_PAQUETE = 32 * 1024 * 1024  # un cuadro H.264 nunca se acerca a esto


class ErrorDeFlujo(Exception):
    """El teléfono mandó algo que no corresponde al protocolo."""


class VideoDesactivado(Exception):
    """El teléfono avisó que no puede (código 1) o no quiere (código 0) mandar video."""

    def __init__(self, codigo: int):
        super().__init__(f"video desactivado por el teléfono (código {codigo})")
        self.codigo = codigo


@dataclass(frozen=True)
class Sesion:
    ancho: int
    alto: int


@dataclass(frozen=True)
class Paquete:
    datos: bytes
    pts: int
    clave: bool


def recibir_exacto(sock, n: int) -> bytes:
    """Lee exactamente n bytes o lanza ConnectionError si el otro lado cierra."""
    buf = bytearray()
    while len(buf) < n:
        trozo = sock.recv(n - len(buf))
        if not trozo:
            raise ConnectionError("el teléfono cerró la conexión")
        buf += trozo
    return bytes(buf)


class LectorVideo:
    """Lee códec, sesiones y paquetes H.264 del socket de video."""

    def __init__(self, sock):
        self._sock = sock
        self._config = b""

    def leer_codec(self) -> int:
        (codec,) = struct.unpack(">I", recibir_exacto(self._sock, 4))
        if codec in (0, 1):
            raise VideoDesactivado(codec)
        if codec != CODEC_H264:
            raise ErrorDeFlujo(f"códec inesperado 0x{codec:08x} (se pidió H.264)")
        return codec

    def siguiente(self) -> Sesion | Paquete:
        while True:
            cabecera = recibir_exacto(self._sock, 12)
            (pts_y_flags,) = struct.unpack(">Q", cabecera[:8])
            if pts_y_flags & FLAG_SESION:
                ancho, alto = struct.unpack(">II", cabecera[4:12])
                return Sesion(ancho, alto)

            (tamano,) = struct.unpack(">I", cabecera[8:12])
            if tamano == 0 or tamano > TAMANO_MAXIMO_PAQUETE:
                raise ErrorDeFlujo(f"tamaño de paquete inválido: {tamano}")
            datos = recibir_exacto(self._sock, tamano)

            if pts_y_flags & FLAG_CONFIG:
                # SPS/PPS: igual que el cliente de scrcpy, se pegan al próximo paquete.
                self._config = datos
                continue
            if self._config:
                datos = self._config + datos
                self._config = b""
            return Paquete(datos, pts_y_flags & MASCARA_PTS, bool(pts_y_flags & FLAG_CLAVE))
