"""
Fuente: FYMELCO (WooCommerce Store API)

Fymelco NO es solo cocina. Vende tres cosas muy distintas:
  - cocina y bano: piletas, mesadas, griferia, anafes, hornos, campanas
  - electrodomesticos: heladeras, microondas, lavavajillas
  - material de construccion: policarbonatos, perfiles de aluminio,
    canos, revestimientos, mosaicos, ladrillos de vidrio

MARCA: la API trae el campo "brands" con la marca de verdad. Se usa ESE
campo y nada mas. Antes la marca se adivinaba con palabras clave y, si
no coincidia ninguna, se ponia TEKA por defecto: eso le puso marca TEKA
a 212 productos que no son TEKA, entre ellos las planchuelas de
aluminio, los perfiles, las siliconas Dow Corning y dos anafes Gorenje.
Un producto sin marca en la API se publica como "Fymelco", que es
cierto, en lugar de inventarle una.

PRECIO: la Store API devuelve el precio en la unidad MINIMA de la moneda
(currency_minor_unit), asi que hay que dividir. Sin eso los precios
salen 100 veces mas caros. Precios en USD, sin margen.

Los productos con precio 0 (los mosaicos de vidrio, que Fymelco publica
sin precio) no se pueden publicar y quedan afuera.
"""
import requests, re, html, time
from fuentes.unificar import unificar

NOMBRE = "fymelco"
API = "https://fymelco.com.uy/wp-json/wc/store/v1/products"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; EdificaBot/1.0)"}

def _limpiar(t):
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', html.unescape(t or ""))).strip()

def detectar_marca(prod):
    """La marca que declara Fymelco, o "Fymelco" si el producto no tiene.

    No se adivina nunca: o la dice la API, o es Fymelco."""
    for b in prod.get("brands") or []:
        nombre = (b.get("name") or "").strip()
        if nombre:
            return nombre
    return "Fymelco"


