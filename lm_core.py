# -*- coding: utf-8 -*-
"""Lógica de LM (sin interfaz): listas, progreso, historial, estadísticas, rachas y el cuestionario.
Es la misma lógica de la versión de escritorio, separada de la pantalla para poder usarla en Android."""
import csv
import io
import json
import os
import random
import unicodedata
from datetime import date, datetime, timedelta

DIRECCIONES = ["Español -> Idioma", "Idioma -> Español", "Mezcla"]
ORDENES = ["Por defecto", "Alfabético", "Al azar", "Adaptativo (más falladas primero)"]
MODOS = ["Escribir la palabra", "Opción múltiple", "Flashcards"]
TAMANOS = {"XXS": 0.70, "XS": 0.80, "S": 0.90, "M": 1.0, "L": 1.15, "XL": 1.30, "XXL": 1.50}
FMT = "%Y-%m-%d %H:%M:%S"
TODOS = "Todos los modos"
TODAS = "Todas las listas"

AJ = PROGRESO = HIST = SESION = None


def configurar(directorio):
    """Indica la carpeta donde se guardan los datos (en Android: la carpeta privada de la app)."""
    global AJ, PROGRESO, HIST, SESION
    os.makedirs(directorio, exist_ok=True)
    AJ = os.path.join(directorio, "ajustes_lm.json")
    PROGRESO = os.path.join(directorio, "progreso_palabras.json")
    HIST = os.path.join(directorio, "historial_lm.json")
    SESION = os.path.join(directorio, "sesion_lm.json")


