import json
import tempfile
import unittest
from pathlib import Path

from gogocam.core import ZOOM_PASO_MAX, Ajustes
from gogocam.ui import TAMANOS, cargar_ajustes, guardar_ajustes, partes_de_tamano


class PruebasAjustes(unittest.TestCase):
    def setUp(self):
        self.carpeta = tempfile.TemporaryDirectory()
        self.archivo = Path(self.carpeta.name) / "ajustes.json"

    def tearDown(self):
        self.carpeta.cleanup()

    def escribir(self, datos) -> Ajustes:
        self.archivo.write_text(json.dumps(datos), encoding="utf-8")
        return cargar_ajustes(self.archivo)

    def test_sin_archivo_o_roto_da_los_de_fabrica(self):
        self.assertEqual(cargar_ajustes(self.archivo), Ajustes())
        self.archivo.write_text("{no es json", encoding="utf-8")
        self.assertEqual(cargar_ajustes(self.archivo), Ajustes())
        self.assertEqual(self.escribir([1, 2, 3]), Ajustes())

    def test_ida_y_vuelta(self):
        original = Ajustes(camara="front", tamano="1440x1080", fps=20, bitrate=20_000_000, rotacion=90,
                           espejo=True, brillo=-12, contraste=135, zoom_paso=7, linterna=True,
                           vista_previa=False, autoiniciar=True, tema_oscuro=False)
        guardar_ajustes(self.archivo, original)
        self.assertEqual(cargar_ajustes(self.archivo), original)

    def test_valores_fuera_de_rango_se_limitan_o_se_ignoran(self):
        a = self.escribir({"brillo": 500, "contraste": 1, "zoom_paso": -4, "fps": 60,
                           "bitrate": 1, "tamano": "4000x3000", "camara": "lateral",
                           "rotacion": 45, "linterna": "si", "tema_oscuro": 0})
        self.assertEqual((a.brillo, a.contraste, a.zoom_paso), (50, 50, 0))
        self.assertEqual((a.fps, a.bitrate, a.tamano, a.camara, a.rotacion),
                         (30, 12_000_000, "1920x1080", "back", 0))
        self.assertFalse(a.linterna)  # "si" no es un booleano: se queda el de fábrica
        self.assertTrue(a.tema_oscuro)
        self.assertEqual(self.escribir({"zoom_paso": 999}).zoom_paso, ZOOM_PASO_MAX)

    def test_ajustes_viejos_siguen_sirviendo(self):
        # Archivo de la primera versión (solo cámara, tamaño, rotación, espejo y vista previa)
        a = self.escribir({"camara": "back", "tamano": "1280x720", "fps": 30, "bitrate": 12000000,
                           "rotacion": 0, "espejo": False, "vista_previa": True})
        self.assertEqual(a.tamano, "1280x720")
        self.assertEqual((a.brillo, a.contraste, a.zoom_paso), (0, 100, 0))

    def test_tamano_en_partes(self):
        for partes, tamano in TAMANOS.items():
            self.assertEqual(partes_de_tamano(tamano), partes)
        self.assertEqual(partes_de_tamano("123x45"), ("1080p", "16:9"))


if __name__ == "__main__":
    unittest.main()