# Categoria de Fymelco -> (Type, subcategoria de Edifica).
# El orden importa: se recorre de arriba hacia abajo y gana la primera
# que el producto tenga, asi "Anafes" le gana a "Electrodomesticos" y
# "Ondulado y greca" le gana a "Policarbonatos y techos".
MAPEO = [
    # --- material de construccion ---
    ("Ondulado y greca",              ("Ferretería", "Policarbonatos")),
    ("Alveolar",                      ("Ferretería", "Policarbonatos")),
    ("Compacto y acrílico",           ("Ferretería", "Policarbonatos")),
    ("Aleros",                        ("Ferretería", "Policarbonatos")),
    ("Policarbonatos y techos",       ("Ferretería", "Policarbonatos")),
    ("Perfiles U y T",                ("Ferretería", "Perfiles de Aluminio")),
    ("Ángulos",                       ("Ferretería", "Perfiles de Aluminio")),
    ("Planchuelas y terminaciones",   ("Ferretería", "Perfiles de Aluminio")),
    ("Caños y tubos",                 ("Ferretería", "Perfiles de Aluminio")),
    ("Perfiles de aluminio",          ("Ferretería", "Perfiles de Aluminio")),
    ("Mosaicos de vidrio",            ("Ferretería", "Revestimientos")),
    ("Ladrillos de vidrio",           ("Ferretería", "Revestimientos")),
    ("Placas de PVC",                 ("Ferretería", "Revestimientos")),
    ("Revestimientos",                ("Ferretería", "Revestimientos")),
    ("Kits de instalación",           ("Ferretería", "Ferretería")),
    ("Accesorios de instalación",     ("Ferretería", "Ferretería")),

    # --- electrodomesticos ---
    ("Accesorios de hornos y anafes", ("Electro", "Cocinas")),
    ("Anafes",                        ("Electro", "Cocinas")),
    ("Hornos",                        ("Electro", "Cocinas")),
    ("Microondas",                    ("Electro", "Cocinas")),
    ("Filtros y accesorios de campanas", ("Electro", "Campanas")),
    ("Campanas de pared",             ("Electro", "Campanas")),
    ("Campanas de isla",              ("Electro", "Campanas")),
    ("Campanas de empotrar",          ("Electro", "Campanas")),
    ("Campanas de mesada",            ("Electro", "Campanas")),
    ("Campanas de techo",             ("Electro", "Campanas")),
    ("Campanas",                      ("Electro", "Campanas")),
    ("Heladeras, freezers y cavas",   ("Electro", "Heladeras")),
    ("Lavavajillas y lavarropas",     ("Electro", "Lavavajillas")),
    ("Cafeteras y pequeños electrodomésticos", ("Electro", "Pequeños Electrodomésticos")),
    ("Repuestos de electrodomésticos", ("Electro", "Repuestos")),

    # --- bano ---
    ("Extractores de baño",           ("Baño", "Extractores")),
    ("Dispensadores de jabón",        ("Baño", "Accesorios de Baño")),
    ("Desagües de piso",              ("Baño", "Desagües")),
    ("Válvulas y sifones",            ("Baño", "Desagües")),
    ("Espejos",                       ("Baño", "Espejos")),
    ("Ducha",                         ("Baño", "Duchas")),
    ("Grifería",                      ("Baño", "Grifería")),
    ("Baño",                          ("Baño", "Baño")),

    # --- piletas y mesadas ---
    # va primero: una tabla de madera comparte categoria con los
    # accesorios de pileta, pero no es una pileta
    ("Escurridores, cestos y tablas", ("Hogar", "Utensilios de Cocina")),
    ("Lavaderos y piletas profesionales", ("Hogar", "Piletas")),
    ("Piletas de cuarzo y loza",      ("Hogar", "Piletas")),
    ("Piletas multifunción",          ("Hogar", "Piletas")),
    ("Piletas simples",               ("Hogar", "Piletas")),
    ("Piletas dobles",                ("Hogar", "Piletas")),
    ("Bachas y lavamanos",            ("Hogar", "Piletas")),
    ("Mesadas",                       ("Hogar", "Piletas")),
    ("Accesorios para piletas",       ("Hogar", "Piletas")),
    ("Piletas y mesadas",             ("Hogar", "Piletas")),

    # --- hogar ---
    ("Ollas y sartenes",              ("Hogar", "Cocina")),
    ("Basureros y papeleras",         ("Hogar", "Organizadores")),
    ("Soportes y organizadores",      ("Hogar", "Organizadores")),
    ("Basureros y organización",      ("Hogar", "Organizadores")),
    ("Limpieza y cuidado",            ("Hogar", "Limpieza")),
    ("Cocina y bazar",                ("Hogar", "Cocina")),
    ("Cocina",                        ("Hogar", "Cocina")),

    # --- genericas, van ultimas a proposito ---
    ("Electrodomésticos",             ("Electro", "Otros")),
    ("Varios",                        ("Ferretería", "Ferretería")),
]


def clasificar(prod):
    """Clasifica por las categorias que declara Fymelco."""
    suyas = {c.get("name") for c in prod.get("categories", []) or []}
    for nombre, destino in MAPEO:
        if nombre in suyas:
            return destino
    # Si aparece una categoria nueva que no esta en el MAPEO, cae aca.
    # Se avisa para poder agregarla.
    if suyas:
        print(f"  fymelco: categoria sin mapear -> {', '.join(sorted(suyas))}")
    return ("Hogar", "Otros")


def _handle(sku, slug):
    base = slug or sku
    return "fy-" + re.sub(r'[^a-z0-9]+', '-', base.lower()).strip('-')

COLS = ["Handle","Title","Body HTML","Vendor","Type","Tags","Published",
        "Option1 Name","Option1 Value","Variant SKU","Variant Price",
        "Variant Compare At Price","Variant Inventory Qty",
        "Variant Inventory Policy","Image Src","Image Position"]

