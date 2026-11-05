"""Ventana de GoGoCam (Tkinter, sin dependencias extra)."""
from __future__ import annotations

import json
import logging
import tkinter as tk
from pathlib import Path
from tkinter import ttk
from typing import Optional

from .core import Ajustes, Transmision

log = logging.getLogger("gogocam")

CAMARAS = {"Trasera": "back", "Frontal": "front"}
CALIDADES = {"1080p (1920x1080)": "1920x1080", "720p (1280x720)": "1280x720"}
ROTACIONES = {"0°": 0, "90°": 90, "180°": 180, "270°": 270}
COLORES = {"info": "#555555", "ok": "#1a7f37", "error": "#c62828", "fin": "#555555"}
FONDO_VISTA = "#1e1e1e"
TICK_MS = 15  # más corto que un cuadro a 30 fps (33 ms): la vista previa no se salta cuadros


def _clave(diccionario: dict, valor) -> str:
    for k, v in diccionario.items():
        if v == valor:
            return k
    return next(iter(diccionario))


def cargar_ajustes(archivo: Path) -> Ajustes:
    ajustes = Ajustes()
    try:
        datos = json.loads(archivo.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ajustes
    if datos.get("camara") in CAMARAS.values():
        ajustes.camara = datos["camara"]
    if datos.get("tamano") in CALIDADES.values():
        ajustes.tamano = datos["tamano"]
    if datos.get("rotacion") in ROTACIONES.values():
        ajustes.rotacion = datos["rotacion"]
    ajustes.espejo = bool(datos.get("espejo", False))
    ajustes.vista_previa = bool(datos.get("vista_previa", True))
    return ajustes


def guardar_ajustes(archivo: Path, ajustes: Ajustes) -> None:
    try:
        archivo.write_text(json.dumps(ajustes.a_dict(), indent=2), encoding="utf-8")
    except OSError:
        log.exception("no pude guardar los ajustes")


class App:
    def __init__(self, raiz: tk.Tk, carpeta_datos: Path):
        self.raiz = raiz
        self.archivo_ajustes = carpeta_datos / "ajustes.json"
        self.ajustes = cargar_ajustes(self.archivo_ajustes)
        self.transmision: Optional[Transmision] = None
        self._imagen: Optional[tk.PhotoImage] = None
        self._tamano_imagen: tuple = ()
        self._ultima_muestra: Optional[bytes] = None

        raiz.title("GoGoCam")
        raiz.resizable(False, False)
        marco = ttk.Frame(raiz, padding=12)
        marco.grid(sticky="nsew")

        # Vista previa
        caja = tk.Frame(marco, width=400, height=260, bg=FONDO_VISTA)
        caja.grid(row=0, column=0, columnspan=4, pady=(0, 10))
        caja.grid_propagate(False)
        caja.columnconfigure(0, weight=1)
        caja.rowconfigure(0, weight=1)
        self.vista = tk.Label(caja, bg=FONDO_VISTA, fg="#9e9e9e", text="Sin imagen", font=("Segoe UI", 11))
        self.vista.grid(row=0, column=0)

        # Opciones
        ttk.Label(marco, text="Cámara").grid(row=1, column=0, sticky="w")
        self.combo_camara = self._combo(marco, CAMARAS, self.ajustes.camara, self._cambio_camara)
        self.combo_camara.grid(row=1, column=1, sticky="ew", padx=(6, 12))
        ttk.Label(marco, text="Calidad").grid(row=1, column=2, sticky="w")
        self.combo_calidad = self._combo(marco, CALIDADES, self.ajustes.tamano, self._cambio_calidad, ancho=17)
        self.combo_calidad.grid(row=1, column=3, sticky="ew", padx=(6, 0))

        ttk.Label(marco, text="Rotación").grid(row=2, column=0, sticky="w", pady=(8, 0))
        self.combo_rotacion = self._combo(marco, ROTACIONES, self.ajustes.rotacion, self._cambio_rotacion)
        self.combo_rotacion.grid(row=2, column=1, sticky="ew", padx=(6, 12), pady=(8, 0))
        self.var_espejo = tk.BooleanVar(value=self.ajustes.espejo)
        ttk.Checkbutton(marco, text="Espejo", variable=self.var_espejo, command=self._cambio_espejo).grid(
            row=2, column=2, sticky="w", pady=(8, 0)
        )
        self.var_vista = tk.BooleanVar(value=self.ajustes.vista_previa)
        ttk.Checkbutton(marco, text="Vista previa", variable=self.var_vista, command=self._cambio_vista).grid(
            row=2, column=3, sticky="w", pady=(8, 0)
        )

        # Botones
        botones = ttk.Frame(marco)
        botones.grid(row=3, column=0, columnspan=4, pady=(12, 6), sticky="ew")
        botones.columnconfigure((0, 1), weight=1)
        self.boton_iniciar = ttk.Button(botones, text="Iniciar", command=self.iniciar)
        self.boton_iniciar.grid(row=0, column=0, sticky="ew", padx=(0, 4))
        self.boton_detener = ttk.Button(botones, text="Detener", command=self.detener, state="disabled")
        self.boton_detener.grid(row=0, column=1, sticky="ew", padx=(4, 0))

        # Estado
        self.estado = tk.Label(marco, text="Detenida. Conecta el teléfono por USB y presiona Iniciar.",
                               fg=COLORES["info"], anchor="w", justify="left", wraplength=400)
        self.estado.grid(row=4, column=0, columnspan=4, sticky="ew")
        self.datos = ttk.Label(marco, text="", foreground="#777777")
        self.datos.grid(row=5, column=0, columnspan=4, sticky="w")

        raiz.protocol("WM_DELETE_WINDOW", self.cerrar)
        raiz.bind("<Return>", lambda _e: self.iniciar())
        raiz.after(TICK_MS, self._tick)

    @staticmethod
    def _combo(padre, opciones: dict, valor, al_cambiar, ancho: int = 10) -> ttk.Combobox:
        combo = ttk.Combobox(padre, values=list(opciones), state="readonly", width=ancho)
        combo.set(_clave(opciones, valor))
        combo.bind("<<ComboboxSelected>>", lambda _e: al_cambiar(opciones[combo.get()]))
        return combo

    # -- cambios de opciones (rotación, espejo y vista previa aplican en vivo)

    def _cambio_camara(self, valor: str) -> None:
        self.ajustes.camara = valor
        self._guardar()

    def _cambio_calidad(self, valor: str) -> None:
        self.ajustes.tamano = valor
        self._guardar()

    def _cambio_rotacion(self, valor: int) -> None:
        self.ajustes.rotacion = valor
        self._guardar()

    def _cambio_espejo(self) -> None:
        self.ajustes.espejo = self.var_espejo.get()
        self._guardar()

    def _cambio_vista(self) -> None:
        self.ajustes.vista_previa = self.var_vista.get()
        if not self.ajustes.vista_previa:
            self._mostrar_sin_imagen("Vista previa apagada")
        self._guardar()

    def _guardar(self) -> None:
        guardar_ajustes(self.archivo_ajustes, self.ajustes)

    # -- control

    def iniciar(self) -> None:
        if self.transmision is not None and self.transmision.activa:
            return
        self._guardar()
        self.transmision = Transmision(self.ajustes)  # mismo objeto: los cambios en vivo le llegan
        self.transmision.iniciar()
        self._en_marcha(True)
        self._poner_estado("info", "Arrancando…")

    def detener(self) -> None:
        if self.transmision is not None:
            self._poner_estado("info", "Deteniendo…")
            self.transmision.detener(esperar=0)

    def cerrar(self) -> None:
        self._guardar()
        if self.transmision is not None:
            self.transmision.detener(esperar=5)
        self.raiz.destroy()

    def _en_marcha(self, activa: bool) -> None:
        self.boton_iniciar.configure(state="disabled" if activa else "normal")
        self.boton_detener.configure(state="normal" if activa else "disabled")
        # Cámara y calidad se fijan al arrancar; rotación y espejo se pueden cambiar en vivo.
        estado = "disabled" if activa else "readonly"
        self.combo_camara.configure(state=estado)
        self.combo_calidad.configure(state=estado)

    def _poner_estado(self, tipo: str, texto: str) -> None:
        self.estado.configure(text=texto, fg=COLORES.get(tipo, COLORES["info"]))

    def _mostrar_sin_imagen(self, texto: str = "Sin imagen") -> None:
        self._imagen = None
        self._ultima_muestra = None
        self.vista.configure(image="", text=texto)

    def _pintar(self, muestra: bytes) -> None:
        """Muestra un cuadro PPM. Reutiliza la imagen si no cambió de tamaño (rotación)."""
        tamano = tuple(muestra.split(maxsplit=3)[1:3])  # cabecera b"P6 ancho alto 255\n"
        if self._imagen is None or tamano != self._tamano_imagen:
            self._imagen = tk.PhotoImage(data=muestra, format="PPM")
            self._tamano_imagen = tamano
            self.vista.configure(image=self._imagen, text="")
        else:
            self._imagen.configure(data=muestra, format="PPM")
        self._ultima_muestra = muestra

    def _tick(self) -> None:
        t = self.transmision
        if t is not None:
            while not t.eventos.empty():
                tipo, texto = t.eventos.get()
                if tipo == "fin":
                    self._en_marcha(False)
                    self._mostrar_sin_imagen()
                    self.datos.configure(text="")
                    if not t.error:
                        self._poner_estado("info", "Detenida.")
                else:
                    self._poner_estado(tipo, texto)
            if t.activa:
                muestra = t.vista_previa
                if self.ajustes.vista_previa and muestra is not None and muestra is not self._ultima_muestra:
                    self._pintar(muestra)
                if t.cuadros:
                    ancho, alto = t.tamano_salida
                    texto = f"{ancho}x{alto} · {t.fps:.0f} fps · «OBS Virtual Camera»"
                    if self.datos.cget("text") != texto:
                        self.datos.configure(text=texto)
        self.raiz.after(TICK_MS, self._tick)


def ejecutar(carpeta_datos: Path) -> None:
    try:  # nitidez en pantallas con escala (125 %, 150 %…)
        import ctypes

        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (AttributeError, OSError):
        pass
    raiz = tk.Tk()
    App(raiz, carpeta_datos)
    raiz.mainloop()
