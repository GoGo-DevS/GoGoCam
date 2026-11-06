# GoGoCam

La cámara del teléfono como cámara web del PC, por USB, sin publicidad y sin
funciones bloqueadas. En el teléfono **no se instala ninguna app**.

```
Teléfono (Android 12+)  --USB-->  GoGoCam (PC)  -->  «OBS Virtual Camera»  -->  Meet, Zoom, OBS, Teams…
 servidor de scrcpy                decodifica          cámara web virtual
 captura la cámara                 rota / espejo
 y manda H.264
```

## Requisitos

- Windows 10/11.
- Teléfono Android 12 o superior con **depuración USB** activa
  (Ajustes > Opciones de desarrollador). La primera vez el teléfono pide
  «Permitir depuración USB»: hay que aceptar.
- **OBS Studio instalado.** GoGoCam usa su cámara virtual; OBS no necesita estar
  abierto.
- `adb` (Android Platform Tools). Se busca en `GOGOCAM_ADB`, en el PATH y en
  `%LOCALAPPDATA%\Android\Sdk\platform-tools`.

## Uso

1. Conecta el teléfono por USB.
2. Abre **GoGoCam** (acceso directo del escritorio) y presiona **Iniciar**.
3. En la app donde la quieras usar, elige la cámara **«OBS Virtual Camera»**.

Se puede **minimizar**: sigue transmitiendo igual (la barra de tareas dice
«GoGoCam · transmitiendo») y deja de dibujar la vista previa para gastar menos.
Windows no la frena en segundo plano (se le desactiva el «modo eficiencia»).

**Pestaña Imagen** (todo en vivo, sin cortar la reunión):

- **Brillo** y **Contraste**: se aplican en el PC a la luz de la imagen.
- **Zoom** de 1x a 4x: es el zoom de la cámara del teléfono, por el canal de
  control de scrcpy.
- **Linterna**: el flash del teléfono como luz de relleno (solo cámara trasera).
- **Rotación** (90° o 270° si el teléfono está vertical) y **Espejo**.

**Pestaña Calidad** (se aplica al presionar Iniciar): cámara, resolución
(1080p/720p), formato (16:9/4:3), fps (30/20/15) y bitrate (8/12/20 Mbps).
**Con poca luz usa 20 fps**: medido en el Redmi 13C, la misma pieza dio luz
media ~30 a 30 fps y ~100 a 20 fps, porque la cámara puede exponer 1/20 s.

**Pestaña Opciones**: vista previa, empezar a transmitir al abrir, abrir con
Windows (acceso directo minimizado en la carpeta Inicio) y tema oscuro.

Los ajustes se recuerdan en `%LOCALAPPDATA%\GoGoCam\ajustes.json` y el registro
queda en `%LOCALAPPDATA%\GoGoCam\gogocam.log`.

El teléfono no da más de **30 fps** (lo informa así su cámara, y no tiene modo
de alta velocidad). El codificador exige alto múltiplo de 16: 1080 sale 1072.

**Para grabar en OBS:** agrega una fuente «Dispositivo de captura de video» con
«OBS Virtual Camera». No enciendas a la vez la cámara virtual de OBS: GoGoCam
la está ocupando.

## Problemas comunes

| Mensaje | Qué hacer |
|---|---|
| «La cámara del teléfono la está usando otra app: DroidCam» | Cierra esa app en el teléfono. |
| «Falta el permiso… Permitir depuración USB» | Desbloquea el teléfono y acepta el aviso. |
| «No pude abrir OBS Virtual Camera» | Apaga la cámara virtual de OBS o cierra OBS. |
| La imagen sale girada | Cambia **Rotación**. |

