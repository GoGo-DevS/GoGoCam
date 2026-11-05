import unittest

import numpy as np

from gogocam.frames import (
    a_ppm, aplicar_tabla_y, tabla_brillo_contraste, tamano_salida, transformar_i420, transformar_rgb,
)


def cuadro_i420(ancho: int, alto: int):
    """I420 con valores distintos por plano para poder seguir cada píxel."""
    y = np.arange(ancho * alto, dtype=np.uint8).reshape(alto, ancho)
    u = (np.arange(ancho * alto // 4, dtype=np.uint8) + 100).reshape(alto // 2, ancho // 2)
    v = (np.arange(ancho * alto // 4, dtype=np.uint8) + 200).reshape(alto // 2, ancho // 2)
    return np.concatenate([y.ravel(), u.ravel(), v.ravel()]), y, u, v


def planos(datos, ancho, alto):
    tam_y, tam_c = ancho * alto, ancho * alto // 4
    return (
        datos[:tam_y].reshape(alto, ancho),
        datos[tam_y : tam_y + tam_c].reshape(alto // 2, ancho // 2),
        datos[tam_y + tam_c :].reshape(alto // 2, ancho // 2),
    )


class PruebasFrames(unittest.TestCase):
    def test_sin_cambios_devuelve_lo_mismo(self):
        datos, *_ = cuadro_i420(8, 4)
        salida, ancho, alto = transformar_i420(datos, 8, 4)
        self.assertEqual((ancho, alto), (8, 4))
        np.testing.assert_array_equal(salida, datos)

    def test_rotacion_90_horaria(self):
        datos, y, u, v = cuadro_i420(8, 4)
        salida, ancho, alto = transformar_i420(datos, 8, 4, rotacion=90)
        self.assertEqual((ancho, alto), (4, 8))
        y2, u2, v2 = planos(salida, ancho, alto)
        # Horario: la primera fila nueva es la primera columna original, de abajo hacia arriba.
        np.testing.assert_array_equal(y2[0], y[::-1, 0])
        np.testing.assert_array_equal(u2[0], u[::-1, 0])
        np.testing.assert_array_equal(v2[0], v[::-1, 0])

    def test_cuatro_rotaciones_vuelven_al_original(self):
        datos, *_ = cuadro_i420(8, 4)
        actual, ancho, alto = datos, 8, 4
        for _ in range(4):
            actual, ancho, alto = transformar_i420(actual, ancho, alto, rotacion=90)
        self.assertEqual((ancho, alto), (8, 4))
        np.testing.assert_array_equal(actual, datos)

    def test_espejo_es_izquierda_derecha_de_la_imagen_final(self):
        datos, y, *_ = cuadro_i420(8, 4)
        salida, ancho, alto = transformar_i420(datos, 8, 4, rotacion=90, espejo=True)
        y2, *_ = planos(salida, ancho, alto)
        rotada = np.rot90(y, -1)
        np.testing.assert_array_equal(y2, rotada[:, ::-1])

    def test_180(self):
        datos, y, *_ = cuadro_i420(8, 4)
        salida, ancho, alto = transformar_i420(datos, 8, 4, rotacion=180)
        y2, *_ = planos(salida, ancho, alto)
        np.testing.assert_array_equal(y2, y[::-1, ::-1])

    def test_errores(self):
        datos, *_ = cuadro_i420(8, 4)
        with self.assertRaises(ValueError):
            transformar_i420(datos, 8, 4, rotacion=45)
        with self.assertRaises(ValueError):
            transformar_i420(datos[:-1], 8, 4, rotacion=90)
        with self.assertRaises(ValueError):
            transformar_i420(datos, 7, 4)

    def test_tamano_salida(self):
        self.assertEqual(tamano_salida(1920, 1080, 90), (1080, 1920))
        self.assertEqual(tamano_salida(1920, 1080, 180), (1920, 1080))

    def test_rgb_y_ppm(self):
        rgb = np.zeros((2, 4, 3), dtype=np.uint8)
        rgb[0, 0] = (255, 0, 0)
        girada = transformar_rgb(rgb, 90)
        self.assertEqual(girada.shape, (4, 2, 3))
        self.assertEqual(tuple(girada[0, 1]), (255, 0, 0))
        ppm = a_ppm(girada)
        self.assertTrue(ppm.startswith(b"P6 2 4 255\n"))
        self.assertEqual(len(ppm), len(b"P6 2 4 255\n") + 2 * 4 * 3)


class PruebasBrilloContraste(unittest.TestCase):
    def test_neutro_no_hace_nada(self):
        self.assertIsNone(tabla_brillo_contraste(0, 100))

    def test_brillo_suma_y_se_corta_en_los_bordes(self):
        tabla = tabla_brillo_contraste(30, 100)
        self.assertEqual(tabla[100], 130)
        self.assertEqual(tabla[240], 255)
        self.assertEqual(tabla_brillo_contraste(-30, 100)[10], 0)

    def test_contraste_estira_alrededor_del_gris(self):
        tabla = tabla_brillo_contraste(0, 150)
        self.assertEqual(tabla[128], 128)  # el gris medio no se mueve
        self.assertEqual(tabla[148], 158)  # +20 -> +30
        self.assertEqual(tabla[108], 98)
        menos = tabla_brillo_contraste(0, 50)
        self.assertEqual(menos[228], 178)  # +100 -> +50

    def test_solo_toca_la_luz_no_el_color(self):
        ancho, alto = 4, 2
        datos = cuadro_i420(ancho, alto)[0]
        color_antes = datos[ancho * alto:].copy()
        tabla = tabla_brillo_contraste(10, 100)
        y_antes = datos[: ancho * alto].copy()
        salida = aplicar_tabla_y(datos, ancho, alto, tabla)
        np.testing.assert_array_equal(salida[: ancho * alto], y_antes + 10)
        np.testing.assert_array_equal(salida[ancho * alto:], color_antes)


if __name__ == "__main__":
    unittest.main()
