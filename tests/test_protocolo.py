import random
import struct
import unittest

from gogocam.protocolo import (
    CODEC_H264, FLAG_CLAVE, FLAG_CONFIG, ErrorDeFlujo, LectorVideo, Paquete, Sesion,
    VideoDesactivado,
)


class SocketFalso:
    """Entrega los bytes en trozos de tamaño al azar, como un socket real."""

    def __init__(self, datos: bytes, semilla: int = 7):
        self._datos = datos
        self._pos = 0
        self._azar = random.Random(semilla)

    def recv(self, n: int) -> bytes:
        if self._pos >= len(self._datos):
            return b""
        cuanto = min(n, self._azar.randint(1, 5))
        trozo = self._datos[self._pos : self._pos + cuanto]
        self._pos += len(trozo)
        return trozo


def sesion(ancho: int, alto: int) -> bytes:
    return struct.pack(">III", 0x80000000, ancho, alto)


def paquete(datos: bytes, pts: int = 0, config: bool = False, clave: bool = False) -> bytes:
    flags = FLAG_CONFIG if config else pts | (FLAG_CLAVE if clave else 0)
    return struct.pack(">QI", flags, len(datos)) + datos


class PruebasProtocolo(unittest.TestCase):
    def test_codec_h264(self):
        lector = LectorVideo(SocketFalso(struct.pack(">I", CODEC_H264)))
        self.assertEqual(lector.leer_codec(), CODEC_H264)

    def test_video_desactivado_y_error(self):
        for codigo in (0, 1):
            with self.subTest(codigo=codigo):
                lector = LectorVideo(SocketFalso(struct.pack(">I", codigo)))
                with self.assertRaises(VideoDesactivado) as ctx:
                    lector.leer_codec()
                self.assertEqual(ctx.exception.codigo, codigo)

    def test_codec_inesperado(self):
        lector = LectorVideo(SocketFalso(struct.pack(">I", 0x68323635)))  # h265
        with self.assertRaises(ErrorDeFlujo):
            lector.leer_codec()

    def test_sesion_config_y_paquetes(self):
        flujo = (
            sesion(1920, 1080)
            + paquete(b"SPSPPS", config=True)
            + paquete(b"IDR", pts=1000, clave=True)
            + paquete(b"P1", pts=34333)
            + sesion(1080, 1920)
        )
        lector = LectorVideo(SocketFalso(flujo))
        self.assertEqual(lector.siguiente(), Sesion(1920, 1080))
        # La configuración se pega al paquete siguiente, y solo a ese.
        self.assertEqual(lector.siguiente(), Paquete(b"SPSPPSIDR", 1000, True))
        self.assertEqual(lector.siguiente(), Paquete(b"P1", 34333, False))
        self.assertEqual(lector.siguiente(), Sesion(1080, 1920))

    def test_corte_a_mitad_de_paquete(self):
        flujo = paquete(b"0123456789", pts=1)[:-3]
        with self.assertRaises(ConnectionError):
            LectorVideo(SocketFalso(flujo)).siguiente()

    def test_tamano_invalido(self):
        flujo = struct.pack(">QI", 5, 0)
        with self.assertRaises(ErrorDeFlujo):
            LectorVideo(SocketFalso(flujo)).siguiente()


if __name__ == "__main__":
    unittest.main()
