"""Núcleo de GoGoCam: la cámara del teléfono (Android 12+) como cámara web del PC.

Flujo:
  1. adb copia el servidor de scrcpy al teléfono (no se instala ninguna app);
  2. se abre un túnel por USB (adb forward) y se arranca el servidor en modo cámara;
  3. el servidor manda H.264; aquí se decodifica con PyAV;
  4. cada cuadro se publica en «OBS Virtual Camera», que OBS, Meet, Zoom, etc.
     ven como una cámara web normal.
"""
from __future__ import annotations

import collections
import logging
import os
import queue
import random
import shutil
import socket
import subprocess
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Optional

import av
import pyvirtualcam

from .frames import (
    a_ppm, aplicar_tabla_y, tabla_brillo_contraste, tamano_salida, transformar_i420, transformar_rgb,
)
from .protocolo import ErrorDeFlujo, LectorVideo, Paquete, Sesion, VideoDesactivado

RAIZ = Path(__file__).resolve().parent.parent
VERSION_SERVIDOR = "5.0.1"
SERVIDOR_LOCAL = RAIZ / "vendor" / f"scrcpy-server-v{VERSION_SERVIDOR}"
SERVIDOR_REMOTO = "/data/local/tmp/gogocam-server.jar"
SDK_MINIMO = 31  # Android 12: lo exige el modo cámara de scrcpy
CAJA_VISTA_PREVIA = (400, 260)  # el recuadro de la ventana, en píxeles
CUADROS_POR_MUESTRA = 3  # vista previa a ~10 fps (gasta menos); la cámara virtual recibe TODOS

# Zoom: scrcpy acerca o aleja en pasos de x1,0625 (CameraCapture.ZOOM_FACTOR, siempre alineado
# a potencias de ese número). GoGoCam guarda el PASO: zoom = 1,0625 ** paso.
ZOOM_FACTOR = 1 + 1 / 16
ZOOM_PASO_MAX = 23  # 1,0625**23 ≈ 4,0x; más allá es zoom digital que se ve mal en una reunión

# Mensajes del canal de control (ControlMessage.java de scrcpy 5.0.1)
TIPO_LINTERNA = 18  # + 1 byte: 1 encender, 0 apagar
TIPO_ZOOM_MAS = 19
TIPO_ZOOM_MENOS = 20
SIN_VENTANA = getattr(subprocess, "CREATE_NO_WINDOW", 0)  # que adb no abra consolas

log = logging.getLogger("gogocam")


class GoGoCamError(Exception):
    """Error con un mensaje pensado para mostrárselo al usuario tal cual."""


class ServidorCerrado(Exception):
    """El servidor del teléfono terminó antes de aceptar la conexión."""


@dataclass
class Ajustes:
    # Se fijan al iniciar
    camara: str = "back"  # back | front
    tamano: str = "1920x1080"
    fps: int = 30
    bitrate: int = 12_000_000
    # Se cambian en vivo
    rotacion: int = 0  # horaria: 0, 90, 180, 270
    espejo: bool = False
    brillo: int = 0  # -50 a 50
    contraste: int = 100  # 50 a 150 (%)
    zoom_paso: int = 0  # 0 a ZOOM_PASO_MAX (ver zoom_de_paso)
    linterna: bool = False  # solo la cámara trasera tiene flash
    # De la ventana
    vista_previa: bool = True
    autoiniciar: bool = False
    tema_oscuro: bool = True

    def a_dict(self) -> dict:
        return asdict(self)


def zoom_de_paso(paso: int) -> float:
    return ZOOM_FACTOR ** paso


def limitar_paso(paso: int) -> int:
    return min(max(int(paso), 0), ZOOM_PASO_MAX)


def linterna_pedida(ajustes: Ajustes) -> bool:
    return ajustes.linterna and ajustes.camara == "back"


def mensajes_control(paso_actual: int, paso_deseado: int,
                     linterna_actual: bool, linterna_deseada: bool) -> bytes:
    """Bytes a mandar por el canal de control para pasar del estado actual al deseado."""
    mensajes = b""
    if linterna_deseada != linterna_actual:
        mensajes += bytes([TIPO_LINTERNA, 1 if linterna_deseada else 0])
    diferencia = paso_deseado - paso_actual
    if diferencia:
        mensajes += bytes([TIPO_ZOOM_MAS if diferencia > 0 else TIPO_ZOOM_MENOS]) * abs(diferencia)
    return mensajes


# ---------------------------------------------------------------- adb

