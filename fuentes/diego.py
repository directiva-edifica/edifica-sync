"""
Fuente: DIEGO CENTRO MAYORISTA (diego.com.uy)
Sitio a medida (SublimeSolutions), sin API. Se usa el sitemap para
listar las fichas y el JSON-LD de cada ficha para sacar nombre, SKU,
descripcion, imagenes, precio y stock.

IMPORTANTE - MONEDA: Diego publica en PESOS URUGUAYOS, no en dolares
como el resto de las fuentes. Por eso este modulo declara MONEDA = "UYU"
y combinar.py NO le aplica la conversion USD->UYU. Si se saca esa marca,
los precios se multiplican por la cotizacion y quedan 39 veces mas caros.

MARGEN: los precios de Diego son mayoristas. Se les aplica MARGEN sobre
el precio publicado antes de subirlos.
"""
import re
import json
import time
import requests
from concurrent.futures import ThreadPoolExecutor
from fuentes.unificar import unificar

NOMBRE = "diego"
MONEDA = "UYU"          # <-- evita la conversion de moneda en combinar.py
MARGEN = 0.50           # 50% sobre el precio publicado por Diego
HILOS = 10

SITEMAP = "https://www.diego.com.uy/sitemap.xml"
HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                         "AppleWebKit/537.36 (KHTML, like Gecko) "
                         "Chrome/120.0.0.0 Safari/537.36",
           "Accept-Language": "es-UY,es;q=0.9"}

# Solo estas categorias raiz se publican. Para sumar mas, agregar aca.
# Disponibles y NO incluidas por ahora: juguetes, temporadas, cotillon,
# estudio, belleza, mascotas.
CATEGORIAS = {
    "hogar":       "Hogar",
    "ferreteria":  "Ferretería",
    "electronica": "Electro",
    "deporte":     "Deporte",
    "camping":     "Camping",
    "viajes":      "Viajes",
}

