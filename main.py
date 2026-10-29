# -*- coding: utf-8 -*-
"""LM (Lenguage Monitoring) para Android - interfaz Kivy.
La lógica está en lm_core.py (la misma de la versión de escritorio)."""
import os
import re
import shutil
import time
from datetime import date, timedelta

from kivy.app import App
from kivy.clock import Clock
from kivy.core.text import Label as CoreLabel
from kivy.core.window import Window
from kivy.graphics import Color, Ellipse, Line, Rectangle
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.checkbox import CheckBox
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.progressbar import ProgressBar
from kivy.uix.scrollview import ScrollView
from kivy.uix.spinner import Spinner, SpinnerOption
from kivy.uix.switch import Switch
from kivy.uix.tabbedpanel import TabbedPanel, TabbedPanelItem
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget
from kivy.utils import get_color_from_hex as hexc, platform

import lm_core as core

# ---------------------------------------------------------------- tema y tamaño de letra
_C = dict(BG="#f4f6fb", CARD="#ffffff", ACC="#4f6df5", OK="#1f9d55", MAL="#d64545", REG="#e08a00",
          TXT="#1f2937", SUB="#6b7280", INPUT="#ffffff", SEC="#e3e7f3", BORDER="#cfd5e6")
_O = dict(BG="#0e131b", CARD="#1a2230", ACC="#5b7cfa", OK="#2fa866", MAL="#e0544f", REG="#f2a93b",
          TXT="#e8ecf4", SUB="#9aa5b8", INPUT="#111823", SEC="#2a3547", BORDER="#2c3748")
CLARO = {k: hexc(v) for k, v in _C.items()}
OSCURO = {k: hexc(v) for k, v in _O.items()}
T = dict(CLARO)
ESC = 1.0
BLANCO = (1, 1, 1, 1)


def fs(n):
    """Tamaño de letra en píxeles según el ajuste elegido."""
    return sp(n * ESC)


# ---------------------------------------------------------------- piezas de interfaz
def lbl(texto="", size=16, color=None, bold=False, halign="left", auto=True, **kw):
    l = Label(text=texto, font_size=fs(size), bold=bold, color=color or T["TXT"],
              halign=halign, valign="middle", **kw)
    if auto:                                   # se ajusta al ancho y crece en alto
        l.size_hint_y = None
        l.bind(width=lambda i, w: setattr(i, "text_size", (w, None)))
        l.bind(texture_size=lambda i, ts: setattr(i, "height", ts[1] + dp(8)))
    else:
        l.bind(size=lambda i, s: setattr(i, "text_size", s))
    return l


def btn(texto, cb, primario=True, size=16, color=None, **kw):
    b = Button(text=texto, font_size=fs(size), background_normal="",
               background_color=T["ACC"] if primario else T["SEC"],
               color=color or (BLANCO if primario else T["TXT"]),
               size_hint_y=None, height=dp(50), **kw)
    b.bind(on_release=lambda *_: cb())
    return b


def pila(**kw):
    g = GridLayout(cols=1, size_hint_y=None, spacing=dp(10), padding=[dp(14), dp(10)], **kw)
    g.bind(minimum_height=g.setter("height"))
    return g


def fila(h=50, **kw):
    return BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(h), spacing=dp(8), **kw)


def scroll(contenido):
    sv = ScrollView(do_scroll_x=False, bar_width=dp(3))
    sv.add_widget(contenido)
    return sv


def entrada(texto="", **kw):
    return TextInput(text=texto, multiline=False, font_size=fs(18), size_hint_y=None,
                     height=dp(54), background_color=T["INPUT"], foreground_color=T["TXT"],
                     cursor_color=T["ACC"], padding=[dp(10), dp(14)], write_tab=False, **kw)


class Opcion(SpinnerOption):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.background_normal = ""
        self.background_color = T["SEC"]
        self.color = T["TXT"]
        self.font_size = fs(15)
        self.size_hint_y = None
        self.height = dp(46)


def selector(titulo, valores, actual, cb):
    f = fila(50)
    f.add_widget(lbl(titulo, 15, bold=True, auto=False, size_hint_x=0.34))
    s = Spinner(text=actual, values=valores, font_size=fs(15), background_normal="",
                background_color=T["SEC"], color=T["TXT"], option_cls=Opcion)
    s.bind(text=lambda i, v: cb(v))
    f.add_widget(s)
    return f


class Celda(Label):
    """Casilla con color de fondo (calendario de la racha)."""

    def __init__(self, fondo, **kw):
        super().__init__(**kw)
        with self.canvas.before:
            Color(*fondo)
            self._r = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._ajusta, size=self._ajusta)

    def _ajusta(self, *_):
        self._r.pos = self.pos
        self._r.size = self.size


