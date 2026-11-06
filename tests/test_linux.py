"""La parte Linux de GoGoCam, simulada (corre también en Windows).

Los textos en inglés son los del módulo nativo de pyvirtualcam 0.15 para Linux
(_native_linux_v4l2loopback), sacados de su paquete manylinux."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from gogocam import core, diagnostico, sistema

SIN_DISPOSITIVO = ("'v4l2loopback' backend: No v4l2 loopback device found at /dev/video[0-99]. "
                   "Did you run 'modprobe v4l2loopback'? See also pyvirtualcam's documentation.")
SIN_PERMISO = ("'v4l2loopback' backend: Could not access /dev/video10 due to missing permissions. "
               "Did you add your user to the 'video' group? Run 'usermod -a -G video myusername' "
               "and log out and in again.")
OCUPADA = "'v4l2loopback' backend: /dev/video10 is already in use."


class MensajesCamaraVirtual(unittest.TestCase):
    def test_sin_v4l2loopback_pide_instalar(self):
        self.assertEqual(core.mensaje_camara_virtual(SIN_DISPOSITIVO, windows=False), core.FALTA_V4L2)

    def test_sin_permiso_pide_el_grupo_video(self):
        mensaje = core.mensaje_camara_virtual(SIN_PERMISO, windows=False)
        self.assertEqual(mensaje, core.SIN_PERMISO_V4L2)
        self.assertIn("usermod -aG video", mensaje)

    def test_ocupada_no_confunde_con_falta(self):
        mensaje = core.mensaje_camara_virtual(OCUPADA, windows=False)
        self.assertNotIn(mensaje, (core.FALTA_V4L2, core.SIN_PERMISO_V4L2))
        self.assertIn("ciérralo", mensaje)
        self.assertNotIn("OBS Studio en este PC", mensaje)

    def test_el_error_de_linux_no_se_lee_como_falta_de_obs_en_windows(self):
        self.assertNotEqual(core.mensaje_camara_virtual(SIN_DISPOSITIVO, windows=True), core.FALTA_V4L2)


class NombreVisible(unittest.TestCase):
    def test_lee_el_card_label_de_sys(self):
        with tempfile.TemporaryDirectory() as carpeta:
            (Path(carpeta) / "video10").mkdir()
            (Path(carpeta) / "video10" / "name").write_text("GoGoCam\n", encoding="utf-8")
            self.assertEqual(core.nombre_visible("/dev/video10", windows=False, carpeta_sys=Path(carpeta)),
                             "GoGoCam (/dev/video10)")

    def test_sin_sys_queda_la_ruta(self):
        with tempfile.TemporaryDirectory() as carpeta:
            self.assertEqual(core.nombre_visible("/dev/video10", windows=False, carpeta_sys=Path(carpeta)),
                             "/dev/video10")

    def test_en_windows_no_cambia(self):
        self.assertEqual(core.nombre_visible("OBS Virtual Camera", windows=True), "OBS Virtual Camera")


class AdbEnLinux(unittest.TestCase):
    def test_sin_permiso_usb_explica_udev(self):
        salida = ("List of devices attached\n"
                  "ABC123\tno permissions (missing udev rules? user is in the plugdev group); see "
                  "[http://developer.android.com/tools/device.html]\n")
        with self.assertRaisesRegex(core.GoGoCamError, "udev"):
            core.elegir_telefono(salida)

    def test_usa_el_adb_del_sdk_en_la_carpeta_personal(self):
        with tempfile.TemporaryDirectory() as casa:
            adb = Path(casa) / "Android" / "Sdk" / "platform-tools" / "adb"
            adb.parent.mkdir(parents=True)
            adb.write_bytes(b"")
            with mock.patch.object(core, "ES_WINDOWS", False), mock.patch.object(core, "RAIZ", Path(casa)), \
                    mock.patch.object(core.shutil, "which", return_value=None), \
                    mock.patch.object(core.Path, "home", return_value=Path(casa)), mock.patch.dict(os.environ):
                os.environ.pop("GOGOCAM_ADB", None)
                self.assertEqual(core.buscar_adb(), str(adb))

    def test_sin_adb_dice_como_instalarlo(self):
        with tempfile.TemporaryDirectory() as casa:
            with mock.patch.object(core, "ES_WINDOWS", False), mock.patch.object(core, "RAIZ", Path(casa)), \
                    mock.patch.object(core.shutil, "which", return_value=None), \
                    mock.patch.object(core.Path, "home", return_value=Path(casa)), mock.patch.dict(os.environ):
                os.environ.pop("GOGOCAM_ADB", None)
                with self.assertRaisesRegex(core.GoGoCamError, "apt install adb"):
                    core.buscar_adb()


class DiagnosticoLinux(unittest.TestCase):
    def _sys_falso(self, carpeta: Path, nombre: str = "GoGoCam") -> tuple[Path, Path]:
        sys_v4l, dev = carpeta / "sys", carpeta / "dev"
        (sys_v4l / "video10").mkdir(parents=True)
        (sys_v4l / "video10" / "name").write_text(nombre + "\n", encoding="utf-8")
        dev.mkdir()
        (dev / "video10").write_bytes(b"")
        return sys_v4l, dev

    def test_encuentra_la_camara_de_v4l2loopback(self):
        with tempfile.TemporaryDirectory() as carpeta:
            sys_v4l, dev = self._sys_falso(Path(carpeta))
            self.assertEqual(diagnostico.camaras_v4l2loopback(sys_v4l, dev), [("GoGoCam", dev / "video10")])

    def test_sin_v4l2loopback_no_hay_camaras(self):
        with tempfile.TemporaryDirectory() as carpeta:
            self.assertEqual(diagnostico.camaras_v4l2loopback(Path(carpeta) / "no-existe"), [])

    def test_lista_si_se_puede_escribir(self):
        with tempfile.TemporaryDirectory() as carpeta:
            sys_v4l, dev = self._sys_falso(Path(carpeta))
            camaras = diagnostico.camaras_v4l2loopback(sys_v4l, dev)
            with mock.patch.object(diagnostico, "ES_WINDOWS", False), \
                    mock.patch.object(diagnostico, "camaras_v4l2loopback", return_value=camaras):
                self.assertIn("«GoGoCam»", diagnostico._camara_virtual())

    def test_sin_camara_falla_con_el_mensaje_de_instalar(self):
        with mock.patch.object(diagnostico, "ES_WINDOWS", False), \
                mock.patch.object(diagnostico, "camaras_v4l2loopback", return_value=[]):
            resultado = diagnostico.revisar([("cámara", diagnostico._camara_virtual)])
        self.assertEqual(resultado, [("cámara", False, core.FALTA_V4L2)])

    def test_sin_permiso_de_escritura_pide_el_grupo_video(self):
        with mock.patch.object(diagnostico, "ES_WINDOWS", False), \
                mock.patch.object(diagnostico, "camaras_v4l2loopback",
                                  return_value=[("GoGoCam", Path("/dev/video10"))]), \
                mock.patch.object(diagnostico.os, "access", return_value=False):
            resultado = diagnostico.revisar([("cámara", diagnostico._camara_virtual)])
        self.assertEqual(resultado, [("cámara", False, core.SIN_PERMISO_V4L2)])

    def test_revisa_tk(self):
        self.assertIn("Tk", diagnostico._ventana())


class ArranqueLinux(unittest.TestCase):
    COMANDO = ("/home/ana/.local/share/gogocam/venv/bin/python", "-m gogocam --minimizada",
               "/home/ana/.local/share/gogocam/app")

    def test_desktop_abre_gogocam_minimizada_desde_su_carpeta(self):
        with tempfile.TemporaryDirectory() as carpeta, \
                mock.patch.object(sistema, "comando_gogocam", return_value=self.COMANDO):
            destino = Path(carpeta) / "autostart" / "gogocam.desktop"
            sistema.escribir_desktop(destino, minimizada=True)
            lineas = destino.read_text(encoding="utf-8").splitlines()
        self.assertEqual(lineas[0], "[Desktop Entry]")
        self.assertIn("Exec=/home/ana/.local/share/gogocam/venv/bin/python -m gogocam --minimizada", lineas)
        self.assertIn("Path=/home/ana/.local/share/gogocam/app", lineas)
        self.assertIn("StartupWMClass=Gogocam", lineas)

    def test_ruta_con_espacios_va_entre_comillas(self):
        self.assertEqual(sistema.argumento_desktop("/home/ana maria/py"), '"/home/ana maria/py"')
        self.assertEqual(sistema.argumento_desktop('/a"b$c'), '"/a\\"b\\$c"')
        self.assertEqual(sistema.argumento_desktop("/usr/bin/python3"), "/usr/bin/python3")

    def test_activar_y_desactivar_el_arranque(self):
        with tempfile.TemporaryDirectory() as carpeta:
            acceso = Path(carpeta) / "autostart" / "gogocam.desktop"
            with mock.patch.object(sistema, "ES_WINDOWS", False), mock.patch.object(sistema, "ACCESO_INICIO", acceso), \
                    mock.patch.object(sistema, "comando_gogocam", return_value=self.COMANDO):
                sistema.abrir_al_encender(True)
                self.assertTrue(sistema.abre_al_encender())
                sistema.abrir_al_encender(False)
                self.assertFalse(sistema.abre_al_encender())


if __name__ == "__main__":
    unittest.main()
