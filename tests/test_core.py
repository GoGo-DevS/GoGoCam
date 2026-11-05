import unittest

from gogocam.core import (
    Ajustes, GoGoCamError, analizar_registro_servidor, app_que_usa_camara, argumentos_servidor,
    elegir_telefono, explicar_fallo_servidor, tamano_vista_previa,
)

# Líneas reales del Redmi 13C 5G con DroidCam ocupando la cámara (05-11-2026).
REGISTRO_CAMARA_OCUPADA = [
    "[server] INFO: Device: [Xiaomi] Redmi 23124RN87G (Android 14)",
    "[server] ERROR: Video encoding error",
    "java.io.IOException: android.hardware.camera2.CameraAccessException: CAMERA_IN_USE (4): "
    'connectHelper:2091: Higher-priority client using camera, ID "0" currently unavailable',
    "\tat com.genymobile.scrcpy.video.CameraCapture.init(CameraCapture.java:126)",
    "Caused by: android.hardware.camera2.CameraAccessException: CAMERA_IN_USE (4): ...",
    "\tat android.hardware.camera2.CameraManager.throwAsPublicException(CameraManager.java:1689)",
    "Caused by: android.os.ServiceSpecificException: connectHelper:2091: ... (code 7)",
    "\tat android.os.Parcel.createException(Parcel.java:3063)",
    "\t... 10 more",
]

DUMPSYS_REAL = """
  11-05 11:52:40 : Device 0 is open. Client instance dump:
    Client PID: 15572
    Client package: com.dev47apps.droidcam
"""


class PruebasTelefono(unittest.TestCase):
    def test_elige_el_listo(self):
        salida = "List of devices attached\n8LMRNVPFNNYTXWB6\tdevice product:atmos_global\n\n"
        self.assertEqual(elegir_telefono(salida), "8LMRNVPFNNYTXWB6")

    def test_prefiere_usb_sobre_wifi(self):
        salida = "List of devices attached\n192.168.1.5:5555\tdevice\nABC123\tdevice\n"
        self.assertEqual(elegir_telefono(salida), "ABC123")

    def test_sin_permiso_offline_y_vacio(self):
        casos = {
            "List of devices attached\nABC\tunauthorized\n": "Permitir depuración USB",
            "List of devices attached\nABC\toffline\n": "offline",
            "List of devices attached\n\n": "No veo ningún teléfono",
        }
        for salida, esperado in casos.items():
            with self.subTest(esperado=esperado):
                with self.assertRaises(GoGoCamError) as ctx:
                    elegir_telefono(salida)
                self.assertIn(esperado, str(ctx.exception))

    def test_argumentos_servidor(self):
        args = argumentos_servidor(Ajustes(camara="back", tamano="1920x1080"), scid=0x1A2B)
        self.assertEqual(args[:5], ["CLASSPATH=/data/local/tmp/gogocam-server.jar", "app_process", "/",
                                    "com.genymobile.scrcpy.Server", "5.0.1"])
        # El servidor lee el scid en hexadecimal; el túnel usa los mismos 8 dígitos.
        self.assertIn("scid=00001a2b", args)
        for esperado in ("video_source=camera", "camera_facing=back", "camera_size=1920x1080",
                         "camera_fps=30", "audio=false", "control=false", "tunnel_forward=true",
                         "video_codec=h264"):
            self.assertIn(esperado, args)
        self.assertTrue(all(" " not in a for a in args), "adb shell separa por espacios")


class PruebasErroresServidor(unittest.TestCase):
    def test_resumen_salta_el_stack_trace(self):
        resumen, completo = analizar_registro_servidor(REGISTRO_CAMARA_OCUPADA)
        self.assertTrue(resumen.startswith("[server] ERROR: Video encoding error | java.io.IOException"))
        self.assertIn("CAMERA_IN_USE", resumen)
        self.assertNotIn("Parcel.java", resumen)
        self.assertIn("Parcel.java", completo)

    def test_sin_error(self):
        self.assertEqual(analizar_registro_servidor(["[server] INFO: todo bien"]), ("", ""))

    def test_camara_ocupada_nombra_la_app(self):
        _, completo = analizar_registro_servidor(REGISTRO_CAMARA_OCUPADA)
        app = app_que_usa_camara(DUMPSYS_REAL)
        self.assertEqual(app, "com.dev47apps.droidcam")
        mensaje = explicar_fallo_servidor(completo, app)
        self.assertIn("DroidCam", mensaje)
        self.assertNotIn("cable", mensaje)

    def test_ignora_al_propio_shell(self):
        self.assertIsNone(app_que_usa_camara("    Client package: com.android.shell\n"))

    def test_error_desconocido_no_se_inventa(self):
        self.assertIsNone(explicar_fallo_servidor("[server] ERROR: algo raro"))


class PruebasVistaPrevia(unittest.TestCase):
    def test_horizontal_y_vertical_caben_en_la_caja(self):
        self.assertEqual(tamano_vista_previa(1920, 1080, 0), (400, 224))
        self.assertEqual(tamano_vista_previa(1920, 1080, 90), (146, 260))


if __name__ == "__main__":
    unittest.main()
