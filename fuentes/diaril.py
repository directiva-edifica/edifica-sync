"""
Fuente: DIARIL (plataforma Fenicio, comercio 'diaruy')
Marcas: Bosch, Futura, Ufesa, Siam, Bristol. Precios en USD.
Tag stock-verificado si el feed dice IN_STOCK.

El feed trae precio, stock, marca y categoria, pero NO trae imagenes
ni descripcion real (repite el nombre). Por eso se scrapea la ficha de
cada producto para sacar la descripcion (div.text) y las fotos del CDN.
"""
import requests, re, json
import xml.etree.ElementTree as ET
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from bs4 import BeautifulSoup
from fuentes.unificar import unificar

NOMBRE = "diaril"
FEED_URL = "https://www.diaril.com.uy/feeds/productos/diaruy/fenicio"
HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                         "AppleWebKit/537.36 (KHTML, like Gecko) "
                         "Chrome/120.0.0.0 Safari/537.36"}
NS = {"a": "http://www.w3.org/2005/Atom"}

MAPEO = {
    "Cocina y electro > Cocción > Cocinas": ["Electro", "Cocinas"],
    "Cocina y electro > Cocción > Anafes": ["Electro", "Cocinas"],
    "Cocina y electro > Cocción > Hornos empotrables": ["Electro", "Cocinas"],
    "Cocina y electro > Cocción > Hornos microondas": ["Electro", "Cocinas"],
    "Cocina y electro > Cocción > Mini-hornos": ["Electro", "Cocinas"],
    "Cocina y electro > Cocción > Mini‑hornos": ["Electro", "Cocinas"],
    "Cocina y electro > Cocción > Freidoras de aire": ["Electro", "Freidoras"],
    "Cocina y electro > Cocción > Campanas": ["Electro", "Campanas"],
    "Cocina y electro > Desayuno > Cafeteras": ["Electro", "Cafeteras"],
    "Cocina y electro > Desayuno > Hervidores de agua": ["Electro", "Jarras"],
    "Cocina y electro > Desayuno > Tostadoras": ["Electro", "Tostadoras"],
    "Cocina y electro > Desayuno > Sandwicheras": ["Electro", "Sandwicheras"],
    "Cocina y electro > Desayuno > Exprimidores y jugueras": ["Electro", "Exprimidores"],
    "Cocina y electro > Preparación de alimentos > Mixers": ["Electro", "Licuadoras"],
    "Cocina y electro > Preparación de alimentos > Licuadoras": ["Electro", "Licuadoras"],
    "Cocina y electro > Preparación de alimentos > Batidoras de mano": ["Electro", "Batidoras"],
    "Cocina y electro > Preparación de alimentos > Robots y procesadores": ["Electro", "Batidoras"],
    "Cocina y electro > Preparación de alimentos > Planchas & grills": ["Electro", "Sandwicheras"],
    "Cocina y electro > Preparación de alimentos > Balanzas de cocina": ["Electro", "Otros"],
    "Cocina y electro > Preparación de alimentos > Otros electros": ["Electro", "Otros"],
    "Cocina y electro > Preparación de alimentos > Accesorios": ["Accesorios", ""],
    "Refrigeración > Heladeras": ["Electro", "Heladeras"],
    "Refrigeración > Freezers": ["Electro", "Heladeras"],
    "Refrigeración > Frigobares y cavas": ["Electro", "Heladeras"],
    "Lavado y limpieza > Lavavajillas": ["Electro", "Lavavajillas"],
    "Lavado y limpieza > Lavavajillas > De libre instalación": ["Electro", "Lavavajillas"],
    "Lavado y limpieza > Lavavajillas > Integrables y panelables": ["Electro", "Lavavajillas"],
    "Lavado y limpieza > Lavarropas y secarropas > Lavarropas": ["Electro", "Lavarropas"],
    "Lavado y limpieza > Lavarropas y secarropas > Lavasecarropas": ["Electro", "Lavarropas"],
    "Lavado y limpieza > Lavarropas y secarropas > Secarropas": ["Electro", "Lavarropas"],
    "Lavado y limpieza > Aspiradoras": ["Electro", "Aspiradoras"],
    "Lavado y limpieza > Planchado y cuidado de ropa > Planchas a vapor": ["Electro", "Planchas"],
    "Lavado y limpieza > Planchado y cuidado de ropa > Centros de planchado": ["Electro", "Planchas"],
    "Climatización > Calefacción": ["Electro", "Climatización"],
    "Climatización > Ventiladores": ["Electro", "Climatización"],
    "Climatización > Aires acondicionados": ["Electro", "Climatización"],
}