# Mapa de subcategorias de Diego -> (Type, subcategoria de Edifica).
# La clave es la ruta de Diego SIN la categoria raiz. Se busca por
# coincidencia mas larga, asi que "cocina-y-bazar/vajilla/platos" cae en
# "cocina-y-bazar/vajilla" si no tiene entrada propia, y si tampoco la
# tiene, en "cocina-y-bazar".
# Cuando una subcategoria de Diego coincide con una que ya usamos
# (Iluminación, Jardín, Audio, Accesorios Auto, Tecnología), se reutiliza
# la nuestra para que no queden tags duplicados.
SUBCATEGORIAS = {
    # ---------- HOGAR ----------
    "cocina-y-bazar":                        ("Hogar", "Bazar"),
    "cocina-y-bazar/ollas-y-sartenes":       ("Hogar", "Cocina"),
    "cocina-y-bazar/asaderas":               ("Hogar", "Cocina"),
    "cocina-y-bazar/cortadores-y-ralladores": ("Hogar", "Cocina"),
    "cocina-y-bazar/tablas":                 ("Hogar", "Cocina"),
    "cocina-y-bazar/coladores":              ("Hogar", "Cocina"),
    "cocina-y-bazar/escurridores":           ("Hogar", "Cocina"),
    "cocina-y-bazar/jarras-y-calderas":      ("Hogar", "Cocina"),
    "cocina-y-bazar/pasteleria-y-reposteria": ("Hogar", "Repostería"),
    "cocina-y-bazar/utensilios-de-cocina":   ("Hogar", "Utensilios de Cocina"),
    "cocina-y-bazar/tramontina":             ("Hogar", "Cocina"),
    "cocina-y-bazar/vajilla":                ("Hogar", "Vajilla"),
    "cocina-y-bazar/luminarc":               ("Hogar", "Vajilla"),
    "cocina-y-bazar/durax":                  ("Hogar", "Vajilla"),
    "cocina-y-bazar/botellas-y-recipientes": ("Hogar", "Bazar"),
    "cocina-y-bazar/manteleria":             ("Hogar", "Mantelería"),
    "cocina-y-bazar/electrodomesticos":      ("Electro", "Otros"),
    "decoracion":                            ("Hogar", "Decoración"),
    "organizadores":                         ("Hogar", "Organizadores"),
    "bano":                                  ("Hogar", "Baño"),
    "ropa-de-cama":                          ("Hogar", "Ropa de Cama"),
    "limpieza-y-lavanderia":                 ("Hogar", "Limpieza"),
    "colchones-y-sofas":                     ("Hogar", "Colchones y Sofás"),
    "jardin":                                ("Jardín", "Jardín"),
    "jardin/herramientas-de-jardin":         ("Jardín", "Herramientas de Jardín"),
    "jardin/macetas":                        ("Jardín", "Macetas"),
    "jardin/flores-y-plantas":               ("Jardín", "Plantas"),
    "jardin/toldos-y-sombras":               ("Jardín", "Jardín"),

    # ---------- FERRETERIA ----------
    "varios":                                ("Ferretería", "Ferretería"),
    "herramientas":                          ("Ferretería", "Herramientas"),
    "herramientas-electricas":               ("Ferretería", "Herramientas Eléctricas"),
    "acc-bicicletas":                        ("Deporte", "Bicicletas"),
    "acc-para-autos":                        ("Accesorios", "Accesorios Auto"),
    "pegamentos":                            ("Ferretería", "Adhesivos"),
    "candados-y-lingas":                     ("Ferretería", "Seguridad"),
    "trampas-p":                             ("Ferretería", "Control de Plagas"),
    "articulos-para-viaje":                  ("Viajes", "Accesorios de Viaje"),

    # ---------- ELECTRONICA ----------
    "iluminacion":                           ("Iluminación", "Iluminación"),
    "iluminacion/luces-led":                 ("Iluminación", "Luces LED"),
    "iluminacion/guias-de-luces":            ("Iluminación", "Luces LED"),
    "iluminacion/lamparas-y-veladoras":      ("Iluminación", "Lámparas"),
    "iluminacion/linternas":                 ("Iluminación", "Linternas"),
    "parlantes":                             ("Electro", "Audio"),
    "auriculares":                           ("Electro", "Audio"),
    "acc-para-celular":                      ("Electro", "Tecnología"),
    "relojes":                               ("Electro", "Tecnología"),
    "vigilancia-y-seguridad":                ("Electro", "Seguridad"),
    "baterias-pilas-y-cargadores":           ("Electro", "Pilas y Cargadores"),

    # ---------- DEPORTE ----------
    "indumentaria-y-accesorios":             ("Deporte", "Indumentaria"),
    "bicicletas":                            ("Deporte", "Bicicletas"),
    "rehabilitacion":                        ("Deporte", "Fitness"),
    "colchonetas":                           ("Deporte", "Fitness"),
    "pesas-y-mancuernas":                    ("Deporte", "Fitness"),
    "trofeos-y-medallas":                    ("Deporte", "Deporte"),

    # ---------- CAMPING ----------
    "pesca":                                 ("Camping", "Pesca"),
    "aire-libre":                            ("Camping", "Camping"),
    "acc-varios":                            ("Camping", "Camping"),
    "cuchillos-de-caza":                     ("Camping", "Cuchillos"),

    # ---------- VIAJES ----------
    "equipaje":                              ("Viajes", "Equipaje"),
    "acc-de-viaje":                          ("Viajes", "Accesorios de Viaje"),
}


def clasificar(raiz, ruta):
    """Busca la coincidencia mas larga en SUBCATEGORIAS. Si no hay ninguna,
    cae en la categoria raiz con subcategoria 'Otros'."""
    partes = [p for p in (ruta or "").split("/") if p]
    while partes:
        clave = "/".join(partes)
        if clave in SUBCATEGORIAS:
            return SUBCATEGORIAS[clave]
        partes.pop()
    return CATEGORIAS.get(raiz, "Hogar"), "Otros"


COLS = ["Handle", "Title", "Body HTML", "Vendor", "Type", "Tags", "Published",
        "Option1 Name", "Option1 Value", "Variant SKU", "Variant Price",
        "Variant Compare At Price", "Variant Inventory Qty",
        "Variant Inventory Policy", "Image Src", "Image Position"]


def _titulo(txt):
    """'acc-varios' -> 'Acc Varios'."""
    return " ".join(p.capitalize() for p in (txt or "").replace("-", " ").split())


def _handle(sku, url):
    base = sku or url.rstrip("/").split("/")[-1]
    return "dg-" + re.sub(r'[^a-z0-9]+', '-', base.lower()).strip('-')


