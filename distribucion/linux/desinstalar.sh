#!/usr/bin/env bash
# Quita GoGoCam: la app, su entorno de Python, tus ajustes y el registro, el acceso del
# menú, el comando «gogocam», el arranque automático y la configuración de la cámara
# virtual. NO desinstala adb, Python ni v4l2loopback: puede que otros programas los usen.
set -euo pipefail

DATOS="${XDG_DATA_HOME:-$HOME/.local/share}"
CONFIG="${XDG_CONFIG_HOME:-$HOME/.config}"

rm -rf "$DATOS/gogocam"
rm -f "$HOME/.local/bin/gogocam" "$DATOS/applications/gogocam.desktop" "$CONFIG/autostart/gogocam.desktop"
for tamano in 256 48 32 16; do
    rm -f "$DATOS/icons/hicolor/${tamano}x${tamano}/apps/gogocam.png"
done
if [ -e /etc/modprobe.d/gogocam.conf ] || [ -e /etc/modules-load.d/gogocam.conf ]; then
    echo "Quitando la configuración de la cámara virtual (pide tu clave)…"
    sudo rm -f /etc/modprobe.d/gogocam.conf /etc/modules-load.d/gogocam.conf
    echo "La cámara virtual sigue cargada hasta que reinicies."
fi
update-desktop-database "$DATOS/applications" >/dev/null 2>&1 || true
echo "GoGoCam quedó desinstalado."