def buscar_adb() -> str:
    candidatos = [
        os.environ.get("GOGOCAM_ADB"),
        shutil.which("adb"),
        str(Path(os.environ.get("LOCALAPPDATA", "")) / "Android" / "Sdk" / "platform-tools" / "adb.exe"),
        str(RAIZ / "vendor" / "adb.exe"),
    ]
    for candidato in candidatos:
        if candidato and Path(candidato).is_file():
            return candidato
    raise GoGoCamError(
        "No encontré adb. Instala Android Platform Tools o define la variable GOGOCAM_ADB "
        "con la ruta de adb.exe."
    )


def adb(adb_exe: str, *args: str, serial: Optional[str] = None, timeout: float = 20) -> str:
    cmd = [adb_exe] + (["-s", serial] if serial else []) + list(args)
    try:
        r = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=timeout, creationflags=SIN_VENTANA,
        )
    except subprocess.TimeoutExpired as e:
        raise GoGoCamError(f"adb no respondió a tiempo ({' '.join(args[:2])}).") from e
    if r.returncode != 0:
        detalle = (r.stderr or r.stdout).strip()
        raise GoGoCamError(f"adb {' '.join(args[:2])} falló: {detalle}")
    return r.stdout


def elegir_telefono(salida_devices: str) -> str:
    """Elige el teléfono de la salida de `adb devices`; prefiere USB sobre Wi-Fi."""
    listos, sin_permiso, offline = [], [], []
    for linea in salida_devices.splitlines()[1:]:
        partes = linea.split()
        if len(partes) < 2:
            continue
        serial, estado = partes[0], partes[1]
        if estado == "device":
            listos.append(serial)
        elif estado == "unauthorized":
            sin_permiso.append(serial)
        elif estado == "offline":
            offline.append(serial)
    if listos:
        por_usb = [s for s in listos if ":" not in s]
        return (por_usb or listos)[0]
    if sin_permiso:
        raise GoGoCamError(
            "El teléfono está conectado pero falta el permiso: desbloquéalo y acepta "
            "«Permitir depuración USB»."
        )
    if offline:
        raise GoGoCamError("El teléfono aparece desconectado (offline). Desenchufa y vuelve a enchufar el cable.")
    raise GoGoCamError(
        "No veo ningún teléfono. Conéctalo por USB y revisa que la depuración USB esté activa "
        "(Ajustes > Opciones de desarrollador)."
    )


def argumentos_servidor(ajustes: Ajustes, scid: int) -> list[str]:
    """Comando para `adb shell`. El scid va en hexadecimal: así lo lee el servidor."""
    argumentos = [
        f"CLASSPATH={SERVIDOR_REMOTO}",
        "app_process", "/", "com.genymobile.scrcpy.Server", VERSION_SERVIDOR,
        f"scid={scid:08x}",
        "log_level=info",
        "tunnel_forward=true",
        # control=true: canal para zoom y linterna en vivo. En modo cámara scrcpy no inyecta
        # toques ni sincroniza el portapapeles, y no manda nada de vuelta por ese canal.
        "video=true", "audio=false", "control=true", "cleanup=false",
        "video_source=camera",
        f"camera_facing={ajustes.camara}",
        f"camera_size={ajustes.tamano}",
        f"camera_fps={ajustes.fps}",
        "video_codec=h264",
        f"video_bit_rate={ajustes.bitrate}",
        "send_device_meta=false",
    ]
    paso = limitar_paso(ajustes.zoom_paso)
    if paso:
        argumentos.append(f"camera_zoom={zoom_de_paso(paso):.6f}")
    if linterna_pedida(ajustes):
        argumentos.append("camera_torch=true")
    return argumentos


NOMBRES_APPS = {
    "com.dev47apps.droidcam": "DroidCam",
    "com.dev47apps.obsdroidcam": "DroidCam OBS",
}


def app_que_usa_camara(salida_dumpsys: str) -> Optional[str]:
    """Paquete que tiene abierta la cámara, según `dumpsys media.camera`."""
    for linea in salida_dumpsys.splitlines():
        linea = linea.strip()
        if linea.startswith("Client package:"):
            paquete = linea.split(":", 1)[1].strip()
            if paquete and paquete != "com.android.shell":
                return paquete
    return None