def _traer_pagina(page):
    """Pide una pagina del catalogo. Reintenta con esperas crecientes porque
    el servidor de Fymelco a veces responde con una pagina de espera en lugar
    del JSON. Devuelve la lista de productos, o None si no se pudo."""
    espera = 5
    for intento in range(1, 6):
        try:
            r = requests.get(API, headers=HEADERS,
                             params={"per_page": 100, "page": page}, timeout=90)
        except Exception as e:
            print(f"  fymelco: pagina {page}, intento {intento}: error de red ({str(e)[:50]})")
            time.sleep(espera); espera = min(espera * 2, 60)
            continue
        if r.status_code == 200 and r.text.lstrip().startswith("["):
            try:
                return r.json()
            except Exception:
                pass
        print(f"  fymelco: pagina {page}, intento {intento}: respuesta no valida "
              f"(HTTP {r.status_code})")
        time.sleep(espera); espera = min(espera * 2, 60)
    return None


def obtener():
    productos = []
    page = 1
    while True:
        d = _traer_pagina(page)
        if d is None:
            # No se pudo leer esta pagina. Si ya habia productos, el catalogo
            # quedaria INCOMPLETO y combinar.py podria dar de baja productos
            # que si existen. Es preferible fallar y usar el respaldo del dia
            # anterior, que publicar medio catalogo.
            raise RuntimeError(
                f"Fymelco: no se pudo leer la pagina {page} tras 5 intentos "
                f"({len(productos)} productos leidos hasta ahi; se usa el respaldo)")
        if not d:
            break
        productos.extend(d)
        page += 1
        if page > 30: break
        time.sleep(1)
    if not productos:
        raise RuntimeError("Fymelco: API sin productos")
    print(f"  fymelco: {len(productos)} productos leidos de la web")

    filas = []
    publicados = 0
    for p in productos:
        title = _limpiar(p.get("name"))
        if title == "Test Plexo (QA Cygnus)":  # producto de prueba
            continue
        pr = p.get("prices", {})
        precio_raw = pr.get("price", "0")
        regular_raw = pr.get("regular_price", precio_raw)
        # La Store API devuelve el precio en la unidad MINIMA de la moneda:
        # "295245" con currency_minor_unit=2 son USD 2.952,45, no 295.245.
        # Sin esta division los precios salen 100 veces mas caros.
        escala = 10 ** int(pr.get("currency_minor_unit", 0) or 0)
        try:
            precio = f"{round(float(precio_raw) / escala, 2)}"
            regular = f"{round(float(regular_raw) / escala, 2)}"
        except Exception:
            continue
        if precio in ("0","0.0","1","1.0"): continue
        # Guardia: ningun articulo de Fymelco supera los USD 20.000.
        # Si aparece uno, algo cambio en la API y es mejor no publicarlo
        # que publicar un precio de millones de pesos.
        if float(precio) > 20000:
            print(f"  fymelco: PRECIO SOSPECHOSO, no se publica -> {title[:50]} (USD {precio})")
            continue

        short = _limpiar(p.get("short_description"))
        desc_raw = p.get("description") or ""
        marca = detectar_marca(p)
        madre, sub = clasificar(p)
        sub = unificar(sub)
        h = _handle(str(p.get("sku") or p.get("id")), p.get("slug"))
        body = desc_raw or short or title
        oferta = p.get("on_sale", False)
        hay_stock = p.get("is_in_stock")
        imgs = [im.get("src") for im in p.get("images", []) if im.get("src")]

        tg = ", ".join([t for t in [sub, marca] + (["stock-verificado"] if hay_stock else []) if t])
        fila = {c:"" for c in COLS}
        fila.update({
            "Handle":h, "Title":title, "Body HTML":body, "Vendor":marca, "Type":madre,
            "Tags":tg, "Published":"TRUE", "Option1 Name":"Título", "Option1 Value":"Default Title",
            "Variant SKU":str(p.get("sku") or p.get("id")), "Variant Price":precio,
            "Variant Compare At Price":regular if oferta else "",
            "Variant Inventory Qty":"10" if hay_stock else "0", "Variant Inventory Policy":"deny",
        })
        if imgs: fila["Image Src"]=imgs[0]; fila["Image Position"]="1"
        filas.append(fila); publicados += 1
        for pos,url in enumerate(imgs[1:],2):
            filas.append({**{c:"" for c in COLS},"Handle":h,"Image Src":url,"Image Position":str(pos)})

    return filas, publicados

if __name__ == "__main__":
    filas, n = obtener()
    print(f"Fymelco: {n} productos, {len(filas)} filas")