class Grafica(Widget):
    """Evolución del % de aciertos por día."""

    def __init__(self, **kw):
        super().__init__(**kw)
        self.puntos = []
        self.bind(pos=self.dibujar, size=self.dibujar)

    def texto(self, txt, x, y, color, tam=10, derecha=False):
        l = CoreLabel(text=txt, font_size=fs(tam))
        l.refresh()
        t = l.texture
        if t is None:
            return
        w, h = t.size
        Color(*color)
        Rectangle(texture=t, pos=(x - w if derecha else x - w / 2, y - h / 2), size=(w, h))

    def dibujar(self, *_):
        self.canvas.clear()
        if self.width < dp(80) or self.height < dp(80):
            return
        with self.canvas:
            x0, x1 = self.x + dp(46), self.right - dp(14)
            y0, y1 = self.y + dp(34), self.top - dp(16)
            pts = self.puntos
            if not pts:
                self.texto("Aún no hay datos para la gráfica.", self.center_x, self.center_y, T["SUB"], 13)
                return
            for v in (0, 25, 50, 75, 100):
                y = y0 + (y1 - y0) * v / 100
                Color(*T["BORDER"])
                Line(points=[x0, y, x1, y], width=1)
                self.texto(f"{v} %", x0 - dp(6), y, T["SUB"], 10, derecha=True)
            d0 = pts[0][0].toordinal()
            span = pts[-1][0].toordinal() - d0

            def X(d):
                return (x0 + x1) / 2 if span == 0 else x0 + (x1 - x0) * (d.toordinal() - d0) / span

            def Y(p):
                return y0 + (y1 - y0) * max(0, min(p, 100)) / 100

            xy = [(X(d), Y(p)) for d, p, _n in pts]
            Color(*T["ACC"])
            if len(xy) > 1:
                Line(points=[c for par in xy for c in par], width=dp(1.5))
            for (x, y), (d, p, _n) in zip(xy, pts):
                Color(*T["ACC"])
                Ellipse(pos=(x - dp(4), y - dp(4)), size=(dp(8), dp(8)))
                if len(pts) <= 12:
                    self.texto(f"{p:.0f}", x, y + dp(12), T["TXT"], 10)
            k = min(len(pts), 5)
            for i in sorted({round(j * (len(pts) - 1) / max(1, k - 1)) for j in range(k)}):
                self.texto(pts[i][0].strftime("%d/%m"), xy[i][0], y0 - dp(14), T["SUB"], 10)