## Desarrollo

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -t .      # pruebas
.\.venv\Scripts\python.exe herramientas\prueba_sin_telefono.py      # cadena completa sin teléfono
.\.venv\Scripts\python.exe -m gogocam --prueba 10                   # 10 s con el teléfono real, sin ventana
.\.venv\Scripts\python.exe -m gogocam --diagnostico                 # ¿falta algo? (no toca el teléfono)
.\.venv\Scripts\python.exe herramientas\generar_icono.py            # vuelve a dibujar recursos/gogocam.*
```

`--diagnostico` (también en el .exe) revisa, **sin tocar el teléfono**, el servidor de
scrcpy (SHA-256), adb (`adb version`, que no arranca el servidor de adb), el
decodificador H.264 y que «OBS Virtual Camera» esté registrada en Windows, sin
abrirla: se puede correr en plena llamada. Deja el resultado en `gogocam.log` y
sale con código 0 si todo está bien.

`prueba_sin_telefono.py` levanta un teléfono falso que habla el mismo protocolo
y comprueba, leyendo la cámara virtual con ffmpeg, que llega la imagen real y no
el relleno de OBS. Revisa también las capturas que guarda.

Estructura:

- `gogocam/core.py`: adb, servidor del teléfono, decodificación, cámara virtual
  y canal de control (zoom/linterna: mensajes 18, 19 y 20 de `ControlMessage.java`
  de scrcpy 5.0.1; se mandan recién con cuadros llegando, porque antes el
  teléfono los descarta sin avisar).
- `gogocam/protocolo.py`: lectura del flujo de scrcpy v5.0.1 (verificado contra
  `Streamer.java` y `DesktopConnection.java` de esa versión).
- `gogocam/frames.py`: rotación, espejo, brillo y contraste sobre I420, sin pasar por RGB.
- `gogocam/ui.py`: la ventana (Tkinter, tema `clam` con los colores de GoGoDevS).
- `gogocam/sistema.py`: ícono, barra de título oscura y abrir con Windows (apunta
  al .exe si está empaquetada).
- `gogocam/diagnostico.py`: el `--diagnostico`.
- `recursos/`: ícono (lo dibuja `herramientas/generar_icono.py`).
- `lanzador.py`, `herramientas/empaquetar.py` y `distribucion/`: el .exe para compartir.

## Compartir (GoGoCam.exe)

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-empaquetar.txt
.\.venv\Scripts\python.exe herramientas\empaquetar.py
```

Deja `dist\GoGoCam-<versión>.zip` (~54 MB): una carpeta con `GoGoCam.exe`
(PyInstaller, sin consola), adb y el servidor de scrcpy dentro, el
`LEEME.txt` para quien lo recibe (fuente: `distribucion/LEEME.txt`) y
`licencias/` con el código fuente. Quien lo recibe **solo necesita OBS Studio**
instalado; ni Python ni adb.

Empaquetada, GoGoCam busca primero el adb que trae adentro (versión conocida) y
sus archivos en `_internal` (`sys._MEIPASS`). Subir la versión en
`gogocam/__init__.py` antes de armar un paquete nuevo.

**Licencias:** pyvirtualcam es GPL-2.0, así que el .exe se reparte junto con su
código fuente (`licencias/codigo-fuente-gogocam.zip`, lo arma el script). Para
venderlo cerrado habría que reemplazar pyvirtualcam.

## Linux

```powershell
.\.venv\Scripts\python.exe herramientas\empaquetar_linux.py     # se arma desde Windows
```

Deja `dist\GoGoCam-<versión>-linux.tar.gz` (~0,7 MB): el código fuente con
`instalar.sh`, `desinstalar.sh` y su `LEEME.txt` (fuentes en `distribucion/linux/`).
El empaquetador fuerza saltos de línea LF y permiso 755 en los `.sh` (con CRLF
fallan con «bad interpreter»; `.gitattributes` también los fija).

`instalar.sh` (apt, dnf, pacman o zypper) instala adb, Python con Tk y
**v4l2loopback**, que es la cámara virtual de Linux: `/dev/video10` con el nombre
«GoGoCam» y `exclusive_caps=1` (sin eso Chrome y Meet no la ven; con eso aparece
recién cuando GoGoCam transmite). Copia la app a `~/.local/share/gogocam/app`, arma
un venv con `requirements-linux.txt` (solo paquetes listos), y crea el comando
`gogocam` y el acceso del menú. Si v4l2loopback ya estaba cargado (OBS lo usa), no lo
toca.

En el código, `core.ES_WINDOWS` separa lo propio de cada sistema: backend
`v4l2loopback` en vez de `obs`, adb del sistema o de `~/Android/Sdk`, datos en
`~/.local/share/gogocam`, arranque con un `.desktop` en `~/.config/autostart`, y en
el diagnóstico la cámara se busca en `/sys/devices/virtual/video4linux`. Las pruebas
de `tests/test_linux.py` simulan esa parte (corren en Windows). **No está probado en
un Linux real**: la simulación del instalador (`sudo`, `apt-get` y `python3` falsos)
recorre el flujo completo, pero no carga el módulo ni transmite.

**Actualizar scrcpy:** el servidor y el cliente tienen que ser exactamente de la
misma versión. Baja `scrcpy-server-vX.Y.Z` de la release oficial, verifica su
SHA-256 con `SHA256SUMS.txt`, déjalo en `vendor/`, cambia `VERSION_SERVIDOR` en
`core.py` y revisa en `doc/develop.md` de esa versión si cambió el protocolo.

## Licencias

- `vendor/scrcpy-server-v5.0.1` es el servidor oficial de
  [scrcpy](https://github.com/Genymobile/scrcpy) (Genymobile), sin modificar,
  bajo licencia Apache 2.0 (`vendor/LICENSE-scrcpy.txt`). SHA-256 en
  `vendor/SHA256SUMS.txt`.
- Usa [PyAV](https://github.com/PyAV-Org/PyAV) y
  [pyvirtualcam](https://github.com/letmaik/pyvirtualcam).