def _listar_urls():
    """Devuelve [(url, categoria_raiz, subcategoria)] de las categorias elegidas."""
    r = requests.get(SITEMAP, headers=HEADERS, timeout=90)
    r.raise_for_status()
    urls = []
    for u in re.findall(r'<loc>([^<]+)</loc>', r.text):
        if "/catalogo/" not in u:
            continue
        partes = u.split("/catalogo/")[1].strip("/").split("/")
        if len(partes) < 2:
            continue
        raiz = partes[0].lower()
        if raiz not in CATEGORIAS:
            continue
        if partes[-1] == "diego":     # es una pagina de listado, no un producto
            continue
        # ruta de subcategorias sin la raiz ni el slug del producto
        ruta = "/".join(partes[1:-1])
        urls.append((u.replace("http://", "https://"), raiz, ruta))
    # sin duplicados, conservando el orden
    vistos, limpio = set(), []
    for t in urls:
        if t[0] not in vistos:
            vistos.add(t[0]); limpio.append(t)
    return limpio


def _ficha(args):
    """Baja una ficha y devuelve el producto del JSON-LD, o None."""
    url, raiz, sub = args
    for intento in range(3):
        try:
            r = requests.get(url, headers=HEADERS, timeout=40)
        except Exception:
            time.sleep(2 + intento * 3)
            continue
        if r.status_code == 404:
            return None
        if r.status_code != 200:
            time.sleep(2 + intento * 3)
            continue
        r.encoding = "utf-8"
        for bloque in re.findall(r'<script[^>]*ld\+json[^>]*>(.*?)</script>', r.text, re.S):
            try:
                d = json.loads(bloque.strip())
            except Exception:
                continue
            if d.get("@type") != "Product":
                continue
            d["_raiz"], d["_sub"], d["_url"] = raiz, sub, url
            return d
        return None
    return None


def obtener():
    urls = _listar_urls()
    if not urls:
        raise RuntimeError("El sitemap de Diego no devolvio productos")

    fichas = []
    with ThreadPoolExecutor(max_workers=HILOS) as ex:
        for d in ex.map(_ficha, urls):
            if d:
                fichas.append(d)

    if len(fichas) < len(urls) * 0.5:
        raise RuntimeError(f"Solo se leyeron {len(fichas)} de {len(urls)} fichas")

    filas, publicados = [], 0
    for d in fichas:
        oferta = d.get("offers") or {}
        if isinstance(oferta, list):
            oferta = oferta[0] if oferta else {}

        # Diego publica en pesos. Si alguna ficha viniera en otra moneda,
        # se saltea para no publicar un precio equivocado.
        if (oferta.get("priceCurrency") or "UYU").upper() != "UYU":
            continue
        try:
            precio = float(oferta.get("price") or 0)
        except (TypeError, ValueError):
            continue
        if precio <= 0:
            continue
        precio = round(precio * (1 + MARGEN))

        title = (d.get("name") or "").strip()
        sku = (d.get("sku") or "").strip()
        if not title:
            continue

        madre, sub = clasificar(d["_raiz"], d["_sub"])
        sub = unificar(sub)
        h = _handle(sku, d["_url"])

        desc = (d.get("description") or "").strip()
        lineas = [l.strip() for l in desc.split("\n") if l.strip()]
        body = ("<ul>" + "".join(f"<li>{l}</li>" for l in lineas) + "</ul>"
                if lineas else title)

        imgs = d.get("image") or []
        if isinstance(imgs, str):
            imgs = [imgs]
        hay_stock = "InStock" in (oferta.get("availability") or "")

        fila = {c: "" for c in COLS}
        fila.update({
            "Handle": h, "Title": title, "Body HTML": body,
            "Vendor": "Diego", "Type": madre,
            "Tags": ", ".join([t for t in [sub] +
                               (["stock-verificado"] if hay_stock else []) if t]),
            "Published": "TRUE",
            "Option1 Name": "Título", "Option1 Value": "Default Title",
            "Variant SKU": sku, "Variant Price": f"{precio}.00",
            "Variant Inventory Qty": "10" if hay_stock else "0",
            "Variant Inventory Policy": "deny",
        })
        if imgs:
            fila["Image Src"] = imgs[0]
            fila["Image Position"] = "1"
        filas.append(fila)
        publicados += 1

        for pos, url in enumerate(imgs[1:9], 2):
            filas.append({**{c: "" for c in COLS}, "Handle": h,
                          "Image Src": url, "Image Position": str(pos)})

    return filas, publicados


if __name__ == "__main__":
    f, n = obtener()
    print(f"Diego: {n} productos, {len(f)} filas")
