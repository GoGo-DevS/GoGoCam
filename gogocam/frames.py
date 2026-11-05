"""Transformaciones de cuadros I420 (YUV 4:2:0 planar) sin convertir a RGB.

Un cuadro I420 plano trae tres planos seguidos: Y (ancho x alto), U y V
(ancho/2 x alto/2 cada uno). Rotar o voltear plano por plano evita la
conversión a RGB, que es lo que más CPU gasta.
"""
from __future__ import annotations

import numpy as np

ROTACIONES = (0, 90, 180, 270)


def tamano_salida(ancho: int, alto: int, rotacion: int) -> tuple[int, int]:
    """Ancho y alto del cuadro después de rotarlo."""
    return (alto, ancho) if rotacion in (90, 270) else (ancho, alto)


def _girar(plano: np.ndarray, rotacion: int, espejo: bool) -> np.ndarray:
    # np.rot90 gira en sentido antihorario con k > 0; aquí la rotación es horaria.
    k = -(rotacion // 90)
    if k:
        plano = np.rot90(plano, k)
    if espejo:
        # Se voltea DESPUÉS de rotar: el espejo es izquierda-derecha de la imagen final.
        plano = plano[:, ::-1]
    return plano


def transformar_i420(
    datos: np.ndarray, ancho: int, alto: int, rotacion: int = 0, espejo: bool = False
) -> tuple[np.ndarray, int, int]:
    """Rota (horario) y/o voltea un cuadro I420. Devuelve (datos, ancho, alto)."""
    if rotacion not in ROTACIONES:
        raise ValueError(f"rotación no soportada: {rotacion}")
    if ancho % 2 or alto % 2:
        raise ValueError(f"I420 necesita ancho y alto pares: {ancho}x{alto}")
    plano = datos.reshape(-1)
    tam_y = ancho * alto
    tam_c = tam_y // 4
    if plano.size != tam_y + 2 * tam_c:
        raise ValueError(f"tamaño I420 inválido: {plano.size} bytes para {ancho}x{alto}")
    if rotacion == 0 and not espejo:
        return plano, ancho, alto

    y = plano[:tam_y].reshape(alto, ancho)
    u = plano[tam_y : tam_y + tam_c].reshape(alto // 2, ancho // 2)
    v = plano[tam_y + tam_c :].reshape(alto // 2, ancho // 2)
    salida = np.concatenate([_girar(p, rotacion, espejo).ravel() for p in (y, u, v)])
    nuevo_ancho, nuevo_alto = tamano_salida(ancho, alto, rotacion)
    return salida, nuevo_ancho, nuevo_alto


def transformar_rgb(imagen: np.ndarray, rotacion: int = 0, espejo: bool = False) -> np.ndarray:
    """Igual que transformar_i420, para la vista previa en RGB (alto x ancho x 3)."""
    if rotacion not in ROTACIONES:
        raise ValueError(f"rotación no soportada: {rotacion}")
    return np.ascontiguousarray(_girar(imagen, rotacion, espejo))


def a_ppm(imagen: np.ndarray) -> bytes:
    """Imagen RGB (alto x ancho x 3, uint8) a PPM binario, que Tk muestra sin Pillow."""
    alto, ancho = imagen.shape[:2]
    return b"P6 %d %d 255\n" % (ancho, alto) + np.ascontiguousarray(imagen, dtype=np.uint8).tobytes()
