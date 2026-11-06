"""Ventana de GoGoCam (Tkinter, sin dependencias extra)."""
from __future__ import annotations

import json
import logging
import tkinter as tk
from pathlib import Path
from tkinter import ttk
from typing import Callable, Optional

from . import sistema
from .core import (
    ES_WINDOWS, NOMBRE_CAMARA_VIRTUAL, ZOOM_PASO_MAX, Ajustes, Transmision, sin_modo_eficiencia, zoom_de_paso,
)

log = logging.getLogger("gogocam")

CAMARAS = {"Trasera": "back", "Frontal": "front"}
RESOLUCIONES = ("1080p", "720p")
FORMATOS = ("16:9", "4:3")
TAMANOS = {  # todas existen en las dos cámaras del Redmi (--list-camera-sizes)
    ("1080p", "16:9"): "1920x1080", ("1080p", "4:3"): "1440x1080",
    ("720p", "16:9"): "1280x720", ("720p", "4:3"): "960x720",
}
FPS = {"30 fps": 30, "20 fps": 20, "15 fps": 15}
BITRATES = {"Normal (8 Mbps)": 8_000_000, "Alta (12 Mbps)": 12_000_000, "Máxima (20 Mbps)": 20_000_000}
ROTACIONES = {"0°": 0, "90°": 90, "180°": 180, "270°": 270}
BRILLO = (-50, 50)
CONTRASTE = (50, 150)

TICK_MS = 30  # la vista previa llega a ~10 fps; revisar cada 30 ms la muestra pareja
TICK_MINIMIZADA_MS = 250  # minimizada solo se atienden avisos (errores, fin)
GUARDAR_TRAS_MS = 400  # los deslizadores guardan al soltarlos, no en cada movimiento
# DejaVu Sans viene en casi todas las distribuciones; si falta, Tk elige la más parecida.
FAMILIA = "Segoe UI" if ES_WINDOWS else "DejaVu Sans"
FUENTE = (FAMILIA, 10)
FUENTE_NEGRITA = ("Segoe UI Semibold", 10) if ES_WINDOWS else (FAMILIA, 10, "bold")

# Colores de GoGoDevS: navy #0A1428, ámbar #FFB627, azul #2563EB, gris #A8B3CF
PALETAS = {
    True: dict(fondo="#0A1428", campo="#14223F", borde="#26365A", texto="#F5F6F8", tenue="#A8B3CF",
               acento="#FFB627", acento_activo="#FFC654", sobre_acento="#0A1428",
               ok="#4ADE80", error="#F87171", info="#A8B3CF", vista="#050A14", vista_texto="#5B6A8C",
               riel="#14223F"),
    False: dict(fondo="#F5F6F8", campo="#FFFFFF", borde="#C9D1E3", texto="#0A1428", tenue="#5B6680",
                acento="#FFB627", acento_activo="#FFC654", sobre_acento="#0A1428",
                ok="#1A7F37", error="#C62828", info="#5B6680", vista="#0A1428", vista_texto="#5B6A8C",
                riel="#D9DFEA"),
}


# ---------------------------------------------------------------- ajustes

def _clave(diccionario: dict, valor) -> str:
    for k, v in diccionario.items():
        if v == valor:
            return k
    return next(iter(diccionario))


def partes_de_tamano(tamano: str) -> tuple[str, str]:
    for partes, valor in TAMANOS.items():
        if valor == tamano:
            return partes
    return RESOLUCIONES[0], FORMATOS[0]