def clasificar(cat):
    if cat in MAPEO:
        return MAPEO[cat]
    c = (cat or "").lower()
    if "aspiradora" in c: return ["Electro", "Aspiradoras"]
    if "lavavajilla" in c: return ["Electro", "Lavavajillas"]
    if any(x in c for x in ["lavarropa", "secarropa"]): return ["Electro", "Lavarropas"]
    if "campana" in c: return ["Electro", "Campanas"]
    if any(x in c for x in ["heladera", "freezer", "frigobar", "refrigera"]):
        return ["Electro", "Heladeras"]
    if any(x in c for x in ["cocina", "anafe", "horno", "microonda"]): return ["Electro", "Cocinas"]
    if "freidora" in c: return ["Electro", "Freidoras"]
    if "cafetera" in c: return ["Electro", "Cafeteras"]
    if "tostadora" in c: return ["Electro", "Tostadoras"]
    if "plancha" in c: return ["Electro", "Planchas"]
    if any(x in c for x in ["licuadora", "mixer"]): return ["Electro", "Licuadoras"]
    if "batidora" in c or "procesador" in c: return ["Electro", "Batidoras"]
    if "hervidor" in c: return ["Electro", "Jarras"]
    if any(x in c for x in ["climatiz", "calefacc", "ventilador", "aire acondicionado"]):
        return ["Electro", "Climatización"]
    if "accesorio" in c: return ["Accesorios", ""]
    return ["Electro", "Otros"]


def _g(item, tag):
    el = item.find("a:" + tag, NS)
    return (el.text or "").strip() if el is not None and el.text else ""


def _precio(txt):
    """El feed trae '749.00 USD' -> '749.00'."""
    return txt.split()[0] if txt else ""


def _handle(code):
    return "dr-" + re.sub(r'[^a-z0-9]+', '-', code.lower()).strip('-')


def _ficha(url):
    """Saca descripcion (div.text) e imagenes del CDN de la ficha del producto."""
    desc, imgs = "", []
    try:
        r = requests.get(url, headers=HEADERS, timeout=30)
        r.encoding = "utf-8"
        if r.status_code != 200:
            return desc, imgs
        soup = BeautifulSoup(r.text, "html.parser")
        t = soup.find("div", class_="text")
        if t:
            desc = t.decode_contents().strip()
        # imagenes del producto: el codigo va en la ruta del CDN
        cod = re.search(r'_([A-Z0-9\-]+)_[A-Z0-9\-]+$', url)
        patron = cod.group(1) if cod else None
        vistas = set()
        for u in re.findall(r'//f\.fcdn\.app/imgs/[^"\' )]+\.(?:jpg|jpeg|png|webp)', r.text):
            if patron and f"/{patron}_" not in u:
                continue
            # quedarse con la version grande y sin duplicar por tamano
            clave = re.sub(r'/\d+[x-]\d+/', '/', u)
            if clave in vistas:
                continue
            vistas.add(clave)
            imgs.append("https:" + u if u.startswith("//") else u)
    except Exception:
        pass
    return desc, imgs[:8]


COLS = ["Handle", "Title", "Body HTML", "Vendor", "Type", "Tags", "Published",
        "Option1 Name", "Option1 Value", "Variant SKU", "Variant Price",
        "Variant Compare At Price", "Variant Inventory Qty",
        "Variant Inventory Policy", "Image Src", "Image Position"]


def obtener():
    resp = requests.get(FEED_URL, headers=HEADERS, timeout=90)
    resp.encoding = "utf-8"
    root = ET.fromstring(resp.text)

    productos = OrderedDict()
    for item in root.findall(".//a:item", NS):
        code = _g(item, "productCode")
        if code:
            productos.setdefault(code, []).append(item)
    if not productos:
        raise RuntimeError("Feed de Diaril vacio")

    links = {p: _g(v[0], "link") for p, v in productos.items()}
    fichas = {}
    with ThreadPoolExecutor(max_workers=8) as ex:
        for p, d in ex.map(lambda kv: (kv[0], _ficha(kv[1])), links.items()):
            fichas[p] = d

    filas = []
    for pcode, variantes in productos.items():
        v0 = variantes[0]
        marca = _g(v0, "brand") or "Diaril"
        madre, sub = clasificar(_g(v0, "productType"))
        sub = unificar(sub)
        title = _g(v0, "productName") or _g(v0, "name")
        h = _handle(pcode)

        desc, imgs = fichas.get(pcode, ("", []))
        if desc:
            lineas = [l.strip() for l in
                      BeautifulSoup(desc, "html.parser").get_text("\n").split("\n") if l.strip()]
            body = "<ul>" + "".join(f"<li>{l}</li>" for l in lineas) + "</ul>" if lineas else title
        else:
            body = title

        base = len(filas)
        for i, v in enumerate(variantes):
            oferta = _g(v, "sale") == "YES"
            hay_stock = _g(v, "availability") == "IN_STOCK"
            fila = {c: "" for c in COLS}
            if i == 0:
                tg = ", ".join([t for t in [sub, marca] +
                                (["stock-verificado"] if hay_stock else []) if t])
                fila.update({"Handle": h, "Title": title, "Body HTML": body,
                             "Vendor": marca, "Type": madre, "Tags": tg,
                             "Published": "TRUE", "Option1 Name": "Color"})
            else:
                fila["Handle"] = h
            fila.update({"Option1 Value": _g(v, "variantName") or "Único",
                         "Variant SKU": _g(v, "sku"),
                         "Variant Price": _precio(_g(v, "salePrice")) or _precio(_g(v, "price")),
                         "Variant Compare At Price": _precio(_g(v, "listPrice")) if oferta else "",
                         "Variant Inventory Qty": "10" if hay_stock else "0",
                         "Variant Inventory Policy": "deny"})
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
    f, n = obtener()
    print(f"Diaril: {n} productos, {len(f)} filas")