def analizar_registro_servidor(lineas: list[str]) -> tuple[str, str]:
    """Del registro del servidor: (resumen del último error, texto completo desde ese error).

    El resumen junta la línea ERROR con la primera excepción, sin el stack trace.
    """
    inicio = None
    for i, linea in enumerate(lineas):
        if "ERROR" in linea:
            inicio = i
    if inicio is None:
        return "", ""
    bloque = [l.strip() for l in lineas[inicio:]]
    resumen = [bloque[0]]
    for linea in bloque[1:]:
        if linea.startswith("at ") or linea.startswith("..."):
            continue
        resumen.append(linea.removeprefix("Caused by: "))
        break
    return " | ".join(resumen), "\n".join(bloque)


def explicar_fallo_servidor(detalle: str, app_ocupando: Optional[str] = None) -> Optional[str]:
    """Traduce los errores conocidos del servidor a un mensaje claro. None si no se reconoce."""
    if "CAMERA_IN_USE" in detalle or "MAX_CAMERAS_IN_USE" in detalle or "currently unavailable" in detalle:
        if app_ocupando:
            nombre = NOMBRES_APPS.get(app_ocupando, app_ocupando)
            return (
                f"La cámara del teléfono la está usando otra app: {nombre}. "
                "Ciérrala en el teléfono y vuelve a intentar."
            )
        return "La cámara del teléfono la está usando otra app. Ciérrala y vuelve a intentar."
    if "CAMERA_DISABLED" in detalle:
        return (
            "El teléfono tiene bloqueado el acceso a la cámara. Actívalo en Ajustes > Privacidad "
            "(o en el panel de accesos rápidos) y vuelve a intentar."
        )
    if "No camera" in detalle or "camera not found" in detalle.lower():
        return "No encontré esa cámara en el teléfono. Prueba con la otra (trasera o frontal)."
    if "size" in detalle.lower() and "camera" in detalle.lower():
        return "El teléfono no acepta esa calidad para esta cámara. Prueba con 720p."
    return None