def cargar_ajustes(archivo: Path) -> Ajustes:
    ajustes = Ajustes()
    try:
        datos = json.loads(archivo.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ajustes
    if not isinstance(datos, dict):
        return ajustes

    def entero(clave: str, minimo: int, maximo: int, defecto: int) -> int:
        valor = datos.get(clave, defecto)
        if isinstance(valor, bool) or not isinstance(valor, (int, float)):
            return defecto
        return min(max(int(valor), minimo), maximo)

    def opcion(clave: str, validos, defecto):
        valor = datos.get(clave, defecto)
        return valor if valor in validos else defecto

    ajustes.camara = opcion("camara", CAMARAS.values(), ajustes.camara)
    ajustes.tamano = opcion("tamano", TAMANOS.values(), ajustes.tamano)
    ajustes.fps = opcion("fps", FPS.values(), ajustes.fps)
    ajustes.bitrate = opcion("bitrate", BITRATES.values(), ajustes.bitrate)
    ajustes.rotacion = opcion("rotacion", ROTACIONES.values(), ajustes.rotacion)
    ajustes.brillo = entero("brillo", *BRILLO, ajustes.brillo)
    ajustes.contraste = entero("contraste", *CONTRASTE, ajustes.contraste)
    ajustes.zoom_paso = entero("zoom_paso", 0, ZOOM_PASO_MAX, ajustes.zoom_paso)
    for clave in ("espejo", "linterna", "vista_previa", "autoiniciar", "tema_oscuro"):
        valor = datos.get(clave)
        if isinstance(valor, bool):
            setattr(ajustes, clave, valor)
    return ajustes


def guardar_ajustes(archivo: Path, ajustes: Ajustes) -> None:
    try:
        archivo.write_text(json.dumps(ajustes.a_dict(), indent=2), encoding="utf-8")
    except OSError:
        log.exception("no pude guardar los ajustes")


# ---------------------------------------------------------------- tema

def aplicar_tema(raiz: tk.Tk, oscuro: bool) -> dict:
    p = PALETAS[oscuro]
    s = ttk.Style(raiz)
    s.theme_use("clam")  # el tema nativo de Windows ignora los colores
    s.configure(".", background=p["fondo"], foreground=p["texto"], fieldbackground=p["campo"],
                bordercolor=p["borde"], lightcolor=p["fondo"], darkcolor=p["fondo"],
                troughcolor=p["campo"], focuscolor=p["fondo"], selectbackground=p["campo"],
                selectforeground=p["texto"], insertcolor=p["texto"], font=FUENTE)
    s.map(".", foreground=[("disabled", p["tenue"])])
    s.configure("Tenue.TLabel", foreground=p["tenue"])
    s.configure("Valor.TLabel", foreground=p["tenue"], width=6, anchor="e")
    s.configure("TButton", background=p["campo"], foreground=p["texto"], bordercolor=p["borde"],
                lightcolor=p["campo"], darkcolor=p["campo"], padding=(12, 6))
    # Desactivado = plano, del color del fondo y con texto tenue: que no parezca un botón vivo
    s.map("TButton", background=[("disabled", p["fondo"]), ("active", p["borde"])],
          lightcolor=[("disabled", p["fondo"]), ("active", p["borde"])],
          darkcolor=[("disabled", p["fondo"]), ("active", p["borde"])],
          foreground=[("disabled", p["tenue"])])
    s.configure("Acento.TButton", background=p["acento"], foreground=p["sobre_acento"],
                bordercolor=p["acento"], lightcolor=p["acento"], darkcolor=p["acento"], font=FUENTE_NEGRITA)
    s.map("Acento.TButton",
          background=[("disabled", p["fondo"]), ("active", p["acento_activo"])],
          lightcolor=[("disabled", p["fondo"]), ("active", p["acento_activo"])],
          darkcolor=[("disabled", p["fondo"]), ("active", p["acento_activo"])],
          bordercolor=[("disabled", p["borde"])], foreground=[("disabled", p["tenue"])])
    s.configure("TCheckbutton", indicatorbackground=p["campo"], indicatorforeground=p["sobre_acento"],
                upperbordercolor=p["borde"], lowerbordercolor=p["borde"], padding=(0, 3))
    s.map("TCheckbutton", background=[("active", p["fondo"])],
          indicatorbackground=[("disabled", p["fondo"]), ("selected", p["acento"])])
    s.configure("TCombobox", fieldbackground=p["campo"], background=p["campo"], foreground=p["texto"],
                arrowcolor=p["texto"], bordercolor=p["borde"], lightcolor=p["campo"],
                darkcolor=p["campo"], padding=4)
    s.map("TCombobox", fieldbackground=[("disabled", p["fondo"]), ("readonly", p["campo"])],
          foreground=[("disabled", p["tenue"])],
          arrowcolor=[("disabled", p["tenue"]), ("readonly", p["texto"])],
          background=[("disabled", p["fondo"]), ("active", p["borde"]), ("readonly", p["campo"])],
          lightcolor=[("readonly", p["campo"])], darkcolor=[("readonly", p["campo"])],
          selectbackground=[("readonly", p["campo"])], selectforeground=[("readonly", p["texto"])])
    s.configure("TNotebook", background=p["fondo"], bordercolor=p["borde"], lightcolor=p["fondo"],
                darkcolor=p["fondo"], tabmargins=(0, 0, 0, 0))
    s.configure("TNotebook.Tab", background=p["campo"], foreground=p["tenue"], bordercolor=p["borde"],
                lightcolor=p["campo"], darkcolor=p["campo"], padding=(14, 5))
    s.map("TNotebook.Tab", background=[("selected", p["fondo"])], foreground=[("selected", p["texto"])],
          lightcolor=[("selected", p["fondo"])], darkcolor=[("selected", p["fondo"])])
    raiz.configure(bg=p["fondo"])
    for opcion, valor in (("background", p["campo"]), ("foreground", p["texto"]),
                          ("selectBackground", p["acento"]), ("selectForeground", p["sobre_acento"])):
        raiz.option_add(f"*TCombobox*Listbox.{opcion}", valor)
    return p


# ---------------------------------------------------------------- ventana

class App:
    def __init__(self, raiz: tk.Tk, carpeta_datos: Path):
        self.raiz = raiz
        self.archivo_ajustes = carpeta_datos / "ajustes.json"
        self.ajustes = cargar_ajustes(self.archivo_ajustes)
        self.transmision: Optional[Transmision] = None
        self._imagen: Optional[tk.PhotoImage] = None
        self._tamano_imagen: tuple = ()
        self._ultima_muestra: Optional[bytes] = None
        self._guardado_pendiente: Optional[str] = None
        self._tipo_estado = "info"
        self.combos: list[ttk.Combobox] = []
        self.escalas: list[tk.Scale] = []
        self.paleta = aplicar_tema(raiz, self.ajustes.tema_oscuro)

        raiz.title("GoGoCam")
        raiz.resizable(False, False)
        self._iconos = [tk.PhotoImage(file=str(ruta)) for ruta in sistema.iconos_png()]
        if self._iconos:
            raiz.iconphoto(True, *self._iconos)
        marco = ttk.Frame(raiz, padding=12)
        marco.grid(sticky="nsew")

        # Vista previa
        self.caja = tk.Frame(marco, width=400, height=260, bg=self.paleta["vista"])
        self.caja.grid(row=0, column=0, sticky="ew")
        self.caja.grid_propagate(False)
        self.caja.columnconfigure(0, weight=1)
        self.caja.rowconfigure(0, weight=1)
        self.vista = tk.Label(self.caja, bg=self.paleta["vista"], fg=self.paleta["vista_texto"],
                              text="Sin imagen", font=(FAMILIA, 11))
        self.vista.grid(row=0, column=0)

        self.cuaderno = ttk.Notebook(marco)
        self.cuaderno.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        self._pestana_imagen(self.cuaderno)
        self._pestana_calidad(self.cuaderno)
        self._pestana_opciones(self.cuaderno)

        # Botones
        botones = ttk.Frame(marco)
        botones.grid(row=2, column=0, pady=(12, 6), sticky="ew")
        botones.columnconfigure((0, 1), weight=1)
        self.boton_iniciar = ttk.Button(botones, text="Iniciar", style="Acento.TButton", command=self.iniciar)
        self.boton_iniciar.grid(row=0, column=0, sticky="ew", padx=(0, 4))
        self.boton_detener = ttk.Button(botones, text="Detener", command=self.detener, state="disabled")
        self.boton_detener.grid(row=0, column=1, sticky="ew", padx=(4, 0))

        # Estado
        self.estado = ttk.Label(marco, wraplength=400, justify="left")
        self.estado.grid(row=3, column=0, sticky="ew")
        self._poner_estado("info", "Detenida. Conecta el teléfono por USB y presiona Iniciar.")
        self.datos = ttk.Label(marco, text="", style="Tenue.TLabel")
        self.datos.grid(row=4, column=0, sticky="w")

        self._actualizar_linterna()
        sistema.barra_titulo_oscura(raiz, self.ajustes.tema_oscuro)
        raiz.protocol("WM_DELETE_WINDOW", self.cerrar)
        raiz.after(TICK_MS, self._tick)
        if self.ajustes.autoiniciar:
            raiz.after(400, self.iniciar)

    # -- pestañas

    def _pestana_imagen(self, cuaderno: ttk.Notebook) -> None:
        p = ttk.Frame(cuaderno, padding=(10, 10, 10, 6))
        cuaderno.add(p, text="Imagen")
        p.columnconfigure(1, weight=1)
        self.brillo = self._deslizador(p, 0, "Brillo", *BRILLO, self.ajustes.brillo,
                                       lambda v: f"{v:+d}", self._cambio_brillo)
        self.contraste = self._deslizador(p, 1, "Contraste", *CONTRASTE, self.ajustes.contraste,
                                          lambda v: f"{v} %", self._cambio_contraste)
        self.zoom = self._deslizador(p, 2, "Zoom", 0, ZOOM_PASO_MAX, self.ajustes.zoom_paso,
                                     lambda v: f"{zoom_de_paso(v):.1f}x", self._cambio_zoom)

        fila = ttk.Frame(p)
        fila.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        ttk.Label(fila, text="Rotación").grid(row=0, column=0, sticky="w")
        self.combo_rotacion = self._combo(fila, ROTACIONES, self.ajustes.rotacion, self._cambio_rotacion, 6)
        self.combo_rotacion.grid(row=0, column=1, padx=(8, 16))
        self.var_espejo = tk.BooleanVar(value=self.ajustes.espejo)
        ttk.Checkbutton(fila, text="Espejo", variable=self.var_espejo,
                        command=self._cambio_espejo).grid(row=0, column=2, padx=(0, 16))
        self.var_linterna = tk.BooleanVar(value=self.ajustes.linterna)
        self.check_linterna = ttk.Checkbutton(fila, text="Linterna", variable=self.var_linterna,
                                              command=self._cambio_linterna)
        self.check_linterna.grid(row=0, column=3)
        ttk.Button(p, text="Restablecer imagen", command=self._restablecer_imagen).grid(
            row=4, column=0, columnspan=3, sticky="e", pady=(10, 0))

    def _pestana_calidad(self, cuaderno: ttk.Notebook) -> None:
        p = ttk.Frame(cuaderno, padding=(10, 10, 10, 6))
        cuaderno.add(p, text="Calidad")
        p.columnconfigure((1, 3), weight=1)
        resolucion, formato = partes_de_tamano(self.ajustes.tamano)
        filas = (
            ("Cámara", self._combo(p, CAMARAS, self.ajustes.camara, self._cambio_camara)),
            ("Resolución", self._combo(p, {r: r for r in RESOLUCIONES}, resolucion, self._cambio_tamano)),
            ("Formato", self._combo(p, {f: f for f in FORMATOS}, formato, self._cambio_tamano)),
            ("FPS", self._combo(p, FPS, self.ajustes.fps, self._cambio_fps)),
            ("Bitrate", self._combo(p, BITRATES, self.ajustes.bitrate, self._cambio_bitrate, 16)),
        )
        self.combos_fijos = [combo for _, combo in filas]
        self.combo_resolucion, self.combo_formato = filas[1][1], filas[2][1]
        for i, (texto, combo) in enumerate(filas):
            fila, columna = divmod(i, 2)
            ttk.Label(p, text=texto).grid(row=fila, column=columna * 2, sticky="w", pady=3)
            combo.grid(row=fila, column=columna * 2 + 1, sticky="ew", padx=(8, 16 if columna == 0 else 0), pady=3)
        ttk.Label(p, text="Se aplica al presionar Iniciar. Con poca luz usa 20 fps: la cámara alcanza "
                          "a tomar más luz y la imagen sale mucho más clara que a 30.",
                  style="Tenue.TLabel", wraplength=370).grid(row=3, column=0, columnspan=4, sticky="w", pady=(8, 0))

    def _pestana_opciones(self, cuaderno: ttk.Notebook) -> None:
        p = ttk.Frame(cuaderno, padding=(10, 10, 10, 6))
        cuaderno.add(p, text="Opciones")
        self.var_vista = tk.BooleanVar(value=self.ajustes.vista_previa)
        self.var_autoiniciar = tk.BooleanVar(value=self.ajustes.autoiniciar)
        self.var_al_encender = tk.BooleanVar(value=sistema.abre_al_encender())
        self.var_tema = tk.BooleanVar(value=self.ajustes.tema_oscuro)
        for i, (texto, var, accion) in enumerate((
            ("Vista previa en la ventana", self.var_vista, self._cambio_vista),
            ("Empezar a transmitir al abrir GoGoCam", self.var_autoiniciar, self._cambio_autoiniciar),
            ("Abrir GoGoCam al encender el PC (minimizada)", self.var_al_encender, self._cambio_al_encender),
            ("Tema oscuro", self.var_tema, self._cambio_tema),
        )):
            ttk.Checkbutton(p, text=texto, variable=var, command=accion).grid(row=i, column=0, sticky="w")

    # -- piezas

    def _combo(self, padre, opciones: dict, valor, al_cambiar, ancho: int = 10) -> ttk.Combobox:
        combo = ttk.Combobox(padre, values=list(opciones), state="readonly", width=ancho)
        combo.set(_clave(opciones, valor))
        combo.bind("<<ComboboxSelected>>", lambda _e: (combo.selection_clear(), al_cambiar(opciones[combo.get()])))
        self.combos.append(combo)
        return combo

    def _deslizador(self, padre, fila: int, texto: str, minimo: int, maximo: int, valor: int,
                    formato: Callable[[int], str], al_cambiar: Callable[[int], None]) -> tk.IntVar:
        ttk.Label(padre, text=texto).grid(row=fila, column=0, sticky="w", pady=2)
        var = tk.IntVar(value=valor)
        etiqueta = ttk.Label(padre, text=formato(valor), style="Valor.TLabel")

        def mover(crudo: str) -> None:
            v = int(round(float(crudo)))
            if v != var.get():
                var.set(v)
            etiqueta.configure(text=formato(v))
            al_cambiar(v)

        # tk.Scale y no ttk.Scale: en el tema clam el borde del riel y el del control comparten
        # color y el control se dibuja partido. Aquí cada color se elige directo.
        escala = tk.Scale(padre, from_=minimo, to=maximo, orient="horizontal", length=250,
                          resolution=1, showvalue=False, bd=0, highlightthickness=0,
                          sliderrelief="flat", sliderlength=18, width=10, command=mover)
        self._colorear_escala(escala)
        self.escalas.append(escala)
        escala.set(valor)
        escala.grid(row=fila, column=1, sticky="ew", padx=(10, 8), pady=2)
        etiqueta.grid(row=fila, column=2, sticky="e")
        var.trace_add("write", lambda *_: (escala.set(var.get()), etiqueta.configure(text=formato(var.get()))))
        return var

    def _colorear_escala(self, escala: tk.Scale) -> None:
        p = self.paleta
        escala.configure(bg=p["acento"], activebackground=p["acento_activo"], troughcolor=p["riel"])

    # -- cambios (los de la pestaña Imagen aplican en vivo: la transmisión lee self.ajustes)

    def _cambio_brillo(self, v: int) -> None:
        self.ajustes.brillo = v
        self._guardar_luego()

    def _cambio_contraste(self, v: int) -> None:
        self.ajustes.contraste = v
        self._guardar_luego()

    def _cambio_zoom(self, v: int) -> None:
        self.ajustes.zoom_paso = v
        self._guardar_luego()

    def _cambio_rotacion(self, valor: int) -> None:
        self.ajustes.rotacion = valor
        self._guardar()

    def _cambio_espejo(self) -> None:
        self.ajustes.espejo = self.var_espejo.get()
        self._guardar()

    def _cambio_linterna(self) -> None:
        self.ajustes.linterna = self.var_linterna.get()
        self._guardar()

    def _restablecer_imagen(self) -> None:
        self.brillo.set(0)
        self.contraste.set(100)
        self.zoom.set(0)
        self.combo_rotacion.set(_clave(ROTACIONES, 0))
        self.var_espejo.set(False)
        self.var_linterna.set(False)
        self.ajustes.brillo, self.ajustes.contraste, self.ajustes.zoom_paso = 0, 100, 0
        self.ajustes.rotacion, self.ajustes.espejo, self.ajustes.linterna = 0, False, False
        self._guardar()

    def _cambio_camara(self, valor: str) -> None:
        self.ajustes.camara = valor
        self._actualizar_linterna()
        self._guardar()

    def _cambio_tamano(self, _valor: str) -> None:
        self.ajustes.tamano = TAMANOS[(self.combo_resolucion.get(), self.combo_formato.get())]
        self._guardar()

    def _cambio_fps(self, valor: int) -> None:
        self.ajustes.fps = valor
        self._guardar()

    def _cambio_bitrate(self, valor: int) -> None:
        self.ajustes.bitrate = valor
        self._guardar()

    def _cambio_vista(self) -> None:
        self.ajustes.vista_previa = self.var_vista.get()
        if not self.ajustes.vista_previa:
            self._mostrar_sin_imagen("Vista previa apagada")
        self._guardar()

    def _cambio_autoiniciar(self) -> None:
        self.ajustes.autoiniciar = self.var_autoiniciar.get()
        self._guardar()

    def _cambio_al_encender(self) -> None:
        pedido = self.var_al_encender.get()
        try:
            sistema.abrir_al_encender(pedido)
        except OSError as e:
            log.exception("no pude cambiar el arranque al encender")
            self.var_al_encender.set(sistema.abre_al_encender())
            self._poner_estado("error", f"No pude cambiar el arranque al encender: {e}")
            return
        self._poner_estado("info", "GoGoCam se abrirá minimizada al encender el PC." if pedido
                           else "GoGoCam ya no se abre al encender el PC.")

    def _cambio_tema(self) -> None:
        self.ajustes.tema_oscuro = self.var_tema.get()
        self.paleta = aplicar_tema(self.raiz, self.ajustes.tema_oscuro)
        for widget in (self.caja, self.vista):
            widget.configure(bg=self.paleta["vista"])
        for escala in self.escalas:
            self._colorear_escala(escala)
        self.vista.configure(fg=self.paleta["vista_texto"])
        for combo in self.combos:  # la lista desplegable ya creada no lee option_add
            try:
                lista = f"{combo.tk.call('ttk::combobox::PopdownWindow', combo)}.f.l"
                combo.tk.call(lista, "configure", "-background", self.paleta["campo"],
                              "-foreground", self.paleta["texto"])
            except tk.TclError:
                pass
        self._poner_estado(self._tipo_estado, self.estado.cget("text"))
        sistema.barra_titulo_oscura(self.raiz, self.ajustes.tema_oscuro)
        self._refrescar_marco()
        self._guardar()

    def _refrescar_marco(self) -> None:
        # Windows repinta la barra de título al cambiar el tamaño de la ventana.
        self.raiz.update_idletasks()
        ancho, alto = self.raiz.winfo_width(), self.raiz.winfo_height()
        self.raiz.geometry(f"{ancho + 1}x{alto}")
        self.raiz.update_idletasks()
        self.raiz.geometry("")

    def _actualizar_linterna(self) -> None:
        # Solo la cámara trasera tiene flash.
        self.check_linterna.configure(state="normal" if self.ajustes.camara == "back" else "disabled")

    def _guardar_luego(self) -> None:
        if self._guardado_pendiente is not None:
            self.raiz.after_cancel(self._guardado_pendiente)
        self._guardado_pendiente = self.raiz.after(GUARDAR_TRAS_MS, self._guardar)

    def _guardar(self) -> None:
        self._guardado_pendiente = None
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
        # La pestaña Calidad se fija al arrancar; la pestaña Imagen se cambia en vivo.
        for combo in self.combos_fijos:
            combo.configure(state="disabled" if activa else "readonly")

    def _poner_estado(self, tipo: str, texto: str) -> None:
        self._tipo_estado = tipo
        self.estado.configure(text=texto, foreground=self.paleta.get(tipo, self.paleta["info"]))

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
        minimizada = self.raiz.state() == "iconic"
        transmitiendo = t is not None and t.activa and t.cuadros > 0
        titulo = "GoGoCam · transmitiendo" if transmitiendo else "GoGoCam"
        if self.raiz.title() != titulo:  # minimizada, se lee en la barra de tareas
            self.raiz.title(titulo)
        if t is not None:
            t.vista_oculta = minimizada  # minimizada no se arma la vista previa: la reunión sigue igual
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
                if (not minimizada and self.ajustes.vista_previa and muestra is not None
                        and muestra is not self._ultima_muestra):
                    self._pintar(muestra)
                if t.cuadros:
                    ancho, alto = t.tamano_salida
                    texto = f"{ancho}x{alto} · {t.fps:.0f} fps · «{t.dispositivo or NOMBRE_CAMARA_VIRTUAL}»"
                    if self.datos.cget("text") != texto:
                        self.datos.configure(text=texto)
        self.raiz.after(TICK_MINIMIZADA_MS if minimizada else TICK_MS, self._tick)


def ejecutar(carpeta_datos: Path, minimizada: bool = False) -> None:
    try:  # nitidez en pantallas con escala (125 %, 150 %…)
        import ctypes

        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (AttributeError, OSError):
        pass
    sin_modo_eficiencia()  # minimizada tiene que seguir a toda velocidad
    sistema.identificar_aplicacion()  # ícono propio en la barra de tareas
    raiz = tk.Tk(className=sistema.CLASE_VENTANA)  # Linux: el ícono del menú, no el de Python
    App(raiz, carpeta_datos)
    if minimizada:
        raiz.iconify()
    raiz.mainloop()
