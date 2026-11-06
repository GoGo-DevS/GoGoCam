"""Lo que cambia cuando GoGoCam corre como .exe empaquetado (PyInstaller)."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from gogocam import core, diagnostico, sistema
from gogocam.diagnostico import _servidor, revisar


class CarpetaPrograma(unittest.TestCase):
    def test_desde_el_codigo_fuente_es_la_raiz_del_proyecto(self):
        with mock.patch.object(sys, "_MEIPASS", None, create=True):
            self.assertEqual(core.carpeta_programa(), Path(core.__file__).resolve().parent.parent)

    def test_empaquetada_es_la_carpeta_interna_del_exe(self):
        with mock.patch.object(sys, "_MEIPASS", r"C:\Apps\GoGoCam\_internal", create=True):
            self.assertEqual(core.carpeta_programa(), Path(r"C:\Apps\GoGoCam\_internal"))


class BuscarAdb(unittest.TestCase):
    def test_prefiere_el_adb_que_viene_en_el_paquete(self):
        with tempfile.TemporaryDirectory() as carpeta:
            propio = Path(carpeta) / "vendor" / ("adb.exe" if core.ES_WINDOWS else "adb")
            propio.parent.mkdir()
            propio.write_bytes(b"")
            with mock.patch.object(core, "RAIZ", Path(carpeta)), mock.patch.dict(os.environ):
                os.environ.pop("GOGOCAM_ADB", None)
                self.assertEqual(core.buscar_adb(), str(propio))

    def test_la_variable_gogocam_adb_gana_igual(self):
        with tempfile.TemporaryDirectory() as carpeta:
            (Path(carpeta) / "vendor").mkdir()
            (Path(carpeta) / "vendor" / "adb.exe").write_bytes(b"")
            elegido = Path(carpeta) / "otro-adb.exe"
            elegido.write_bytes(b"")
            with mock.patch.object(core, "RAIZ", Path(carpeta)), \
                    mock.patch.dict(os.environ, {"GOGOCAM_ADB": str(elegido)}):
                self.assertEqual(core.buscar_adb(), str(elegido))


    @unittest.skipUnless(sys.platform == "win32", "el .exe es solo para Windows")
    def test_empaquetada_sin_adb_pide_descomprimir_de_nuevo(self):
        with tempfile.TemporaryDirectory() as carpeta, \
                mock.patch.object(core, "RAIZ", Path(carpeta)), \
                mock.patch.object(sys, "frozen", True, create=True), \
                mock.patch.object(core.shutil, "which", return_value=None), \
                mock.patch.dict(os.environ, {"LOCALAPPDATA": carpeta}):
            os.environ.pop("GOGOCAM_ADB", None)
            with self.assertRaisesRegex(core.GoGoCamError, "descomprimir el .zip"):
                core.buscar_adb()


class MensajeCamaraVirtual(unittest.TestCase):
    def test_sin_obs_instalado_dice_que_lo_instale(self):
        detalle = "'obs' backend: OBS Virtual Camera device not found! Did you install OBS?"
        self.assertEqual(core.mensaje_camara_virtual(detalle, windows=True), core.FALTA_OBS)
        self.assertIn("obsproject.com", core.FALTA_OBS)

    def test_ocupada_dice_que_la_apague(self):
        mensaje = core.mensaje_camara_virtual("'obs' backend: virtual camera output could not be started", windows=True)
        self.assertNotEqual(mensaje, core.FALTA_OBS)
        self.assertIn("apágala", mensaje)


class ComandoGoGoCam(unittest.TestCase):
    @unittest.skipUnless(sys.platform == "win32", "rutas de Windows")
    def test_empaquetada_apunta_al_exe_sin_menos_m(self):
        exe = r"C:\Apps\GoGoCam\GoGoCam.exe"
        with mock.patch.object(sys, "frozen", True, create=True), mock.patch.object(sys, "executable", exe):
            self.assertEqual(sistema.comando_gogocam(minimizada=True), (exe, "--minimizada", r"C:\Apps\GoGoCam"))
            self.assertEqual(sistema.comando_gogocam(), (exe, "", r"C:\Apps\GoGoCam"))

    def test_desde_el_codigo_fuente_usa_pythonw_menos_m(self):
        with mock.patch.object(sys, "frozen", False, create=True):
            _, argumentos, carpeta = sistema.comando_gogocam(minimizada=True)
            self.assertEqual(argumentos, "-m gogocam --minimizada")
            self.assertEqual(sistema.comando_gogocam()[1], "-m gogocam")
        self.assertEqual(carpeta, str(core.RAIZ))


class Diagnostico(unittest.TestCase):
    def test_sigue_aunque_una_revision_falle(self):
        def rota():
            raise RuntimeError("se rompió")

        resultados = revisar([("a", lambda: "bien"), ("b", rota), ("c", lambda: "también")])
        self.assertEqual(resultados, [("a", True, "bien"), ("b", False, "se rompió"), ("c", True, "también")])

    def test_el_servidor_de_scrcpy_del_repo_esta_integro(self):
        self.assertIn("íntegro", _servidor())

    @unittest.skipUnless(sys.platform == "win32", "OBS es la cámara virtual de Windows")
    def test_obs_instalado_se_reconoce_sin_abrir_la_camara(self):
        with mock.patch.object(diagnostico, "camaras_de_windows", return_value=["DroidCam Source 2", "OBS Virtual Camera"]):
            self.assertEqual(diagnostico._camara_virtual(), "instalada")

    @unittest.skipUnless(sys.platform == "win32", "OBS es la cámara virtual de Windows")
    def test_sin_obs_el_diagnostico_dice_que_lo_instale(self):
        with mock.patch.object(diagnostico, "camaras_de_windows", return_value=["DroidCam Source 2"]):
            resultado = revisar([("OBS Virtual Camera", diagnostico._camara_virtual)])
        self.assertEqual(resultado, [("OBS Virtual Camera", False, core.FALTA_OBS)])

    @unittest.skipUnless(sys.platform == "win32", "registro de Windows")
    def test_lee_las_camaras_de_este_windows(self):
        self.assertIsInstance(diagnostico.camaras_de_windows(), list)


if __name__ == "__main__":
    unittest.main()