def cargar_sesion():
    try:
        with open(SESION, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def guardar_sesion(rutas, encabezado):
    try:
        with open(SESION, "w", encoding="utf-8") as f:
            json.dump({"rutas": list(rutas), "enc": bool(encabezado)}, f, ensure_ascii=False)
    except OSError:
        pass


def parse_custom(texto):
    """Lista escrita a mano: una pareja por línea separada por coma (o punto y coma)."""
    out = []
    for linea in texto.splitlines():
        p = [x.strip().lower() for x in linea.replace(";", ",").split(",")]
        if len(p) >= 2 and p[0] and p[1]:
            out.append((p[0], p[1]))
    return out


def norm(s):
    return s.strip().lower()


def clave(s):
    """Clave de ordenación sin tildes ni mayúsculas (árbol va junto a arbol)."""
    return "".join(c for c in unicodedata.normalize("NFKD", norm(s)) if not unicodedata.combining(c))


def _importar_openpyxl():
    try:
        import openpyxl
    except ImportError:
        raise RuntimeError("Para usar archivos .xlsx necesitas la librería openpyxl.\n"
                           "Instálala con:   pip install openpyxl")
    return openpyxl


def _celda(c):
    if c is None:
        return ""
    if isinstance(c, float) and c.is_integer():
        c = int(c)
    return str(c).strip()


def leer_filas_xlsx(ruta):
    """Filas de la primera hoja de un Excel, ya como texto y sin celdas vacías sobrantes."""
    openpyxl = _importar_openpyxl()
    wb = openpyxl.load_workbook(ruta, read_only=True, data_only=True)
    try:
        ws = wb.active
        if ws is None:
            return []
        filas = []
        for fila in ws.iter_rows(values_only=True):
            r = [_celda(c) for c in fila]
            while r and not r[-1]:
                r.pop()
            filas.append(r)
        return filas
    finally:
        wb.close()


def leer_lista(ruta, encabezado=True):
    """Lee un CSV/TXT/XLSX. Devuelve (filas, con_articulos).
    2 columnas: español, idioma  |  4 columnas: art_esp, español, art_idioma, idioma"""
    if ruta.lower().endswith(".xls"):
        raise RuntimeError("El formato .xls antiguo no se admite.\nGuárdalo como .xlsx desde Excel.")
    if ruta.lower().endswith(".xlsx"):
        filas = leer_filas_xlsx(ruta)
    else:
        texto = None
        for cod in ("utf-8-sig", "latin-1"):
            try:
                with open(ruta, encoding=cod, newline="") as f:
                    texto = f.read()
                break
            except UnicodeDecodeError:
                continue
        try:
            dialecto = csv.Sniffer().sniff(texto[:2048], delimiters=",;\t")
        except csv.Error:
            dialecto = csv.excel
        filas = [[c.strip() for c in r] for r in csv.reader(texto.splitlines(), dialecto)]
    filas = [r for r in filas if any(r)]
    if encabezado:
        filas = filas[1:]
    art = bool(filas) and len(filas[0]) >= 4
    if art:
        validas = [tuple(r[:4]) for r in filas if len(r) >= 4 and r[1] and r[3]]
    else:
        validas = [tuple(r[:2]) for r in filas if len(r) >= 2 and r[0] and r[1]]
    return validas, art


def filas_a_texto(filas):
    """Filas -> texto CSV (con comillas si una palabra lleva comas) para el editor."""
    buf = io.StringIO()
    csv.writer(buf, lineterminator="\n").writerows(filas)
    return buf.getvalue()


def texto_a_filas(texto, art):
    """Texto del editor -> filas válidas. Con artículos solo hacen falta las dos palabras:
    el artículo puede quedar vacío (plurales, etc.)."""
    n = 4 if art else 2
    out = []
    for r in csv.reader(texto.splitlines()):
        r = [c.strip() for c in r][:n]
        if len(r) < n:
            continue
        if (r[1] and r[3]) if art else (r[0] and r[1]):
            out.append(tuple(r))
    return out


def guardar_lista_en_archivo(ruta, filas, con_encabezado=True, con_articulos=False):
    """Guarda las filas en la ruta indicada (CSV/TXT, o Excel si termina en .xlsx)."""
    cab = (["art_esp", "español", "art_idioma", "idioma"] if con_articulos
           else ["español", "idioma"]) if con_encabezado else None
    try:
        if ruta.lower().endswith(".xlsx"):
            wb = _importar_openpyxl().Workbook()
            ws = wb.active
            if cab:
                ws.append(cab)
            for r in filas:
                ws.append(list(r))
            wb.save(ruta)
        else:
            with open(ruta, "w", encoding="utf-8-sig", newline="") as f:
                w = csv.writer(f)
                if cab:
                    w.writerow(cab)
                w.writerows(filas)
        return True
    except (OSError, RuntimeError):
        return False


def a_un_caracter(a, b):
    if a == b or abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        return sum(x != y for x, y in zip(a, b)) == 1
    if len(a) > len(b):
        a, b = b, a
    return any(b[:i] + b[i + 1:] == a for i in range(len(b)))


def texto_resp(fila, art):
    return f"{fila[2]} {fila[3]}".strip() if art else fila[1]


def orientar(filas, art, modo):
    """modo 0: español→idioma, 1: idioma→español, 2: mezcla (conserva el orden de las filas)."""
    out = []
    for r in filas:
        b = (r[2], r[3], r[0], r[1]) if art else (r[1], r[0])
        out.append(r if modo == 0 else b if modo == 1 else random.choice((r, b)))
    return out


def cargar_ajustes():
    aj = {"oscuro": False, "tamano": "M", "timer": False, "objetivo": 20}
    try:
        with open(AJ, encoding="utf-8") as f:
            d = json.load(f)
        if isinstance(d, dict):
            aj["oscuro"] = bool(d.get("oscuro", False))
            aj["timer"] = bool(d.get("timer", False))
            if d.get("tamano") in TAMANOS:
                aj["tamano"] = d["tamano"]
            try:
                aj["objetivo"] = max(1, min(int(d.get("objetivo", 20)), 9999))
            except (TypeError, ValueError):
                pass
    except (OSError, ValueError):
        pass
    return aj


def guardar_ajustes(aj):
    try:
        with open(AJ, "w", encoding="utf-8") as f:
            json.dump(aj, f, indent=1)
    except OSError:
        pass


def cargar_progreso():
    try:
        with open(PROGRESO, encoding="utf-8") as f:
            datos = json.load(f)
        if isinstance(datos, dict):
            return datos
    except (OSError, ValueError):
        pass
    return {}


def guardar_progreso(progreso):
    try:
        with open(PROGRESO, "w", encoding="utf-8") as f:
            json.dump(progreso, f, ensure_ascii=False, indent=1)
    except OSError:
        pass


def registrar_resultado_palabras(registro_intentos):
    """registro_intentos: {(lista_origen, español, idioma): {"acierto": bool, "arts": (a, b) | None}}"""
    progreso = cargar_progreso()
    ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for (lista, esp, idio), info in registro_intentos.items():
        datos = progreso.get(lista)
        if not isinstance(datos, dict):               # datos dañados -> se reinicia esa lista
            datos = progreso[lista] = {}
        k = f"{esp}|||{idio}"
        p = datos.get(k)
        if not isinstance(p, dict):
            p = datos[k] = {}
        p["vistas"] = int(p.get("vistas", 0)) + 1
        p["fallos"] = int(p.get("fallos", 0)) + (0 if info["acierto"] else 1)
        p["ult_fecha"] = ahora
        if info.get("arts"):
            p["arts"] = list(info["arts"])
    guardar_progreso(progreso)


def obtener_tasa_error(progreso, nombre_lista, fila_orig):
    """Proporción de fallos de una palabra (0.5 si todavía no se ha visto)."""
    esp = fila_orig[1] if len(fila_orig) >= 4 else fila_orig[0]
    idio = fila_orig[3] if len(fila_orig) >= 4 else fila_orig[1]
    lista = progreso.get(nombre_lista)
    p = lista.get(f"{esp}|||{idio}") if isinstance(lista, dict) else None
    try:
        vistas, fallos = int(p["vistas"]), int(p["fallos"])
    except (TypeError, KeyError, ValueError):
        return 0.5
    return fallos / vistas if vistas else 0.5


def palabras_dificiles(progreso, n=None):
    """Palabras falladas alguna vez, de más a menos fallos (a igualdad, mayor % de fallos)."""
    out = []
    for lista, datos in progreso.items():
        if not isinstance(datos, dict):
            continue
        for k, p in datos.items():
            try:
                vistas, fallos = int(p["vistas"]), int(p["fallos"])
                esp, idio = k.split("|||", 1)
            except (TypeError, KeyError, ValueError):
                continue
            if vistas > 0 and fallos > 0:
                arts = p.get("arts")
                out.append({"lista": lista, "esp": esp, "idio": idio, "vistas": vistas,
                            "fallos": fallos, "tasa": fallos / vistas,
                            "arts": tuple(arts) if isinstance(arts, list) and len(arts) == 2 else None})
    out.sort(key=lambda r: (-r["fallos"], -r["tasa"], clave(r["esp"])))
    return out[:n] if n else out


def preparar(filas, art, orden, n, filas_origen=None, fuentes=None):
    """Aplica el orden elegido y se queda con las n primeras.
    Devuelve (filas, filas_originales, fuentes) SIEMPRE alineadas: la palabra i de cada lista es
    la misma, se ordene como se ordene y se recorte como se recorte.
    `fuentes` es el nombre de la lista de la que sale cada palabra (para combinar varias)."""
    orig = filas if filas_origen is None else filas_origen
    src = fuentes if fuentes is not None else [""] * len(filas)
    ternas = list(zip(filas, orig, src))
    if orden == "Alfabético":
        ternas.sort(key=lambda t: clave(t[0][1] if art else t[0][0]))
    elif orden == "Al azar":
        random.shuffle(ternas)
    elif orden == ORDENES[3]:                      # adaptativo: se lee el progreso una sola vez
        progreso = cargar_progreso()
        ternas.sort(key=lambda t: (obtener_tasa_error(progreso, t[2], t[1]), random.random()),
                    reverse=True)
    ternas = ternas[:max(1, min(n, len(ternas)))]
    return [t[0] for t in ternas], [t[1] for t in ternas], [t[2] for t in ternas]


def cargar_hist():
    try:
        with open(HIST, encoding="utf-8") as f:
            datos = json.load(f)
    except (OSError, ValueError):
        return []
    if not isinstance(datos, list):
        return []
    return [e for e in datos if isinstance(e, dict) and {"fecha", "archivo", "pct"} <= e.keys()]


def guardar_hist(hist):
    try:
        with open(HIST, "w", encoding="utf-8") as f:
            json.dump(hist, f, ensure_ascii=False, indent=1)
    except OSError:
        pass


def _n(e):
    try:
        return int(e.get("palabras") or 0)
    except (TypeError, ValueError):
        return 0


def estadisticas(hist, modo=None):
    """[(archivo, modo, palabras, listas, media)] agrupado por archivo, modo y nº de palabras."""
    grupos = {}
    for e in hist:
        if modo and e.get("modo") != modo:
            continue
        grupos.setdefault((e["archivo"], e.get("modo", "—"), _n(e)), []).append(e["pct"])
    claves = sorted(grupos, key=lambda k: (clave(k[0]), k[1], k[2]))
    return [(a, md, n, len(grupos[(a, md, n)]), sum(grupos[(a, md, n)]) / len(grupos[(a, md, n)]))
            for a, md, n in claves]


def palabras_aprendidas(hist, modo=None):
    """Por nombre de lista: palabras de la versión más larga × su % medio de aciertos."""
    por_lista = {}
    for e in hist:
        if modo and e.get("modo") != modo:
            continue
        por_lista.setdefault(e["archivo"], []).append((_n(e), e["pct"]))
    total = 0.0
    for entradas in por_lista.values():
        mayor = max(n for n, _ in entradas)
        pcts = [pct for n, pct in entradas if n == mayor]
        total += mayor * (sum(pcts) / len(pcts)) / 100
    return int(total + 0.5)


def _dia(e):
    try:
        return datetime.strptime(e["fecha"], FMT).date()
    except (ValueError, TypeError, KeyError):
        return None


def fecha_bonita(txt):
    try:
        return datetime.strptime(txt, FMT).strftime("%d/%m/%Y  %H:%M")
    except (ValueError, TypeError):
        return str(txt)


def serie_diaria(hist, lista=None, modo=None):
    """[(día, media de aciertos de ese día, nº de listas)] ordenado por fecha."""
    dias = {}
    for e in hist:
        if (lista and e.get("archivo") != lista) or (modo and e.get("modo") != modo):
            continue
        d = _dia(e)
        if d:
            dias.setdefault(d, []).append(e["pct"])
    return [(d, sum(v) / len(v), len(v)) for d, v in sorted(dias.items())]


def palabras_por_dia(hist):
    """{día: palabras practicadas ese día} (suma de todas las listas, repasos incluidos)."""
    por_dia = {}
    for e in hist:
        d = _dia(e)
        if d:
            por_dia[d] = por_dia.get(d, 0) + _n(e)
    return por_dia


def calcular_rachas(por_dia, objetivo, hoy):
    """(racha actual, mejor racha) en días seguidos con palabras >= objetivo.
    La racha actual no se rompe hasta que acaba el día: si hoy aún no se ha cumplido, cuenta desde ayer."""
    objetivo = max(1, objetivo)
    ok = {d for d, n in por_dia.items() if n >= objetivo}
    d = hoy if hoy in ok else hoy - timedelta(days=1)
    actual = 0
    while d in ok:
        actual += 1
        d -= timedelta(days=1)
    mejor = 0
    for d in ok:
        if d - timedelta(days=1) not in ok:           # primer día de una racha
            k, x = 1, d
            while x + timedelta(days=1) in ok:
                k, x = k + 1, x + timedelta(days=1)
            mejor = max(mejor, k)
    return actual, mejor


def fmt_tiempo(seg):
    cs = int(seg * 100)
    return f"{cs // 6000:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"


# ---------------------------------------------------------------- listas cargadas
class Listas:
    """Una o varias listas combinadas en una sola sesión."""

    def __init__(self):
        self.items = []          # {"ruta", "nombre", "filas", "art"}
        self.base, self.base_src, self.art = [], [], False

    def agregar(self, ruta, nombre=None, encabezado=True):
        """Lee una lista y la añade (si ya estaba, se actualiza). Devuelve None o el error."""
        nombre = nombre or os.path.basename(ruta)
        try:
            filas, art = leer_lista(ruta, encabezado)
        except Exception as e:
            return f"{nombre}: {e}"
        if not filas:
            return f"{nombre}: no tiene palabras válidas (revisa el formato y el encabezado)"
        nueva = {"ruta": ruta, "nombre": nombre, "filas": filas, "art": art}
        for k, l in enumerate(self.items):
            if l["ruta"] == ruta:
                self.items[k] = nueva
                break
        else:
            self.items.append(nueva)
        self.recombinar()
        return None

    def quitar(self, i):
        del self.items[i]
        self.recombinar()

    def recargar(self, encabezado):
        errores = []
        for l in list(self.items):
            e = self.agregar(l["ruta"], l["nombre"], encabezado)
            if e:
                errores.append(e)
        return errores

    def recombinar(self):
        """Si alguna lista lleva artículos, las demás se completan con artículo vacío."""
        self.art = any(l["art"] for l in self.items)
        self.base, self.base_src = [], []
        for l in self.items:
            for r in l["filas"]:
                if self.art and not l["art"]:
                    r = ("", r[0], "", r[1])
                self.base.append(r)
                self.base_src.append(l["nombre"])

    def nombre_sesion(self):
        nombres = [l["nombre"] for l in self.items]
        if len(nombres) <= 3:
            return " + ".join(nombres)
        return " + ".join(nombres[:2]) + f" + {len(nombres) - 2} más"


# ---------------------------------------------------------------- cuestionario (sin pantalla)
class Quiz:
    """Estado y reglas de una ronda: tres modos, pistas, 'casi correcto', progreso y repaso."""

    def __init__(self, filas, art, modo, pool=None, nombre="", repaso=False,
                 filas_orig=None, fuentes=None):
        self.filas, self.art, self.modo = filas, art, modo
        self.pool = pool or filas
        self.filas_orig = filas_orig or filas        # alineada con filas
        self.fuentes = fuentes or [nombre] * len(filas)
        self.nombre, self.es_repaso = nombre, repaso
        self.i = self.ok = self.mal = self.parcial = self.resp = self.pistas_n = 0
        self.falladas, self.falladas_orig, self.falladas_fuente = [], [], []
        self.registro = {}
        self.reveladas = set()
        self.casi = self.hecho = self.revelada = False

    # --- datos de la palabra actual
    def valido(self):
        if self.modo == MODOS[1]:
            return len({texto_resp(f, self.art) for f in self.pool}) >= 2
        return True

    def fila(self):
        return self.filas[self.i]

    def con_art(self):
        """¿Se responde con artículo? Solo si la palabra tiene el suyo."""
        return bool(self.art and self.fila()[2])

    def palabra(self):
        f = self.fila()
        return f[3] if self.art else f[1]

    def pregunta(self):
        f = self.fila()
        return f"{f[0]} {f[1]}".strip() if self.art else f[0]

    def origen(self):
        return self.fuentes[self.i]

    def correcta(self):
        return texto_resp(self.fila(), self.art)

    def nuevo(self):
        self.reveladas = set()
        self.casi = self.hecho = self.revelada = False

    # --- pistas
    def exceso(self):
        """Más de la mitad de las letras descubiertas -> la palabra no puntúa."""
        letras = sum(ch.isalnum() for ch in self.palabra())
        return len(self.reveladas) * 2 > letras

    def pista(self):
        """Descubre una letra más. Devuelve (texto, letras_que_quedan) o None."""
        if self.modo == MODOS[1] or self.hecho or self.revelada:
            return None
        p = self.palabra()
        ocultas = [k for k, ch in enumerate(p) if ch.isalnum() and k not in self.reveladas]
        if not ocultas:
            return None
        self.reveladas.add(random.choice(ocultas))
        texto = " ".join(ch if (not ch.isalnum() or k in self.reveladas) else "_"
                         for k, ch in enumerate(p))
        return texto, len(ocultas) - 1

    # --- anotar resultados
    def _repaso(self):
        f = self.fila()
        if f not in self.falladas:
            self.falladas.append(f)
            self.falladas_orig.append(self.filas_orig[self.i])
            self.falladas_fuente.append(self.fuentes[self.i])

    def _anotar(self, acierto):
        fo = self.filas_orig[self.i]
        con = len(fo) >= 4
        esp, idio = (fo[1], fo[3]) if con else (fo[0], fo[1])
        self.registro[(self.fuentes[self.i], esp, idio)] = {
            "acierto": acierto, "arts": (fo[0], fo[2]) if con else None}

    # --- modo escribir
    def comprobar(self, art_txt, pal_txt):
        """Devuelve {"tipo": casi|ok|ok_rect|ok_exceso|mal_exceso|parcial_art|parcial_pal|mal, ...}"""
        f, p, con = self.fila(), self.palabra(), self.con_art()
        ok_a = (norm(art_txt) == norm(f[2])) if con else True
        ok_p = norm(pal_txt) == norm(p)
        exceso = self.exceso()
        if (not ok_p and not self.casi and not exceso and len(p) >= 3
                and a_un_caracter(norm(pal_txt), norm(p))):
            self.casi = True
            return {"tipo": "casi", "revisar_art": not ok_a}
        self.hecho = True
        self.resp += 1
        usada = bool(self.reveladas)
        if usada:
            self._repaso()
        acierto = False
        if exceso:
            self.pistas_n += 1
            tipo = "exceso_ok" if (ok_a and ok_p) else "mal_exceso"
        elif ok_a and ok_p:
            self.ok += 1
            acierto = True
            tipo = "ok_rect" if self.casi else "ok"
        elif con and (ok_a or ok_p):
            self.parcial += 1
            self._repaso()
            tipo = "parcial_art" if ok_a else "parcial_pal"
        else:
            self.mal += 1
            self._repaso()
            tipo = "mal"
        self._anotar(acierto)
        return {"tipo": tipo, "correcta": self.correcta(), "pista": usada}

    # --- opción múltiple
    def opciones(self):
        c = self.correcta()
        otras = list({texto_resp(f, self.art) for f in self.pool} - {c})
        random.shuffle(otras)
        ops = otras[:3] + [c]
        random.shuffle(ops)
        return ops

    def elegir(self, elegida):
        c = self.correcta()
        self.hecho = True
        self.resp += 1
        ok = elegida == c
        if ok:
            self.ok += 1
        else:
            self.mal += 1
            self._repaso()
        self._anotar(ok)
        return ok, c

    # --- flashcards
    def mostrar(self):
        self.revelada = True
        return self.correcta(), self.exceso()

    def juzgar(self, acierto):
        self.resp += 1
        if self.reveladas:
            self._repaso()
        if self.exceso():
            self.pistas_n += 1
            self._anotar(False)
        elif acierto:
            self.ok += 1
            self._anotar(True)
        else:
            self.mal += 1
            self._repaso()
            self._anotar(False)

    # --- avance y final
    def avanzar(self):
        self.i += 1
        return self.i < len(self.filas)

    def finalizar(self):
        """Guarda historial y progreso por palabra. Devuelve (palabras puntuadas, % de aciertos)."""
        puntuadas = self.ok + self.mal + self.parcial
        pct = self.ok * 100 / puntuadas if puntuadas else 0
        if puntuadas:
            h = cargar_hist()
            h.append({"fecha": datetime.now().strftime(FMT), "archivo": self.nombre,
                      "pct": round(pct, 1), "repaso": self.es_repaso, "modo": self.modo,
                      "palabras": self.resp})
            guardar_hist(h)
        if self.registro:
            registrar_resultado_palabras(self.registro)
        return puntuadas, pct
