#!/usr/bin/env bash
# GoGoCam para Linux: instalador para tu usuario.
#
#   ./instalar.sh
#
# Deja GoGoCam en ~/.local/share/gogocam (la app y su entorno de Python), un acceso
# en el menú de aplicaciones y el comando «gogocam». Pide tu clave (sudo) solo para
# instalar adb, Tk y la cámara virtual (v4l2loopback), y para configurarla.
# Se puede correr de nuevo sin problema: también sirve para actualizar.
set -euo pipefail

ORIGEN="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATOS="${XDG_DATA_HOME:-$HOME/.local/share}"
DESTINO="$DATOS/gogocam"
APP="$DESTINO/app"
VENV="$DESTINO/venv"
BIN="$HOME/.local/bin"
MENU="$DATOS/applications"
ICONOS="$DATOS/icons/hicolor"
OPCIONES_CAMARA=/etc/modprobe.d/gogocam.conf
CARGA_CAMARA=/etc/modules-load.d/gogocam.conf
CAMARA_PENDIENTE=0
VOLVER_A_ENTRAR=0

paso()  { printf '\n\033[1;33m==> %s\033[0m\n' "$*"; }
bien()  { printf '\033[1;32m%s\033[0m\n' "$*"; }
aviso() { printf '\033[1;31m%s\033[0m\n' "$*" >&2; }

if [ "$(id -u)" -eq 0 ]; then
    aviso "Corre ./instalar.sh con tu usuario normal, sin sudo: la clave se pide cuando hace falta."
    exit 1
fi
if [ ! -f "$ORIGEN/gogocam/__init__.py" ]; then
    aviso "Corre instalar.sh desde la carpeta descomprimida de GoGoCam."
    exit 1
fi
case "$(uname -m)" in
    x86_64|amd64) ;;
    *) aviso "Aviso: GoGoCam está preparado para PCs x86_64; en $(uname -m) puede que falten paquetes." ;;
esac

# --------------------------------------------------------------------------- 1
paso "1/5 · Paquetes del sistema: adb, Python con Tk y la cámara virtual"
if command -v apt-get >/dev/null 2>&1; then          # Ubuntu, Mint, Pop!_OS, Debian…
    sudo apt-get update
    # Los headers van antes: v4l2loopback-dkms compila el módulo contra el kernel en uso.
    sudo apt-get install -y "linux-headers-$(uname -r)" || aviso "No encontré los headers de tu kernel; sigo igual."
    sudo apt-get install -y adb python3 python3-venv python3-tk v4l2loopback-dkms
elif command -v dnf >/dev/null 2>&1; then            # Fedora
    sudo dnf install -y android-tools python3 python3-tkinter
    sudo dnf install -y v4l2loopback || aviso "v4l2loopback viene de RPM Fusion: actívalo (https://rpmfusion.org/Configuration) y vuelve a correr ./instalar.sh."
elif command -v pacman >/dev/null 2>&1; then         # Arch, Manjaro, EndeavourOS
    sudo pacman -S --needed --noconfirm android-tools android-udev python tk v4l2loopback-dkms \
        || aviso "Revisa el error de pacman. v4l2loopback-dkms necesita los headers de tu kernel (linux-headers o el de tu kernel)."
elif command -v zypper >/dev/null 2>&1; then         # openSUSE
    sudo zypper --non-interactive install android-tools python3 python3-tk v4l2loopback-kmp-default \
        || aviso "Revisa el error de zypper e instala a mano lo que falte."
else
    aviso "No reconozco tu distribución. Instala a mano adb, Python 3 (con venv y Tk) y v4l2loopback; sigo con lo que haya."
fi

PY="$(command -v python3 || true)"
if [ -z "$PY" ]; then
    aviso "Falta Python 3."
    exit 1
fi
if ! "$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)'; then
    aviso "GoGoCam necesita Python 3.10 o más nuevo; este es $("$PY" -V 2>&1)."
    exit 1
fi
if ! "$PY" -c 'import tkinter' 2>/dev/null; then
    aviso "Falta Tk para Python (python3-tk o python3-tkinter): sin eso la ventana no abre."
    exit 1
fi
if ! command -v adb >/dev/null 2>&1; then
    aviso "Falta adb (paquete adb o android-tools): sin eso GoGoCam no le habla al teléfono."
    exit 1
fi

# --------------------------------------------------------------------------- 2
paso "2/5 · Cámara virtual «GoGoCam» (v4l2loopback)"
if grep -q '^v4l2loopback ' /proc/modules; then
    bien "v4l2loopback ya estaba cargado; no lo toco (puede que OBS lo use con su propia configuración)."