# ---------------------------------------------------------------- aplicación
class LMApp(App):
    title = "LM Palabras"

    def build(self):
        if platform not in ("android", "ios"):
            Window.size = (420, 780)                      # para probar en el ordenador
        Window.softinput_mode = "resize"                  # el teclado no tapa los botones
        core.configurar(self.user_data_dir)
        self.dir_listas = os.path.join(self.user_data_dir, "listas")
        os.makedirs(self.dir_listas, exist_ok=True)
        aj = core.cargar_ajustes()
        self.oscuro, self.tam = aj["oscuro"], aj["tamano"]
        self.timer_on, self.objetivo = aj["timer"], aj["objetivo"]
        self.tema()
        self.dir, self.orden, self.modo = core.DIRECCIONES[0], core.ORDENES[0], core.MODOS[0]
        ses = core.cargar_sesion()
        self.enc = ses.get("enc", True)
        self.listas = core.Listas()
        for r in ses.get("rutas", []):
            if os.path.exists(r):
                self.listas.agregar(r, encabezado=self.enc)
        self.n_txt = str(len(self.listas.base)) if self.listas.base else ""
        self.q, self.pop, self._ev, self.actual = None, None, None, "menu"
        self.e1 = self.e2 = self.btn_pista = None
        Window.bind(on_keyboard=self._tecla)
        self.raiz = BoxLayout(orientation="vertical")
        self.pedir_permisos()
        self.menu()
        return self.raiz

    def on_pause(self):
        return True

    # ---------- utilidades
    def tema(self):
        global ESC
        T.clear()
        T.update(OSCURO if self.oscuro else CLARO)
        ESC = core.TAMANOS[self.tam]
        Window.clearcolor = T["BG"]

    def guardar_aj(self):
        core.guardar_ajustes({"oscuro": self.oscuro, "tamano": self.tam,
                              "timer": self.timer_on, "objetivo": self.objetivo})

    def guardar_sesion(self):
        core.guardar_sesion([l["ruta"] for l in self.listas.items], self.enc)

    def pantalla(self, widget, nombre):
        self._parar_timer()
        self.actual = nombre
        self.raiz.clear_widgets()
        self.raiz.add_widget(widget)

    def _parar_timer(self):
        if self._ev:
            self._ev.cancel()
            self._ev = None

    def pedir_permisos(self):
        if platform == "android":
            try:
                from android.permissions import Permission, request_permissions
                request_permissions([Permission.READ_EXTERNAL_STORAGE,
                                     Permission.WRITE_EXTERNAL_STORAGE])
            except Exception:
                pass

    def abrir_popup(self, titulo, contenido, alto=0.45):
        p = Popup(title=titulo, content=contenido, size_hint=(0.92, alto), auto_dismiss=False)
        p.bind(on_dismiss=lambda *_: setattr(self, "pop", None))
        self.pop = p
        p.open()
        return p

    def _texto(self, texto):
        c = pila()
        c.add_widget(lbl(texto, 15, BLANCO))
        return c

    def aviso(self, titulo, texto):
        c = BoxLayout(orientation="vertical", spacing=dp(10), padding=dp(8))
        c.add_widget(scroll(self._texto(texto)))
        p = self.abrir_popup(titulo, c, 0.45)
        c.add_widget(btn("Aceptar", p.dismiss))

    def confirmar(self, titulo, texto, si, alto=0.4):
        c = BoxLayout(orientation="vertical", spacing=dp(10), padding=dp(8))
        c.add_widget(scroll(self._texto(texto)))
        f = fila(50)
        p = self.abrir_popup(titulo, c, alto)
        f.add_widget(btn("No", p.dismiss, False))
        f.add_widget(btn("Sí", lambda: (p.dismiss(), si())))
        c.add_widget(f)

    def enfocar(self, w):
        Clock.schedule_once(lambda dt: setattr(w, "focus", True), 0.15)

    def _tecla(self, window, key, *args):
        if key != 27:                                     # botón "atrás"
            return False
        if self.pop is not None:
            self.pop.dismiss()
            return True
        if self.actual == "menu":
            return False                                  # sale de la app
        if self.actual == "quiz":
            self.terminar()
        else:
            self.menu()
        return True

    # ---------- menú principal
    def menu(self):
        L = self.listas
        c = pila()
        top = fila(52)
        top.add_widget(lbl("LM", 28, T["ACC"], True, auto=False))
        top.add_widget(btn("Perfil", self.perfil, False, 14, size_hint_x=None, width=dp(84)))
        top.add_widget(btn("Ajustes", self.ajustes, False, 14, size_hint_x=None, width=dp(94)))
        c.add_widget(top)
        c.add_widget(lbl("Importa tus listas de palabras (CSV, TXT o Excel) y elige cómo practicarlas. "
                         "Puedes añadir varias: se combinan en una sola sesión.", 13, T["SUB"]))
        if not L.items:
            c.add_widget(lbl("Ninguna lista cargada", 15, T["SUB"]))
        for i, l in enumerate(L.items):
            f = fila(58)
            tipo = "con artículos" if l["art"] else "sin artículos"
            f.add_widget(lbl(f"{l['nombre']}\n{len(l['filas'])} palabras ({tipo})", 13, auto=False))
            f.add_widget(btn("Editar", lambda i=i: self.editor(i), False, 13,
                             size_hint_x=None, width=dp(74)))
            f.add_widget(btn("Quitar", lambda i=i: self.pedir_quitar(i), False, 13, T["MAL"],
                             size_hint_x=None, width=dp(74)))
            c.add_widget(f)
        if len(L.items) > 1:
            c.add_widget(lbl(f"Sesión combinada: {len(L.base)} palabras", 14, T["ACC"], True))
        c.add_widget(btn("Importar / añadir listas", self.importar, False))

        fe = fila(46)
        cb = CheckBox(active=self.enc, size_hint_x=None, width=dp(44), color=T["ACC"])
        cb.bind(active=self._enc)
        fe.add_widget(cb)
        fe.add_widget(lbl("La primera fila del archivo es un encabezado", 13, auto=False))
        c.add_widget(fe)

        c.add_widget(selector("Dirección", core.DIRECCIONES, self.dir, lambda v: setattr(self, "dir", v)))
        c.add_widget(selector("Orden", core.ORDENES, self.orden, lambda v: setattr(self, "orden", v)))
        c.add_widget(selector("Modo", core.MODOS, self.modo, lambda v: setattr(self, "modo", v)))
        fn = fila(54)
        fn.add_widget(lbl("Nº de palabras", 15, bold=True, auto=False, size_hint_x=0.34))
        n_in = entrada(self.n_txt, input_filter="int")
        n_in.bind(text=lambda i, v: setattr(self, "n_txt", v))
        fn.add_widget(n_in)
        fn.add_widget(lbl(f"(máx. {len(L.base)})", 12, T["SUB"], auto=False, size_hint_x=0.3))
        c.add_widget(fn)

        c.add_widget(btn("Empezar", self.empezar, True, 18))
        c.add_widget(btn("Escribir mi lista", self.lista_propia, False))
        self.pantalla(scroll(c), "menu")

    def _enc(self, inst, val):
        self.enc = val
        errores = self.listas.recargar(val)
        self.guardar_sesion()
        self.menu()
        if errores:
            self.aviso("Algunas listas no se cargaron", "\n\n".join(errores))

    def leer_n(self, total):
        try:
            return max(1, min(int(self.n_txt), total))
        except ValueError:
            return total

    def pedir_quitar(self, i):
        nombre = self.listas.items[i]["nombre"]
        self.confirmar("Quitar lista", f"¿Quitar «{nombre}» de la app?\n"
                       "Se borra la copia que guarda la app; tu archivo original no cambia.",
                       lambda: self.quitar(i))

    def quitar(self, i):
        ruta = self.listas.items[i]["ruta"]
        self.listas.quitar(i)
        try:
            os.remove(ruta)
        except OSError:
            pass
        self.n_txt = str(len(self.listas.base)) if self.listas.base else ""
        self.guardar_sesion()
        self.menu()

    # ---------- importar listas (CSV, TXT o Excel)
    def importar(self):
        if platform == "android":
            try:
                from androidstorage4kivy import Chooser
                self._chooser = Chooser(self._al_elegir)
                try:
                    self._chooser.choose_content("*/*", multiple=True)
                except TypeError:
                    self._chooser.choose_content("*/*")
                return
            except Exception:
                pass
        self.explorador()

    def _al_elegir(self, uris):
        if not uris:
            return
        rutas = []
        try:
            from androidstorage4kivy import SharedStorage
            ss = SharedStorage()
            for u in uris:
                try:
                    p = ss.copy_from_shared(u)
                except Exception:
                    p = None
                if p:
                    rutas.append(p)
        except Exception:
            pass
        Clock.schedule_once(lambda dt: self.agregar_archivos(rutas), 0)

    def explorador(self):
        """Selector de archivos propio (ordenador, o Android si falla el del sistema)."""
        from kivy.uix.filechooser import FileChooserListView
        inicio = os.path.expanduser("~")
        if platform == "android" and os.path.isdir("/storage/emulated/0"):
            inicio = "/storage/emulated/0"
        fc = FileChooserListView(path=inicio, multiselect=True, filters=["*.csv", "*.txt", "*.xlsx"])
        c = BoxLayout(orientation="vertical", spacing=dp(8))
        c.add_widget(fc)
        p = self.abrir_popup("Elige tus listas", c, 0.92)
        f = fila(50)
        f.add_widget(btn("Cancelar", p.dismiss, False))
        f.add_widget(btn("Añadir", lambda: (p.dismiss(), self.agregar_archivos(list(fc.selection)))))
        c.add_widget(f)

    def a_biblioteca(self, ruta):
        """Copia la lista a la carpeta de la app (así no hay que volver a importarla)."""
        nombre = os.path.basename(ruta)
        base, ext = os.path.splitext(nombre)
        if ext.lower() not in (".csv", ".txt", ".xlsx", ".xls"):
            with open(ruta, "rb") as f:
                ext = ".xlsx" if f.read(2) == b"PK" else ".csv"
            nombre = (base or "lista") + ext
        destino = os.path.join(self.dir_listas, nombre)
        if os.path.abspath(ruta) != os.path.abspath(destino):
            shutil.copy2(ruta, destino)
        return destino

    def agregar_archivos(self, rutas):
        errores = []
        for r in rutas:
            try:
                destino = self.a_biblioteca(r)
            except Exception as e:
                errores.append(f"{os.path.basename(r)}: {e}")
                continue
            err = self.listas.agregar(destino, encabezado=self.enc)
            if err:
                errores.append(err)
        self.n_txt = str(len(self.listas.base)) if self.listas.base else ""
        self.guardar_sesion()
        self.menu()
        if errores:
            self.aviso("Algunas listas no se cargaron", "\n\n".join(errores))

    # ---------- editar una lista
    def editor(self, i):
        l = self.listas.items[i]
        c = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(8))
        c.add_widget(lbl(f"Modificando: {l['nombre']}", 18, T["ACC"], True))
        formato = ("art_esp, español, art_idioma, idioma  (el artículo puede ir vacío)" if l["art"]
                   else "español, idioma")
        c.add_widget(lbl(f"Una palabra por línea: {formato}. Si una palabra lleva comas, ponla entre "
                         "comillas. Se edita la copia de la app; tu archivo original no cambia.", 12, T["SUB"]))
        ti = TextInput(text=core.filas_a_texto(l["filas"]), multiline=True, font_size=fs(16),
                       background_color=T["INPUT"], foreground_color=T["TXT"], cursor_color=T["ACC"])

        def guardar():
            nuevas = core.texto_a_filas(ti.text, l["art"])
            if not nuevas:
                return self.aviso("Lista vacía", "Debe haber al menos una pareja de palabras válida.")
            if not core.guardar_lista_en_archivo(l["ruta"], nuevas, self.enc, l["art"]):
                return self.aviso("Error", "No se pudo guardar la lista.")
            self.listas.agregar(l["ruta"], l["nombre"], self.enc)
            self.n_txt = str(len(self.listas.base))
            self.menu()

        barra = fila(52)
        barra.add_widget(btn("Cancelar", self.menu, False))
        barra.add_widget(btn("Guardar cambios", guardar))
        c.add_widget(barra)
        c.add_widget(ti)
        self.pantalla(c, "editor")

    # ---------- escribir mi propia lista
    def lista_propia(self):
        c = pila()
        c.add_widget(lbl("Crea tu lista de palabras", 22, T["ACC"], True))
        c.add_widget(lbl("Una pareja por línea, separada por coma: palabra 1, palabra a escribir", 13, T["SUB"]))
        ti = TextInput(text="casa, house\nperro, dog", multiline=True, font_size=fs(17),
                       size_hint_y=None, height=dp(220), background_color=T["INPUT"],
                       foreground_color=T["TXT"], cursor_color=T["ACC"])
        c.add_widget(ti)
        c.add_widget(selector("Modo", core.MODOS, self.modo, lambda v: setattr(self, "modo", v)))
        fn = fila(54)
        fn.add_widget(lbl("Nº de palabras", 15, bold=True, auto=False, size_hint_x=0.4))
        n_in = entrada("", input_filter="int", hint_text="vacío = todas")
        fn.add_widget(n_in)
        c.add_widget(fn)
        fg = fila(54)
        fg.add_widget(lbl("Guardar como", 15, bold=True, auto=False, size_hint_x=0.4))
        nom_in = entrada("", hint_text="nombre (opcional)")
        fg.add_widget(nom_in)
        c.add_widget(fg)

        def seguir():
            base = core.parse_custom(ti.text)
            if not base:
                return self.aviso("Lista vacía", "Escribe al menos una pareja.")
            nombre = "Mi propia lista"
            nom = re.sub(r"[^\w\- ]", "_", nom_in.text.strip())
            extra = ""
            if nom:
                ruta = os.path.join(self.dir_listas, nom + ".csv")
                if core.guardar_lista_en_archivo(ruta, base, self.enc, False):
                    nombre = os.path.basename(ruta)
                    self.listas.agregar(ruta, encabezado=self.enc)
                    self.guardar_sesion()
                    self.n_txt = str(len(self.listas.base))
                    if self.exportar_publico(ruta):
                        extra = " (copia también en Documentos)"
            filas = core.orientar(base, False, core.DIRECCIONES.index(self.dir))
            try:
                n = max(1, min(int(n_in.text), len(filas)))
            except ValueError:
                n = len(filas)
            f, o, s = core.preparar(filas, False, self.orden, n, filas_origen=base,
                                    fuentes=[nombre] * len(filas))
            self.iniciar(f, False, self.modo, filas, nombre, False, o, s)

        fb = fila(54)
        fb.add_widget(btn("Volver", self.menu, False))
        fb.add_widget(btn("Continuar", seguir))
        c.add_widget(fb)
        self.pantalla(scroll(c), "lista_propia")

    def exportar_publico(self, ruta):
        """En Android, copia el archivo a la carpeta Documentos del móvil (si se puede)."""
        if platform != "android":
            return None
        try:
            from androidstorage4kivy import SharedStorage
            return SharedStorage().copy_to_shared(ruta)
        except Exception:
            return None

    # ---------- ajustes
    def ajustes(self):
        c = pila()
        c.add_widget(lbl("Ajustes", 26, T["ACC"], True))
        f = fila(52)
        f.add_widget(lbl("Tema oscuro", 17, auto=False))
        sw = Switch(active=self.oscuro, size_hint_x=None, width=dp(100))
        sw.bind(active=self._set_oscuro)
        f.add_widget(sw)
        c.add_widget(f)
        f = fila(52)
        f.add_widget(lbl("Mostrar temporizador", 17, auto=False))
        sw = Switch(active=self.timer_on, size_hint_x=None, width=dp(100))
        sw.bind(active=self._set_timer)
        f.add_widget(sw)
        c.add_widget(f)
        c.add_widget(lbl("El temporizador aparece arriba a la derecha durante la lista y se detiene "
                         "al terminar. Al final se muestra tu tiempo.", 12, T["SUB"]))
        c.add_widget(lbl("Tamaño de letra", 17, T["TXT"], True))
        f = fila(48)
        for t in core.TAMANOS:
            f.add_widget(btn(t, lambda t=t: self._set_tam(t), t == self.tam, 12))
        c.add_widget(f)
        c.add_widget(lbl("M es el tamaño estándar.", 12, T["SUB"]))
        c.add_widget(btn("Volver", self.menu))
        self.pantalla(scroll(c), "ajustes")

    def _set_oscuro(self, inst, val):
        self.oscuro = val
        self.guardar_aj()
        self.tema()
        self.ajustes()

    def _set_tam(self, t):
        self.tam = t
        self.guardar_aj()
        self.tema()
        self.ajustes()

    def _set_timer(self, inst, val):
        self.timer_on = val
        self.guardar_aj()

    # ---------- empezar y cuestionario
    def empezar(self):
        L = self.listas
        if not L.base:
            return self.aviso("Falta la lista", "Importa primero al menos un archivo de palabras.")
        filas = core.orientar(L.base, L.art, core.DIRECCIONES.index(self.dir))
        f, o, s = core.preparar(filas, L.art, self.orden, self.leer_n(len(filas)),
                                filas_origen=L.base, fuentes=L.base_src)
        self.iniciar(f, L.art, self.modo, filas, L.nombre_sesion(), False, o, s)

    def iniciar(self, filas, art, modo, pool, nombre, repaso, orig, fuentes):
        q = core.Quiz(filas, art, modo, pool, nombre, repaso, orig, fuentes)
        if not q.valido():
            return self.aviso("Pocas palabras", "La opción múltiple necesita al menos 2 respuestas distintas.")
        self.q = q
        self.vista_quiz()

    def vista_quiz(self):
        q = self.q
        multiple = q.modo == core.MODOS[1]
        self.e1 = self.e2 = self.btn_pista = None
        raiz = BoxLayout(orientation="vertical", padding=[dp(12), dp(8)], spacing=dp(6))
        top = fila(28)
        self.l_prog = lbl("", 13, T["SUB"], auto=False)
        top.add_widget(self.l_prog)
        self.l_tiempo = lbl("", 13, T["SUB"], auto=False, halign="right", size_hint_x=None, width=dp(96))
        if self.timer_on:
            top.add_widget(self.l_tiempo)
        raiz.add_widget(top)
        self.l_marc = lbl("", 12, T["TXT"], True, auto=False, size_hint_y=None, height=dp(24))
        raiz.add_widget(self.l_marc)
        self.barra = ProgressBar(max=max(1, len(q.filas)), value=0, size_hint_y=None, height=dp(8))
        raiz.add_widget(self.barra)

        cuerpo = pila()
        instr = {core.MODOS[0]: "Traduce:", core.MODOS[1]: "Elige la traducción correcta:",
                 core.MODOS[2]: "Piensa la traducción:"}[q.modo]
        cuerpo.add_widget(lbl(instr, 14, T["SUB"], halign="center"))
        self.l_origen = lbl("", 12, T["SUB"], halign="center")
        self.l_preg = lbl("", 30, T["TXT"], True, halign="center")
        self.zona = GridLayout(cols=1, size_hint_y=None, spacing=dp(8))
        self.zona.bind(minimum_height=self.zona.setter("height"))
        self.l_pista = lbl("", 24, T["ACC"], True, halign="center")
        self.l_fb = lbl("", 16, T["TXT"], True, halign="center")
        for w in (self.l_origen, self.l_preg, self.zona, self.l_pista, self.l_fb):
            cuerpo.add_widget(w)
        raiz.add_widget(scroll(cuerpo))

        pie = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(6))
        self.fila_btn = fila(52)
        pie.add_widget(self.fila_btn)
        pie.height = dp(52)
        if not multiple:                                  # en opción múltiple no hay pistas
            self.btn_pista = btn("Pista", self.pista, False)
            pie.add_widget(self.btn_pista)
            pie.height = dp(52) + dp(56)
        raiz.add_widget(pie)

        self.pantalla(raiz, "quiz")
        self.t0 = time.perf_counter()
        if self.timer_on:
            self._ev = Clock.schedule_interval(self._tick, 0.03)
        self.pregunta()

    def _tick(self, dt):
        self.l_tiempo.text = core.fmt_tiempo(time.perf_counter() - self.t0)

    def botones(self, *items):
        self.fila_btn.clear_widgets()
        self.fila_btn.add_widget(btn("Terminar", self.terminar, False, 15))
        for texto, cb, prim, *col in items:
            self.fila_btn.add_widget(btn(texto, cb, prim, 15, col[0] if col else None))

    def fb(self, texto, color):
        self.l_fb.text = texto
        self.l_fb.color = color

    def marcador(self):
        q = self.q
        t = f"Aciertos {q.ok}   Fallos {q.mal}"
        if q.art:
            t += f"   Parciales {q.parcial}"
        if q.modo != core.MODOS[1]:
            t += f"   Con pistas {q.pistas_n}"
        self.l_marc.text = t

    def pregunta(self):
        q = self.q
        q.nuevo()
        self.l_prog.text = f"Palabra {q.i + 1} de {len(q.filas)}"
        self.marcador()
        self.barra.value = q.i
        self.l_origen.text = q.origen()                  # lista de la que viene la palabra
        self.l_preg.text = q.pregunta()
        self.fb("", T["TXT"])
        self.l_pista.text = ""
        if self.btn_pista:
            self.btn_pista.disabled = False
        self.zona.clear_widgets()
        self.e1 = self.e2 = None
        if q.modo == core.MODOS[0]:
            if q.con_art():                               # con artículo: dos casillas
                self.e1 = entrada(hint_text="Artículo")
                self.e1.bind(on_text_validate=lambda *_: self.enfocar(self.e2))
                self.zona.add_widget(self.e1)
            self.e2 = entrada(hint_text="Palabra")        # sin artículo: solo la palabra
            self.e2.bind(on_text_validate=lambda *_: self.accion())
            self.zona.add_widget(self.e2)
            self.botones(("Comprobar", self.accion, True))
            self.enfocar(self.e1 or self.e2)
        elif q.modo == core.MODOS[1]:
            self.opciones = []
            for k, t in enumerate(q.opciones(), 1):
                b = Button(text=f"{k}.  {t}", font_size=fs(17), background_normal="",
                           background_color=T["SEC"], color=T["TXT"], size_hint_y=None,
                           height=dp(56), halign="left", valign="middle")
                b.bind(size=lambda i, s: setattr(i, "text_size", (s[0] - dp(20), s[1])))
                b.bind(on_release=lambda i, t=t: self.elegir(t))
                self.zona.add_widget(b)
                self.opciones.append((t, b))
            self.botones()
        else:
            self.l_resp = lbl("", 26, T["ACC"], True, halign="center")
            self.zona.add_widget(self.l_resp)
            self.botones(("Mostrar respuesta", self.accion, True))

    def accion(self):
        q = self.q
        if q.modo == core.MODOS[0]:
            self.siguiente() if q.hecho else self.comprobar()
        elif q.modo == core.MODOS[2] and not q.revelada:
            self.revelar()

    def fin_pregunta(self):
        q = self.q
        if self.btn_pista:
            self.btn_pista.disabled = True
        for e in (self.e1, self.e2):
            if e is not None:
                e.disabled = True
        ultima = q.i + 1 >= len(q.filas)
        self.botones(("Ver resultado" if ultima else "Siguiente", self.siguiente, True))

    def siguiente(self):
        if self.q.avanzar():
            self.pregunta()
        else:
            self.resultado()

    def pista(self):
        q = self.q
        r = q.pista()
        if r is None:
            return
        texto, quedan = r
        self.l_pista.text = texto
        if quedan == 0:
            self.btn_pista.disabled = True
        if q.exceso():
            self.fb("Con más de la mitad de las letras descubiertas,\nesta palabra ya no puntuará.", T["REG"])

    # --- escribir
    def comprobar(self):
        q = self.q
        r = q.comprobar(self.e1.text if self.e1 else "", self.e2.text)
        tipo = r["tipo"]
        if tipo == "casi":
            extra = "\nRevisa también el artículo." if r["revisar_art"] else ""
            self.fb("Casi correcto. Te equivocas en un solo carácter de la palabra.\n"
                    "Puedes rectificar y volver a comprobar." + extra, T["REG"])
            self.botones(("Comprobar de nuevo", self.accion, True))
            self.enfocar(self.e2)
            return
        c = r["correcta"]
        nota = "\nHas usado pista: la repasarás al final." if r["pista"] else ""
        msg = {"ok": ("¡Correcto!" + nota, T["OK"]),
               "ok_rect": ("¡Correcto tras rectificar!" + nota, T["OK"]),
               "exceso_ok": ("Correcto, pero con demasiadas pistas:\nno puntúa.", T["REG"]),
               "mal_exceso": (f"Con demasiadas pistas: no puntúa.\nLa respuesta era: {c}", T["REG"]),
               "parcial_art": (f"Regular, solo has acertado el artículo.\nLa respuesta era: {c}" + nota, T["REG"]),
               "parcial_pal": (f"Regular, solo has acertado la palabra.\nLa respuesta era: {c}" + nota, T["REG"]),
               "mal": (f"Incorrecto.\nLa respuesta era: {c}" + nota, T["MAL"])}[tipo]
        self.fb(*msg)
        self.marcador()
        self.fin_pregunta()

    # --- opción múltiple
    def elegir(self, elegida):
        q = self.q
        if q.hecho:
            return
        ok, c = q.elegir(elegida)
        self.fb("¡Correcto!" if ok else f"Incorrecto.\nLa respuesta era: {c}", T["OK"] if ok else T["MAL"])
        for t, b in self.opciones:
            if t == c:
                b.background_color, b.color = T["OK"], BLANCO
            elif t == elegida:
                b.background_color, b.color = T["MAL"], BLANCO
        self.marcador()
        self.fin_pregunta()

    # --- flashcards
    def revelar(self):
        q = self.q
        c, exceso = q.mostrar()
        self.l_resp.text = c
        self.fb("Con demasiadas pistas: esta palabra no puntuará." if exceso else "¿La sabías?",
                T["REG"] if exceso else T["SUB"])
        if self.btn_pista:
            self.btn_pista.disabled = True
        self.botones(("Incorrecto", lambda: self.juzgar(False), False, T["MAL"]),
                     ("Correcto", lambda: self.juzgar(True), True))

    def juzgar(self, acierto):
        self.q.juzgar(acierto)
        self.marcador()
        self.siguiente()

    def terminar(self):
        t = time.perf_counter() - self.t0                # no cuenta lo que tardes en confirmar
        self.confirmar("Finalizar lista", "¿Seguro que quieres finalizar la lista?",
                       lambda: self.resultado(t))

    # ---------- resultado
    def resultado(self, t=None):
        q = self.q
        if t is None:
            t = time.perf_counter() - self.t0
        puntuadas, pct = q.finalizar()
        incompleta = q.resp < len(q.filas)
        c = pila()
        c.add_widget(lbl("Has finalizado la lista" if incompleta else "Resultado", 24, T["TXT"], True,
                         halign="center"))
        if incompleta:
            c.add_widget(lbl(f"Has contestado {q.resp} de {len(q.filas)} palabras", 14, T["SUB"],
                             halign="center"))
        color = T["OK"] if pct >= 70 else T["REG"] if pct >= 50 else T["MAL"]
        c.add_widget(lbl(f"{pct:.0f} %" if puntuadas else "-", 54, color, True, halign="center"))
        c.add_widget(lbl("de aciertos sobre las palabras contestadas" if incompleta else "de aciertos",
                         13, T["SUB"], halign="center"))
        if self.timer_on:
            c.add_widget(lbl(f"Tu tiempo ha sido de: {core.fmt_tiempo(t)}", 16, T["TXT"], True,
                             halign="center"))
        c.add_widget(lbl(f"Correctas {q.ok}   Parciales {q.parcial}   Incorrectas {q.mal}", 15, T["TXT"],
                         halign="center"))
        if q.pistas_n:
            c.add_widget(lbl(f"{q.pistas_n} con pistas (no puntúan)", 14, T["REG"], halign="center"))
        if q.falladas:
            fall, orig, src = q.falladas[:], q.falladas_orig[:], q.falladas_fuente[:]
            art, modo, pool, nombre = q.art, q.modo, q.pool, q.nombre
            c.add_widget(btn(f"Repasar falladas ({len(fall)})",
                             lambda: self.iniciar(fall, art, modo, pool, nombre, True, orig, src)))
        c.add_widget(btn("Menú principal", self.menu, not q.falladas))
        self.pantalla(scroll(c), "resultado")

    # ---------- perfil: historial, estadísticas, difíciles, gráfica y racha
    def perfil(self, abrir=0):
        tp = TabbedPanel(do_default_tab=False, tab_width=dp(108), tab_height=dp(40))
        items = []
        for nombre, fn in (("Historial", self.t_hist), ("Estadísticas", self.t_est),
                           ("Difíciles", self.t_dif), ("Gráfica", self.t_graf), ("Racha", self.t_racha)):
            it = TabbedPanelItem(text=nombre, font_size=fs(14))
            it.add_widget(fn())
            tp.add_widget(it)
            items.append(it)
        Clock.schedule_once(lambda dt: tp.switch_to(items[abrir]), 0)
        raiz = BoxLayout(orientation="vertical", spacing=dp(6), padding=dp(6))
        raiz.add_widget(tp)
        f = fila(52)
        f.add_widget(btn("Volver", self.menu, False))
        f.add_widget(btn("Borrar historial", self.pedir_borrar, False, 15, T["MAL"]))
        raiz.add_widget(f)
        self.pantalla(raiz, "perfil")

    def pedir_borrar(self):
        self.confirmar("Borrar historial", "¿Seguro que quieres borrar el historial, las estadísticas, "
                       "la gráfica, la racha y el progreso por palabra?", self._borrar, 0.45)

    def _borrar(self):
        core.guardar_hist([])
        core.guardar_progreso({})
        self.perfil()

    def con_filtro(self, titulo, valores, construir, por_defecto=None):
        cont = BoxLayout(orientation="vertical", spacing=dp(6), padding=dp(6))
        cuerpo = BoxLayout()

        def pintar(v):
            cuerpo.clear_widgets()
            cuerpo.add_widget(construir(v))

        cont.add_widget(selector(titulo, valores, por_defecto or valores[0], pintar))
        cont.add_widget(cuerpo)
        pintar(por_defecto or valores[0])
        return cont

    def t_hist(self):
        h = core.cargar_hist()
        c = pila()
        if not h:
            c.add_widget(lbl("Aún no hay listas completadas.", 15, T["SUB"]))
        for e in reversed(h):
            rep = " (repaso)" if e.get("repaso") else ""
            c.add_widget(lbl(f"{core.fecha_bonita(e['fecha'])}\n{e['archivo']}{rep}   -   {e['pct']:.1f} %", 14))
        return scroll(c)

    def t_est(self):
        h = core.cargar_hist()

        def construir(v):
            modo = None if v == core.TODOS else v
            c = pila()
            ap = core.palabras_aprendidas(h, modo)
            c.add_widget(lbl(f"Has aprendido {ap} palabra{'' if ap == 1 else 's'}", 17, T["ACC"], True))
            filas = core.estadisticas(h, modo)
            if not filas:
                c.add_widget(lbl("No hay listas completadas en este modo.", 14, T["SUB"]))
            for a, md, n, k, m in filas:
                c.add_widget(lbl(f"{a}\n{md}  ·  {n or '-'} palabras  ·  {k} lista{'' if k == 1 else 's'}  ·  "
                                 f"media {m:.1f} %", 13))
            return scroll(c)

        return self.con_filtro("Modo", [core.TODOS] + core.MODOS, construir)

    def t_dif(self):
        def construir(v):
            n = None if v == "Todas" else int(v)
            dif = core.palabras_dificiles(core.cargar_progreso(), n)
            c = pila()
            if not dif:
                c.add_widget(lbl("Todavía no has fallado ninguna palabra.", 15, T["SUB"]))

            def pal(r, k):
                art = r["arts"][k] if r["arts"] else ""
                return f"{art} {r['idio' if k else 'esp']}".strip()

            for r in dif:
                c.add_widget(lbl(f"{pal(r, 0)}  ->  {pal(r, 1)}\n{r['lista']}  ·  {r['fallos']} fallos de "
                                 f"{r['vistas']} ({r['tasa'] * 100:.0f} %)", 13))
            if dif:
                c.add_widget(btn("Guardar como lista nueva", lambda: self.guardar_dificiles(dif)))
            return scroll(c)

        return self.con_filtro("Mostrar", ["10", "20", "50", "Todas"], construir, "20")

    def guardar_dificiles(self, dif):
        con_art = any(r["arts"] for r in dif)
        datos, vistos = [], set()
        for r in dif:
            if (r["esp"], r["idio"]) in vistos:
                continue
            vistos.add((r["esp"], r["idio"]))
            a1, a2 = r["arts"] or ("", "")
            datos.append((a1, r["esp"], a2, r["idio"]) if con_art else (r["esp"], r["idio"]))
        ruta = os.path.join(self.dir_listas, "palabras_dificiles.csv")
        if not core.guardar_lista_en_archivo(ruta, datos, self.enc, con_art):
            return self.aviso("Error", "No se pudo guardar la lista.")
        err = self.listas.agregar(ruta, encabezado=self.enc)
        self.n_txt = str(len(self.listas.base))
        self.guardar_sesion()
        extra = "\nTambién se ha copiado a la carpeta Documentos del móvil." if self.exportar_publico(ruta) else ""
        self.aviso("Lista guardada", "Se ha guardado «palabras_dificiles.csv» y añadido a tus listas."
                   + extra + (f"\n\n{err}" if err else ""))

    def t_graf(self):
        h = core.cargar_hist()
        nombres = [core.TODAS] + sorted({e["archivo"] for e in h}, key=core.clave)
        est = {"lista": core.TODAS, "modo": core.TODOS}
        g = Grafica()

        def pintar():
            lista = None if est["lista"] == core.TODAS else est["lista"]
            modo = None if est["modo"] == core.TODOS else est["modo"]
            g.puntos = core.serie_diaria(h, lista, modo)
            g.dibujar()

        def cambia(clave_):
            def f(v):
                est[clave_] = v
                pintar()
            return f

        cont = BoxLayout(orientation="vertical", spacing=dp(6), padding=dp(6))
        cont.add_widget(selector("Lista", nombres, core.TODAS, cambia("lista")))
        cont.add_widget(selector("Modo", [core.TODOS] + core.MODOS, core.TODOS, cambia("modo")))
        cont.add_widget(g)
        cont.add_widget(lbl("Cada punto es la media de aciertos de ese día.", 12, T["SUB"], halign="center"))
        pintar()
        return cont

    def t_racha(self):
        h = core.cargar_hist()
        obj, hoy = self.objetivo, date.today()
        por_dia = core.palabras_por_dia(h)
        actual, mejor = core.calcular_rachas(por_dia, obj, hoy)
        hecho = por_dia.get(hoy, 0)
        c = pila()
        c.add_widget(lbl(f"Racha: {actual} día{'' if actual == 1 else 's'}", 26, T["ACC"], True, halign="center"))
        c.add_widget(lbl(f"Mejor racha: {mejor} día{'' if mejor == 1 else 's'}", 14, T["SUB"], halign="center"))
        f = fila(54)
        f.add_widget(lbl("Objetivo diario", 15, bold=True, auto=False, size_hint_x=0.4))
        obj_in = entrada(str(obj), input_filter="int")
        f.add_widget(obj_in)
        f.add_widget(btn("OK", lambda: self.set_objetivo(obj_in.text), True, 15, size_hint_x=None, width=dp(64)))
        c.add_widget(f)
        extra = "Objetivo cumplido" if hecho >= obj else f"te faltan {obj - hecho}"
        c.add_widget(lbl(f"Hoy: {hecho} / {obj} palabras  ({extra})", 15, T["TXT"], True, halign="center"))
        c.add_widget(ProgressBar(max=obj, value=min(hecho, obj), size_hint_y=None, height=dp(10)))

        cal = GridLayout(cols=7, size_hint_y=None, spacing=dp(4), height=dp(36) * 6 + dp(4) * 5)
        for letra in "LMXJVSD":
            cal.add_widget(lbl(letra, 12, T["SUB"], True, halign="center", auto=False,
                               size_hint_y=None, height=dp(36)))
        ini = hoy - timedelta(days=hoy.weekday() + 28)
        for i in range(35):
            d = ini + timedelta(days=i)
            n = por_dia.get(d, 0)
            if d > hoy:
                fondo, col = T["BG"], T["SUB"]
            elif n >= obj:
                fondo, col = T["OK"], BLANCO
            elif n > 0:
                fondo, col = T["REG"], BLANCO
            else:
                fondo, col = T["SEC"], T["SUB"]
            cal.add_widget(Celda(fondo, text=str(d.day), font_size=fs(14), bold=(d == hoy), color=col,
                                 size_hint_y=None, height=dp(36)))
        c.add_widget(cal)
        c.add_widget(lbl("Verde: objetivo cumplido  ·  Naranja: practicado  ·  Gris: sin práctica", 12,
                         T["SUB"], halign="center"))
        return scroll(c)

    def set_objetivo(self, txt):
        try:
            self.objetivo = max(1, min(int(txt), 9999))
        except ValueError:
            return
        self.guardar_aj()
        self.perfil(abrir=4)


if __name__ == "__main__":
    LMApp().run()
