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

- **Cámara** (trasera/frontal) y **Calidad** (1080p/720p) se eligen antes de
  iniciar.
- **Rotación** y **Espejo** se cambian en vivo. Si el teléfono está vertical,
  usa 90° o 270°.
- Los ajustes se recuerdan en `%LOCALAPPDATA%\GoGoCam\ajustes.json` y el
  registro queda en `%LOCALAPPDATA%\GoGoCam\gogocam.log`.

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
```

`prueba_sin_telefono.py` levanta un teléfono falso que habla el mismo protocolo
y comprueba, leyendo la cámara virtual con ffmpeg, que llega la imagen real y no
el relleno de OBS. Revisa también las capturas que guarda.

Estructura:

- `gogocam/core.py`: adb, servidor del teléfono, decodificación y cámara virtual.
- `gogocam/protocolo.py`: lectura del flujo de scrcpy v5.0.1 (verificado contra
  `Streamer.java` y `DesktopConnection.java` de esa versión).
- `gogocam/frames.py`: rotación y espejo sobre I420, sin pasar por RGB.
- `gogocam/ui.py`: la ventana (Tkinter).

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
