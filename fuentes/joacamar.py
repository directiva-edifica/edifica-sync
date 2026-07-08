"""
Fuente: JOACAMAR (plataforma Fenicio, codigo de comercio 'joacuy')
Lee el feed oficial, clasifica en las 8 categorias de Edifica,
baja las descripciones reales de cada ficha y devuelve filas Matrixify.
"""

import requests, re
import xml.etree.ElementTree as ET
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from bs4 import BeautifulSoup

NOMBRE = "joacamar"
FEED_URL = "https://joacamar.com.uy/feeds/productos/joacuy/fenicio"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; EdificaBot/1.0)"}
NS = {"a": "http://www.w3.org/2005/Atom"}

MAPEO = {
    "Línea blanca > Lavarropas": ["Electro", "Lavarropas"],
    "Línea blanca > Refrigeración": ["Electro", "Heladeras"],
    "Línea blanca > Refrigeración > Heladeras": ["Electro", "Heladeras"],
    "Línea blanca > Refrigeración > Frigobares y cavas": ["Electro", "Heladeras"],
    "Línea blanca > Refrigeración > Freezers": ["Electro", "Heladeras"],
    "Línea blanca > Refrigeración > Vitrinas": ["Electro", "Heladeras"],
    "Línea blanca > Campanas": ["Electro", "Campanas"],
    "Línea blanca > Anafes": ["Electro", "Cocinas"],
    "Línea blanca > Hornos y cocinas": ["Electro", "Cocinas"],
    "Línea blanca > Lavavajillas": ["Electro", "Lavavajillas"],
    "Línea blanca > Calefones": ["Electro", "Calefones"],
    "Pequeños electrodomésticos > Freidoras sin aceite": ["Electro", "Freidoras"],
    "Pequeños electrodomésticos > Microondas y hornos eléctricos": ["Electro", "Cocinas"],
    "Pequeños electrodomésticos > Batidoras": ["Electro", "Batidoras"],
    "Pequeños electrodomésticos > Licuadoras y mixers": ["Electro", "Licuadoras"],
    "Pequeños electrodomésticos > Exprimidores y jugueras": ["Electro", "Exprimidores"],
    "Pequeños electrodomésticos > Cafeteras": ["Electro", "Cafeteras"],
    "Pequeños electrodomésticos > Jarras eléctricas": ["Electro", "Jarras"],
    "Pequeños electrodomésticos > Sandwicheras y grills": ["Electro", "Sandwicheras"],
    "Pequeños electrodomésticos > Planchas": ["Electro", "Planchas"],
    "Pequeños electrodomésticos > Aspiradoras": ["Electro", "Aspiradoras"],
    "Pequeños electrodomésticos > Otros electrodomésticos": ["Electro", "Otros"],
    "Aires acondicionados": ["Electro", "Climatización"],
    "Calefacción": ["Electro", "Climatización"],
    "Ventilación": ["Electro", "Climatización"],
    "Smartwatches": ["Electro", "Tecnología"],
    "Cámaras de seguridad": ["Electro", "Tecnología"],
    "Más tecnología": ["Electro", "Tecnología"],
    "Escritorio": ["Electro", "Tecnología"],
    "Afeitadoras y cortadoras": ["Electro", "Cuidado Personal"],
    "Planchitas y rizadores": ["Electro", "Cuidado Personal"],
    "Secadores y cepillos": ["Electro", "Cuidado Personal"],
    "Otros cuidado personal": ["Electro", "Cuidado Personal"],
    "Hogar": ["Herramientas", ""],
    "Jardín": ["Jardín", ""],
    "Jardín > Cortadoras de Cesped": ["Jardín", "Cortadoras de Césped"],
    "Accesorios": ["Accesorios", ""],
    "Otros": ["Accesorios", ""],
    "Accesorios para auto": ["Accesorios", "Auto"],
    "Audio e imagen": ["Accesorios", "Auto"],
}