else
    if [ ! -f "$OPCIONES_CAMARA" ] && grep -rqs 'options v4l2loopback' /etc/modprobe.d/; then
        echo "Ya hay una configuración de v4l2loopback en /etc/modprobe.d: la respeto."
    elif [ ! -f "$OPCIONES_CAMARA" ]; then
        # video_nr=10 la aleja de las webcams reales; exclusive_caps=1 hace que Chrome y Meet la vean.
        echo 'options v4l2loopback devices=1 video_nr=10 card_label=GoGoCam exclusive_caps=1' \
            | sudo tee "$OPCIONES_CAMARA" >/dev/null
    fi
    echo v4l2loopback | sudo tee "$CARGA_CAMARA" >/dev/null   # que cargue sola al encender
    if sudo modprobe v4l2loopback; then
        bien "Cámara virtual lista."
    else
        CAMARA_PENDIENTE=1
        aviso "No pude cargar la cámara virtual todavía. Lo más común:"
        aviso "  · Secure Boot: reinicia; en la pantalla azul elige «Enroll MOK» y escribe la clave que te pidió la instalación."
        aviso "  · Faltan los headers del kernel: instálalos y vuelve a correr ./instalar.sh."
    fi
fi
if [ "$CAMARA_PENDIENTE" = 0 ]; then
    sudo udevadm settle 2>/dev/null || true
    for dispositivo in /sys/devices/virtual/video4linux/video*; do
        [ -e "$dispositivo" ] || continue
        if [ ! -w "/dev/$(basename "$dispositivo")" ]; then
            sudo usermod -aG video "${USER:-$(id -un)}"
            VOLVER_A_ENTRAR=1
        fi
        break
    done
fi

# --------------------------------------------------------------------------- 3
paso "3/5 · Copiando GoGoCam a $APP"
mkdir -p "$DESTINO"
rm -rf "$APP.nuevo"
mkdir -p "$APP.nuevo"
cp -r "$ORIGEN/gogocam" "$ORIGEN/vendor" "$ORIGEN/recursos" "$ORIGEN/requirements-linux.txt" "$APP.nuevo/"
rm -rf "$APP"
mv "$APP.nuevo" "$APP"

# --------------------------------------------------------------------------- 4
paso "4/5 · Entorno de Python (la primera vez descarga unos 100 MB)"
if [ -x "$VENV/bin/python" ] && ! "$VENV/bin/python" -c 'import sys' 2>/dev/null; then
    rm -rf "$VENV"   # el Python del sistema cambió de versión: se arma de nuevo
fi
if [ ! -x "$VENV/bin/python" ]; then
    if ! "$PY" -m venv "$VENV"; then
        rm -rf "$VENV"
        aviso "No pude crear el entorno de Python. En Ubuntu, Mint o Debian: sudo apt install python3-venv"
        exit 1
    fi
fi
"$VENV/bin/python" -m pip install --upgrade --quiet pip
# Solo paquetes listos: compilar PyAV a mano necesita las bibliotecas de desarrollo de FFmpeg.
"$VENV/bin/python" -m pip install --upgrade --only-binary=:all: -r "$APP/requirements-linux.txt"

# --------------------------------------------------------------------------- 5
paso "5/5 · Menú de aplicaciones y comando «gogocam»"
mkdir -p "$BIN" "$MENU"
cat > "$BIN/gogocam" <<EOF
#!/bin/sh
# Abre GoGoCam (lo creó instalar.sh). Acepta sus argumentos, por ejemplo: gogocam --diagnostico
cd "$APP" && exec "$VENV/bin/python" -m gogocam "\$@"
EOF
chmod +x "$BIN/gogocam"
for tamano in 256 48 32 16; do
    if [ "$tamano" = 256 ]; then
        origen_icono="$APP/recursos/gogocam.png"
    else
        origen_icono="$APP/recursos/gogocam-$tamano.png"
    fi
    mkdir -p "$ICONOS/${tamano}x${tamano}/apps"
    cp "$origen_icono" "$ICONOS/${tamano}x${tamano}/apps/gogocam.png"
done
cat > "$MENU/gogocam.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=GoGoCam
GenericName=Cámara web
Comment=La cámara del teléfono como cámara web
Exec="$BIN/gogocam"
Icon=gogocam
Terminal=false
Categories=AudioVideo;Video;
Keywords=webcam;camara;camera;android;
StartupWMClass=Gogocam
EOF
update-desktop-database "$MENU" >/dev/null 2>&1 || true
gtk-update-icon-cache -q -t "$ICONOS" >/dev/null 2>&1 || true

# --------------------------------------------------------------------------- fin
paso "Revisión final (no toca el teléfono)"
"$BIN/gogocam" --diagnostico || true
echo
if [ "$CAMARA_PENDIENTE" = 1 ]; then
    aviso "Falta la cámara virtual: reinicia el PC (con Secure Boot, acepta «Enroll MOK») y corre ./instalar.sh otra vez."
fi
if [ "$VOLVER_A_ENTRAR" = 1 ]; then
    aviso "Te agregué al grupo «video»: cierra sesión y vuelve a entrar antes de usar GoGoCam."
fi
bien "Listo. Abre GoGoCam desde el menú de aplicaciones (o escribe gogocam en una terminal)."
case ":$PATH:" in
    *":$BIN:"*) ;;
    *) echo "El comando «gogocam» funciona después de cerrar sesión; mientras tanto: $BIN/gogocam" ;;
esac
echo "En Meet, Zoom o Discord elige la cámara «GoGoCam» DESPUÉS de presionar Iniciar en GoGoCam."