def tamano_vista_previa(ancho: int, alto: int, rotacion: int) -> tuple[int, int]:
    """Tamaño (par) de la vista previa YA rotada, cabiendo en CAJA_VISTA_PREVIA."""
    ancho_final, alto_final = tamano_salida(ancho, alto, rotacion)
    escala = min(CAJA_VISTA_PREVIA[0] / ancho_final, CAJA_VISTA_PREVIA[1] / alto_final)
    return (max(2, int(ancho_final * escala) // 2 * 2), max(2, int(alto_final * escala) // 2 * 2))


def sin_modo_eficiencia() -> bool:
    """Le pide a Windows que no frene este proceso estando minimizado.

    Windows 11 aplica "modo eficiencia" (EcoQoS) a los procesos en segundo plano:
    baja la velocidad del CPU para ellos y eso trabaría el video que recibe la reunión.
    Devuelve True si Windows aceptó.
    """
    try:
        import ctypes
        from ctypes import wintypes

        class EstadoAhorro(ctypes.Structure):  # PROCESS_POWER_THROTTLING_STATE
            _fields_ = [("Version", wintypes.ULONG), ("ControlMask", wintypes.ULONG),
                        ("StateMask", wintypes.ULONG)]

        velocidad, resolucion_timer = 0x1, 0x4  # ..._EXECUTION_SPEED, ..._IGNORE_TIMER_RESOLUTION
        estado = EstadoAhorro(1, velocidad | resolucion_timer, 0)  # StateMask 0 = nunca frenar
        kernel32 = ctypes.windll.kernel32
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        kernel32.SetProcessInformation.argtypes = [
            wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        kernel32.SetProcessInformation.restype = wintypes.BOOL
        ok = bool(kernel32.SetProcessInformation(
            kernel32.GetCurrentProcess(), 4,  # 4 = ProcessPowerThrottling
            ctypes.byref(estado), ctypes.sizeof(estado)))
    except (AttributeError, OSError):
        ok = False
    log.info("modo eficiencia de Windows desactivado: %s", ok)
    return ok


def puerto_libre() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def abrir_camara_virtual(ancho: int, alto: int, fps: int) -> pyvirtualcam.Camera:
    try:
        return pyvirtualcam.Camera(
            width=ancho, height=alto, fps=fps, fmt=pyvirtualcam.PixelFormat.I420, backend="obs"
        )
    except RuntimeError as e:
        raise GoGoCamError(
            "No pude abrir «OBS Virtual Camera». Si OBS tiene su cámara virtual encendida, "
            f"apágala o cierra OBS y vuelve a intentar. (Detalle: {e})"
        ) from e


# ---------------------------------------------------------------- transmisión

class Transmision:
    """Una sesión teléfono -> cámara virtual. Corre en su propio hilo.

    Los avisos para la interfaz van a `self.eventos` como tuplas (tipo, texto),
    con tipo en: "info", "ok", "error", "fin".
    """

    def __init__(self, ajustes: Ajustes):
        self.ajustes = ajustes
        self.eventos: "queue.Queue[tuple[str, str]]" = queue.Queue()
        self.vista_previa: Optional[bytes] = None  # PPM del último cuadro de muestra
        self.vista_oculta = False  # la ventana está minimizada: no se arma la vista previa
        self.cuadros = 0
        self.fps = 0.0
        self.tamano_salida = (0, 0)
        self.error: Optional[str] = None
        self._parar = threading.Event()
        self._hilo: Optional[threading.Thread] = None
        self._sock: Optional[socket.socket] = None
        self._control: Optional[socket.socket] = None
        # Lo que el teléfono ya tiene aplicado (al arrancar, lo que se le pasó por argumento)
        self._paso_aplicado = limitar_paso(ajustes.zoom_paso)
        self._linterna_aplicada = linterna_pedida(ajustes)
        self._tabla: tuple[tuple[int, int], Optional["np.ndarray"]] = ((0, 100), None)
        self._proc: Optional[subprocess.Popen] = None
        self._tunel: Optional[tuple[str, str, int]] = None
        self._registro_servidor: collections.deque[str] = collections.deque(maxlen=300)

    # -- control

    def iniciar(self) -> None:
        self._hilo = threading.Thread(target=self._correr, name="gogocam", daemon=True)
        self._hilo.start()

    def detener(self, esperar: float = 5.0) -> None:
        self._parar.set()
        for sock in (self._sock, self._control):
            if sock is not None:
                try:
                    sock.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
        if self._hilo is not None and threading.current_thread() is not self._hilo:
            self._hilo.join(esperar)

    @property
    def activa(self) -> bool:
        return self._hilo is not None and self._hilo.is_alive()

    # -- internos

    def _avisar(self, tipo: str, texto: str) -> None:
        log.info("[%s] %s", tipo, texto)
        self.eventos.put((tipo, texto))

    def _leer_registro_servidor(self, proc: subprocess.Popen) -> None:
        assert proc.stdout is not None
        for linea in proc.stdout:
            linea = linea.rstrip()
            if linea:
                self._registro_servidor.append(linea)
                log.info("teléfono: %s", linea)

    def _preparar_telefono(self) -> int:
        """Copia y arranca el servidor en el teléfono. Devuelve el puerto local del túnel.

        Las pruebas sin teléfono reemplazan solo este método.
        """
        self._avisar("info", "Buscando el teléfono…")
        adb_exe = buscar_adb()
        serial = elegir_telefono(adb(adb_exe, "devices"))
        modelo = adb(adb_exe, "shell", "getprop", "ro.product.marketname", serial=serial).strip() \
            or adb(adb_exe, "shell", "getprop", "ro.product.model", serial=serial).strip()
        sdk = adb(adb_exe, "shell", "getprop", "ro.build.version.sdk", serial=serial).strip()
        if sdk.isdigit() and int(sdk) < SDK_MINIMO:
            raise GoGoCamError("La cámara por USB necesita Android 12 o superior en el teléfono.")
        if not SERVIDOR_LOCAL.is_file():
            raise GoGoCamError(f"Falta el archivo del servidor: {SERVIDOR_LOCAL}")

        adb(adb_exe, "push", str(SERVIDOR_LOCAL), SERVIDOR_REMOTO, serial=serial, timeout=60)
        scid = random.randint(1, 0x7FFFFFFF)
        puerto = puerto_libre()
        adb(adb_exe, "forward", f"tcp:{puerto}", f"localabstract:scrcpy_{scid:08x}", serial=serial)
        self._tunel = (adb_exe, serial, puerto)

        self._proc = subprocess.Popen(
            [adb_exe, "-s", serial, "shell", *argumentos_servidor(self.ajustes, scid)],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
            text=True, encoding="utf-8", errors="replace", creationflags=SIN_VENTANA,
        )
        threading.Thread(target=self._leer_registro_servidor, args=(self._proc,), daemon=True).start()
        self._avisar("info", f"Abriendo la cámara de {modelo or 'tu teléfono'}…")
        return puerto

    def _correr(self) -> None:
        try:
            puerto = self._preparar_telefono()
            self._sock = self._conectar(puerto)
            # El teléfono acepta primero el video y después el control; recién con los dos
            # conectados empieza a mandar video.
            self._control = socket.create_connection(("127.0.0.1", puerto), timeout=5)
            self._control.settimeout(2)
            lector = LectorVideo(self._sock)
            lector.leer_codec()
            self._transmitir(lector)
        except GoGoCamError as e:
            self.error = str(e)
        except ServidorCerrado:
            self.error = self._explicar_fallo("El servidor de cámara se cerró al arrancar.")
        except VideoDesactivado as e:
            self.error = self._explicar_fallo(
                f"El teléfono no pudo abrir la cámara (código {e.codigo})."
            )
        except (ConnectionError, OSError, ErrorDeFlujo) as e:
            if not self._parar.is_set():
                self.error = self._explicar_fallo(
                    f"Se cortó la conexión con el teléfono. ¿Se soltó el cable? ({e})"
                )
        except Exception as e:  # noqa: BLE001 - se muestra al usuario y queda en el log
            log.exception("error inesperado")
            self.error = f"Error inesperado: {e}"
        finally:
            self._limpiar()
            if self.error:
                self._avisar("error", self.error)
            self._avisar("fin", self.error or "Detenida.")

    def _explicar_fallo(self, mensaje_generico: str) -> str:
        """Mensaje para el usuario a partir de lo que dijo el servidor del teléfono."""
        resumen, completo = self._esperar_detalle_servidor()
        app_ocupando = None
        if self._tunel is not None and ("unavailable" in completo or "IN_USE" in completo):
            adb_exe, serial, _ = self._tunel
            try:
                app_ocupando = app_que_usa_camara(
                    adb(adb_exe, "shell", "dumpsys", "media.camera", serial=serial, timeout=10)
                )
            except GoGoCamError:
                pass
        claro = explicar_fallo_servidor(completo, app_ocupando)
        if claro:
            log.info("fallo del servidor: %s", resumen)
            return claro
        return mensaje_generico + (f"\nDetalle: {resumen}" if resumen else "")

    def _esperar_detalle_servidor(self) -> tuple[str, str]:
        # El servidor termina de escribir su error (con el stack trace) al cerrarse.
        limite = time.monotonic() + 2.0
        while time.monotonic() < limite:
            if self._proc is None or self._proc.poll() is not None:
                break
            time.sleep(0.1)
        time.sleep(0.1)  # dejar que el hilo lector vacíe la tubería
        return analizar_registro_servidor(list(self._registro_servidor))

    def _conectar(self, puerto: int) -> socket.socket:
        """Con adb forward, conectar siempre funciona aunque el teléfono aún no escuche:
        la conexión real se confirma al recibir el byte de prueba."""
        limite = time.monotonic() + 15
        while not self._parar.is_set():
            if self._proc is not None and self._proc.poll() is not None:
                raise ServidorCerrado()
            sock = None
            try:
                sock = socket.create_connection(("127.0.0.1", puerto), timeout=3)
                sock.settimeout(3)
                if sock.recv(1):
                    sock.settimeout(10)  # 10 s sin video = algo se cortó
                    return sock
            except OSError:
                pass
            if sock is not None:
                sock.close()
            if time.monotonic() > limite:
                raise GoGoCamError("El teléfono no respondió. Desbloquéalo y vuelve a intentar.")
            time.sleep(0.25)
        raise GoGoCamError("Cancelado.")

    def _transmitir(self, lector: LectorVideo) -> None:
        decodificador = av.CodecContext.create("h264", "r")
        decodificador.flags |= av.codec.context.Flags.low_delay
        camara: Optional[pyvirtualcam.Camera] = None
        dims_camara: Optional[tuple[int, int]] = None
        ventana_inicio = time.monotonic()
        cuadros_ventana = 0
        try:
            while not self._parar.is_set():
                elemento = lector.siguiente()
                if isinstance(elemento, Sesion):
                    log.info("sesión de video %dx%d", elemento.ancho, elemento.alto)
                    continue
                assert isinstance(elemento, Paquete)
                try:
                    cuadros = decodificador.decode(av.Packet(elemento.datos))
                except av.FFmpegError as e:
                    log.warning("paquete no decodificable: %s", e)
                    continue

                for cuadro in cuadros:
                    if cuadro.format.name not in ("yuv420p", "yuvj420p"):
                        cuadro = cuadro.reformat(format="yuv420p")
                    rotacion, espejo = self.ajustes.rotacion, self.ajustes.espejo
                    crudo = cuadro.to_ndarray()
                    tabla = self._tabla_actual()
                    if tabla is not None:
                        crudo = aplicar_tabla_y(crudo, cuadro.width, cuadro.height, tabla)
                    datos, ancho, alto = transformar_i420(
                        crudo, cuadro.width, cuadro.height, rotacion, espejo
                    )
                    if dims_camara != (ancho, alto):
                        if camara is not None:
                            camara.close()
                        camara = abrir_camara_virtual(ancho, alto, self.ajustes.fps)
                        dims_camara = (ancho, alto)
                        self.tamano_salida = dims_camara
                        self._avisar("ok", f"Transmitiendo {ancho}x{alto} a «{camara.device}».")
                    camara.send(datos)
                    # Con cuadros llegando la cámara del teléfono ya está lista: antes de eso
                    # descarta los mensajes de control sin avisar.
                    self._sincronizar_controles()

                    self.cuadros += 1
                    cuadros_ventana += 1
                    ahora = time.monotonic()
                    if ahora - ventana_inicio >= 1.0:
                        self.fps = cuadros_ventana / (ahora - ventana_inicio)
                        ventana_inicio, cuadros_ventana = ahora, 0
                    if (self.ajustes.vista_previa and not self.vista_oculta
                            and self.cuadros % CUADROS_POR_MUESTRA == 0):
                        fuente = cuadro if tabla is None else self._cuadro_desde(crudo, cuadro)
                        self.vista_previa = self._muestra(fuente, rotacion, espejo)
        finally:
            if camara is not None:
                camara.close()

    def _tabla_actual(self) -> Optional["np.ndarray"]:
        clave = (int(self.ajustes.brillo), int(self.ajustes.contraste))
        if clave != self._tabla[0]:
            self._tabla = (clave, tabla_brillo_contraste(*clave))
        return self._tabla[1]

    @staticmethod
    def _cuadro_desde(crudo: "np.ndarray", original: av.VideoFrame) -> av.VideoFrame:
        """Cuadro con brillo y contraste aplicados, para que la vista previa muestre lo mismo
        que recibe la reunión."""
        arreglo = crudo.reshape(original.height * 3 // 2, original.width)
        try:
            return av.VideoFrame.from_ndarray(arreglo, format=original.format.name)
        except ValueError:
            return av.VideoFrame.from_ndarray(arreglo, format="yuv420p")

    def _sincronizar_controles(self) -> None:
        if self._control is None:
            return
        paso, linterna = limitar_paso(self.ajustes.zoom_paso), linterna_pedida(self.ajustes)
        if paso == self._paso_aplicado and linterna == self._linterna_aplicada:
            return
        mensajes = mensajes_control(self._paso_aplicado, paso, self._linterna_aplicada, linterna)
        try:
            self._control.sendall(mensajes)
        except OSError as e:
            # El video sigue; solo se pierde el control en vivo.
            log.warning("no pude mandar zoom/linterna al teléfono: %s", e)
            self._control = None
            self._avisar("info", "El zoom y la linterna quedaron fijos hasta volver a iniciar.")
            return
        log.info("control: zoom %.2fx, linterna %s", zoom_de_paso(paso), "sí" if linterna else "no")
        self._paso_aplicado, self._linterna_aplicada = paso, linterna

    @staticmethod
    def _muestra(cuadro: av.VideoFrame, rotacion: int, espejo: bool) -> bytes:
        ancho, alto = tamano_vista_previa(cuadro.width, cuadro.height, rotacion)
        # Se achica antes de rotar: si va rotada, ancho y alto se intercambian.
        if rotacion in (90, 270):
            ancho, alto = alto, ancho
        rgb = cuadro.reformat(width=ancho, height=alto, format="rgb24").to_ndarray()
        return a_ppm(transformar_rgb(rgb, rotacion, espejo))

    def _limpiar(self) -> None:
        for sock in (self._sock, self._control):
            if sock is not None:
                try:
                    sock.close()
                except OSError:
                    pass
        if self._proc is not None and self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(3)
            except subprocess.TimeoutExpired:
                self._proc.kill()
        if self._tunel is not None:
            adb_exe, serial, puerto = self._tunel
            try:
                adb(adb_exe, "forward", "--remove", f"tcp:{puerto}", serial=serial, timeout=5)
            except GoGoCamError:
                pass
            self._tunel = None
        self.vista_previa = None