def clasificar(cat, marca):
    if marca.upper() == "MAXWHEEL":
        return ["Accesorios", "Movilidad"]
    if cat in MAPEO:
        return MAPEO[cat]
    c = cat.lower()
    if "televisor" in c or "soporte" in c or "pantalla" in c:
        return ["Electro", "TV"]
    if any(x in c for x in ["audio", "auricular", "parlante", "radio", "barras"]):
        return ["Electro", "Audio"]
    if "car audio" in c:
        return ["Accesorios", "Auto"]
    return ["Electro", "Otros"]


def _g(item, tag):
    el = item.find("a:" + tag, NS)
    return (el.text or "").strip() if el is not None and el.text else ""


def _precio(txt):
    return txt.split()[0] if txt else ""


def _handle(code):
    return "jm-" + re.sub(r'[^a-z0-9]+', '-', code.lower()).strip('-')


def _get_descripcion(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=30)
        r.encoding = "utf-8"
        soup = BeautifulSoup(r.text, "html.parser")
        bloque = soup.find("div", class_="blkDetalle")
        if bloque:
            t = bloque.find("div", class_="text")
            if t:
                return t.decode_contents().strip()
    except Exception:
        pass
    return ""


COLS = ["Handle", "Title", "Body HTML", "Vendor", "Type", "Tags", "Published",
        "Option1 Name", "Option1 Value", "Variant SKU", "Variant Price",
        "Variant Compare At Price", "Variant Inventory Qty",
        "Variant Inventory Policy", "Image Src", "Image Position"]


def obtener():
    resp = requests.get(FEED_URL, timeout=60)
    resp.encoding = "utf-8"
    root = ET.fromstring(resp.text)

    productos = OrderedDict()
    for item in root.findall(".//a:item", NS):
        productos.setdefault(_g(item, "productCode"), []).append(item)

    if not productos:
        raise RuntimeError("Feed de Joacamar vacio")

    links = {p: _g(v[0], "link") for p, v in productos.items()}
    descripciones = {}
    with ThreadPoolExecutor(max_workers=8) as ex:
        for p, d in ex.map(lambda kv: (kv[0], _get_descripcion(kv[1])), links.items()):
            descripciones[p] = d

    filas = []
    for pcode, variantes in productos.items():
        v0 = variantes[0]
        madre, sub = clasificar(_g(v0, "productType"), _g(v0, "brand"))
        tags = ", ".join([t for t in [sub, _g(v0, "brand")] if t])
        title = _g(v0, "productName") or _g(v0, "name")
        h = _handle(pcode)

        desc = descripciones.get(pcode, "")
        if desc:
            lineas = [l.strip() for l in
                      BeautifulSoup(desc, "html.parser").get_text("\n").split("\n")
                      if l.strip()]
            body = "<ul>" + "".join(f"<li>{l}</li>" for l in lineas) + "</ul>"
        else:
            body = title

        imgs = []
        for v in variantes:
            for l in v.findall("a:images/a:link", NS):
                if l.text and l.text.strip() not in imgs:
                    imgs.append(l.text.strip())

        base = len(filas)
        for i, v in enumerate(variantes):
            oferta = _g(v, "sale") == "YES"
            fila = {c: "" for c in COLS}
            if i == 0:
                fila.update({"Handle": h, "Title": title, "Body HTML": body,
                             "Vendor": _g(v0, "brand"), "Type": madre, "Tags": tags,
                             "Published": "TRUE", "Option1 Name": "Color"})
            else:
                fila["Handle"] = h
            fila.update({
                "Option1 Value": _g(v, "variantName") or "Único",
                "Variant SKU": _g(v, "sku"),
                "Variant Price": _precio(_g(v, "salePrice")),
                "Variant Compare At Price": _precio(_g(v, "listPrice")) if oferta else "",
                "Variant Inventory Qty": "10" if _g(v, "availability") == "IN_STOCK" else "0",
                "Variant Inventory Policy": "deny",
            })
            filas.append(fila)

        for pos, url in enumerate(imgs, 1):
            if pos == 1:
                filas[base]["Image Src"] = url
                filas[base]["Image Position"] = "1"
            else:
                filas.append({**{c: "" for c in COLS}, "Handle": h,
                              "Image Src": url, "Image Position": str(pos)})

    return filas, len(productos)


if __name__ == "__main__":
    filas, n = obtener()
    print(f"Joacamar: {n} productos, {len(filas)} filas")
