"""
Fuente: ENKO (plataforma custom, se scrapea via sitemap + JSON-LD)
Tratamiento de madera, pisos, barnices, aceites, abrasivos, herramientas.
Precios en USD (sin margen). Todo el catalogo.
Marca = primera palabra del nombre. Construccion + Herramientas segun tipo.
"""
import requests, re, json, html
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor
from fuentes.unificar import unificar

NOMBRE = "enko"
SITEMAP = "https://enkotienda.com.uy/sitemap.xml"
HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                         "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"}

# Marcas conocidas de ENKO (solo estas se toman como marca)
MARCAS = {"bona","milesi","borma","enko","festool","mirka","osmo","liberon",
          "saicos","ciranova","blanchon","rubio","monocoat"}

def clasificar(nombre):
    n = nombre.lower()
    # Herramientas
    if any(x in n for x in ["rodillo","pincel","brocha","espatula","espátula","lija","lijadora",
                             "herramienta","soplete","pistola","cepillo","llana","taco","disco",
                             "abrasivo","malla","banda","rodete"]):
        # abrasivos y lijas pueden ir a herramientas
        if any(x in n for x in ["rodillo","pincel","brocha","espatula","espátula","herramienta",
                                 "soplete","pistola","cepillo","llana","taco"]):
            return ["Herramientas", ""]
        return ["Construcción", "Abrasivos"]
    # Todo el tratamiento de madera / pisos / quimicos -> Construccion
    if any(x in n for x in ["barniz","impregnante","sellador","aceite","cera","masilla",
                             "plastificante","adhesivo","blanqueador","catalizador","fondo",
                             "protector","tinte","laca","pintura","decapante","diluyente",
                             "limpiador","mantenimiento","piso","parquet","deck"]):
        return ["Construcción", "Pinturas"]
    return ["Construcción", "Otros"]

def marca_de(nombre):
    if not nombre: return "ENKO"
    primera = nombre.split()[0]
    if primera.lower() in MARCAS:
        return primera.capitalize() if primera.islower() else primera
    return "ENKO"  # si no arranca con marca conocida, marca generica

def _handle(handle_url, sku):
    base = handle_url or sku
    return "en-" + re.sub(r'[^a-z0-9]+', '-', base.lower()).strip('-')

COLS = ["Handle","Title","Body HTML","Vendor","Type","Tags","Published",
        "Option1 Name","Option1 Value","Variant SKU","Variant Price",
        "Variant Compare At Price","Variant Inventory Qty",
        "Variant Inventory Policy","Image Src","Image Position"]

def _urls_productos():
    r = requests.get(SITEMAP, headers=HEADERS, timeout=30)
    urls = re.findall(r'<loc>(https://enkotienda\.com\.uy/p/[^<]+)</loc>', r.text)
    vistos = {}
    for u in urls:
        m = re.search(r'/p/([a-z0-9-]+)/(\d+)/(\d+)', u)
        if m:
            vistos.setdefault(m.group(1), u)
    return vistos  # handle -> url

def _scrape(item):
    handle, url = item
    try:
        r = requests.get(url, headers=HEADERS, timeout=25)
        soup = BeautifulSoup(r.text, "html.parser")
        ld = soup.find("script", type="application/ld+json")
        if not ld: return None
        d = json.loads(ld.string)
        offer = d.get("offers", {})
        img = d.get("image", "")
        if isinstance(img, list): img = img[0] if img else ""
        return {
            "handle": handle,
            "name": html.unescape(d.get("name", "")),
            "desc": d.get("description", ""),
            "price": offer.get("price", ""),
            "sku": offer.get("sku", ""),
            "stock": "InStock" in str(offer.get("availability", "")),
            "img": img,
        }
    except Exception:
        return None

def obtener():
    urls = _urls_productos()
    if not urls:
        raise RuntimeError("ENKO: sitemap sin productos")
    productos = []
    with ThreadPoolExecutor(max_workers=8) as ex:
        for res in ex.map(_scrape, urls.items()):
            if res and res["price"]:
                productos.append(res)
    if not productos:
        raise RuntimeError("ENKO: no se pudo scrapear ningun producto")

    filas = []
    for p in productos:
        title = p["name"]
        madre, sub = clasificar(title)
        sub = unificar(sub)
        marca = marca_de(title)
        h = _handle(p["handle"], p["sku"])
        try:
            precio = f"{round(float(p['price']),2)}"
        except Exception:
            continue
        tg = ", ".join([t for t in [sub, marca] + (["stock-verificado"] if p["stock"] else []) if t])
        fila = {c: "" for c in COLS}
        fila.update({
            "Handle": h, "Title": title, "Body HTML": p["desc"] or title,
            "Vendor": marca, "Type": madre, "Tags": tg, "Published": "TRUE",
            "Option1 Name": "Título", "Option1 Value": "Default Title",
            "Variant SKU": p["sku"] or h, "Variant Price": precio,
            "Variant Compare At Price": "",
            "Variant Inventory Qty": "10" if p["stock"] else "0",
            "Variant Inventory Policy": "deny",
        })
        if p["img"]:
            fila["Image Src"] = p["img"]; fila["Image Position"] = "1"
        filas.append(fila)

    return filas, len(productos)

if __name__ == "__main__":
    filas, n = obtener()
    print(f"ENKO: {n} productos, {len(filas)} filas")
