"""Dibuja el ícono de GoGoCam (colores de GoGoDevS) y lo guarda en recursos/.

    python herramientas/generar_icono.py

Sin Pillow: se dibuja con numpy (con suavizado por supermuestreo) y se escribe el
PNG y el ICO a mano. El ICO lleva 16, 24, 32, 48 y 64 px en BMP y 256 px en PNG.
"""
from __future__ import annotations

import struct
import zlib
from pathlib import Path

import numpy as np

RECURSOS = Path(__file__).resolve().parent.parent / "recursos"
NAVY_CLARO = (0x16, 0x26, 0x47)
NAVY = (0x0A, 0x14, 0x28)
AMBAR = (0xFF, 0xB6, 0x27)
AZUL = (0x25, 0x63, 0xEB)
AZUL_CLARO = (0x60, 0x9D, 0xFF)
LENTE = (0x05, 0x0A, 0x14)
BLANCO = (0xF5, 0xF6, 0xF8)


def dibujar(lado: int, sobremuestreo: int = 4) -> np.ndarray:
    """Devuelve una imagen RGBA (lado x lado x 4, uint8)."""
    n = lado * sobremuestreo
    yy, xx = np.mgrid[0:n, 0:n]
    x = (xx + 0.5) / n
    y = (yy + 0.5) / n
    rgb = np.zeros((n, n, 3), np.float32)
    alfa = np.zeros((n, n), np.float32)

    def pintar(mascara, color):
        rgb[mascara] = color

    # Cuadrado redondeado con degradado diagonal
    margen, radio = 0.04, 0.23
    dx = np.maximum(np.abs(x - 0.5) - (0.5 - margen - radio), 0)
    dy = np.maximum(np.abs(y - 0.5) - (0.5 - margen - radio), 0)
    fondo = dx ** 2 + dy ** 2 <= radio ** 2
    t = ((x + y) / 2)[..., None]
    degradado = np.array(NAVY_CLARO, np.float32) * (1 - t) + np.array(NAVY, np.float32) * t
    rgb[fondo] = degradado[fondo]
    alfa[fondo] = 1.0

    # Lente: anillo ámbar, vidrio oscuro, iris azul con degradado, pupila y brillo
    d = np.hypot(x - 0.5, y - 0.53)
    pintar(fondo & (d <= 0.315), AMBAR)
    pintar(fondo & (d <= 0.24), LENTE)
    iris = fondo & (d <= 0.165) & (d > 0.085)
    mezcla = np.clip((y - 0.37) / 0.32, 0, 1)[..., None]
    tono_iris = np.array(AZUL_CLARO, np.float32) * (1 - mezcla) + np.array(AZUL, np.float32) * mezcla
    rgb[iris] = tono_iris[iris]
    pintar(fondo & (np.hypot(x - 0.445, y - 0.47) <= 0.045), BLANCO)
    # Luz de "transmitiendo"
    pintar(fondo & (np.hypot(x - 0.80, y - 0.20) <= 0.055), AMBAR)

    s = sobremuestreo
    rgb = rgb.reshape(lado, s, lado, s, 3).mean(axis=(1, 3))
    alfa = alfa.reshape(lado, s, lado, s).mean(axis=(1, 3))
    # rgb premultiplicado por el borde: se des-premultiplica para que el contorno no oscurezca
    con_alfa = np.where(alfa[..., None] > 0, rgb / np.maximum(alfa[..., None], 1e-6), 0)
    salida = np.dstack([np.clip(np.rint(con_alfa), 0, 255), np.rint(alfa * 255)])
    return salida.astype(np.uint8)


def a_png(imagen: np.ndarray) -> bytes:
    alto, ancho = imagen.shape[:2]
    crudo = b"".join(b"\x00" + imagen[f].tobytes() for f in range(alto))

    def bloque(tipo: bytes, datos: bytes) -> bytes:
        return struct.pack(">I", len(datos)) + tipo + datos + struct.pack(">I", zlib.crc32(tipo + datos))

    cabecera = struct.pack(">IIBBBBB", ancho, alto, 8, 6, 0, 0, 0)  # 8 bits, RGBA
    return (b"\x89PNG\r\n\x1a\n" + bloque(b"IHDR", cabecera)
            + bloque(b"IDAT", zlib.compress(crudo, 9)) + bloque(b"IEND", b""))


def a_bmp_de_icono(imagen: np.ndarray) -> bytes:
    """Imagen de ICO en formato DIB: BGRA de abajo hacia arriba + máscara AND vacía."""
    alto, ancho = imagen.shape[:2]
    cabecera = struct.pack("<IiiHHIIiiII", 40, ancho, alto * 2, 1, 32, 0, 0, 0, 0, 0, 0)
    bgra = imagen[::-1, :, [2, 1, 0, 3]].tobytes()
    fila_mascara = ((ancho + 31) // 32) * 4
    return cabecera + bgra + b"\x00" * (fila_mascara * alto)


def a_ico(imagenes: dict[int, bytes]) -> bytes:
    cabecera = struct.pack("<HHH", 0, 1, len(imagenes))
    entradas, datos = b"", b""
    desplazamiento = 6 + 16 * len(imagenes)
    for lado, contenido in sorted(imagenes.items()):
        medida = 0 if lado >= 256 else lado
        entradas += struct.pack("<BBBBHHII", medida, medida, 0, 0, 1, 32, len(contenido),
                                desplazamiento + len(datos))
        datos += contenido
    return cabecera + entradas + datos


def main() -> None:
    RECURSOS.mkdir(exist_ok=True)
    grande = dibujar(256)
    (RECURSOS / "gogocam.png").write_bytes(a_png(grande))
    for lado in (16, 32, 48):  # para la ventana (Tk iconphoto); el .ico es para los accesos directos
        (RECURSOS / f"gogocam-{lado}.png").write_bytes(a_png(dibujar(lado, 8)))
    imagenes = {lado: a_bmp_de_icono(dibujar(lado, 8)) for lado in (16, 24, 32, 48, 64)}
    imagenes[256] = a_png(grande)
    (RECURSOS / "gogocam.ico").write_bytes(a_ico(imagenes))
    print("listo:", RECURSOS / "gogocam.ico", RECURSOS / "gogocam.png")


if __name__ == "__main__":
    main()
