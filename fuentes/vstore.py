"""
Fuente: VSTORE (plataforma VTEX)
Solo publica productos de 1900 USD o mas. Sin margen (precio tal cual).
Marca real de VTEX. Categoria por la ruta de VTEX + palabra clave.
"""
import requests, re, html
from fuentes.unificar import unificar

NOMBRE = "vstore"
API = "https://www.vstore.com.uy/api/catalog_system/pub/products/search"
HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                         "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"}
MIN_USD = 1900

def _clean(t): return html.unescape(t or "").strip()

def clasificar(nombre, categoria):
    t = (nombre + " " + (categoria or "")).lower()
    if "tractor" in t or "corta cesped" in t or "corta césped" in t or "cortacesped" in t:
        return ["Jardín", "Cortadoras de Césped"]
    if "bicicleta" in t or "bike" in t: return ["Jardín", "Bicicletas"]
    if "smart tv" in t or "televisor" in t or " tv " in t or "qled" in t or "oled" in t: return ["Electro", "TV"]
    if "refrigerador" in t or "heladera" in t: return ["Electro", "Heladeras"]
    if "lavasecarropas" in t or "lavarropas" in t or "secarropas" in t: return ["Electro", "Lavarropas"]
    if "freidora" in t: return ["Electro", "Freidoras"]
    if "cafetera" in t: return ["Electro", "Cafeteras"]
    if "microonda" in t or "cocina" in t or "horno" in t: return ["Electro", "Cocinas"]
    if "radiador" in t or "calefac" in t or "aire" in t or "climatiz" in t: return ["Electro", "Climatización"]
    if "taladro" in t or "herramienta" in t or "amoladora" in t: return ["Herramientas", ""]
    if "aspiradora" in t: return ["Electro", "Aspiradoras"]
    if "audio" in t or "parlante" in t or "barra de sonido" in t: return ["Electro", "Audio"]
    return ["Electro", "Otros"]

def _handle(sku, link):
    base = link or sku
    return "vs-" + re.sub(r'[^a-z0-9]+', '-', str(base).lower()).strip('-')

COLS = ["Handle","Title","Body HTML","Vendor","Type","Tags","Published",
        "Option1 Name","Option1 Value","Variant SKU","Variant Price",
        "Variant Compare At Price","Variant Inventory Qty",
        "Variant Inventory Policy","Image Src","Image Position"]

def obtener():
    productos = []
    frm = 0
    while frm < 3000:
        r = requests.get(API, headers=HEADERS,
                         params={"_from": frm, "_to": frm+49}, timeout=60)
        if r.status_code not in (200, 206): break
        d = r.json()
        if not d: break
        productos.extend(d)
        frm += 50
        if len(d) < 50: break
    if not productos:
        raise RuntimeError("VStore: API sin productos")

    filas = []
    publicados = 0
    for p in productos:
        items = p.get("items", [])
        if not items: continue
        item = items[0]
        try:
            offer = item["sellers"][0]["commertialOffer"]
            precio = offer.get("Price", 0)
        except (KeyError, IndexError):
            continue
        # FILTRO 1900+ USD
        if not precio or precio < MIN_USD: continue

        title = _clean(p.get("productName"))
        marca = _clean(p.get("brand")) or "VStore"
        cat = p.get("categories", [""])[0] if p.get("categories") else ""
        madre, sub = clasificar(title, cat)
        sub = unificar(sub)
        link = p.get("linkText", "")
        h = _handle(p.get("productId"), link)
        body = _clean(p.get("description")) or title

        # precio de lista (tachado) si hay
        lista = offer.get("ListPrice", precio)
        hay_stock = offer.get("AvailableQuantity", 0) > 0
        regular = f"{round(lista,2)}" if lista and lista > precio else ""

        # imagenes
        imgs = []
        for it in items:
            for img in it.get("images", []):
                u = img.get("imageUrl")
                if u and u not in imgs: imgs.append(u)

        tg = ", ".join([t for t in [sub, marca] + (["stock-verificado"] if hay_stock else []) if t])
        fila = {c: "" for c in COLS}
        fila.update({
            "Handle": h, "Title": title, "Body HTML": body, "Vendor": marca,
            "Type": madre, "Tags": tg, "Published": "TRUE",
            "Option1 Name": "Título", "Option1 Value": "Default Title",
            "Variant SKU": str(item.get("itemId") or p.get("productId")),
            "Variant Price": f"{round(precio,2)}",
            "Variant Compare At Price": regular,
            "Variant Inventory Qty": "10" if hay_stock else "0",
            "Variant Inventory Policy": "deny",
        })
        if imgs: fila["Image Src"] = imgs[0]; fila["Image Position"] = "1"
        filas.append(fila); publicados += 1
        for pos, url in enumerate(imgs[1:], 2):
            filas.append({**{c: "" for c in COLS}, "Handle": h,
                          "Image Src": url, "Image Position": str(pos)})

    return filas, publicados

if __name__ == "__main__":
    filas, n = obtener()
    print(f"VStore: {n} productos publicados (1900+ USD), {len(filas)} filas")
