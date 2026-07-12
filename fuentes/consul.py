"""
Fuente: CONSUL (distribuidor oficial, tienda Shopify - feed products.json)
Electrodomesticos Consul. Sin margen (precio tal cual UYU->USD dolar compra).
Heladeras/freezers/microondas/cerveceras -> Electro. Repuestos/filtros -> Accesorios.
"""
import requests, re, time, html
from fuentes.unificar import unificar

NOMBRE = "consul"
FEED = "https://www.consul.uy/products.json"
DOLAR_API = "https://uy.dolarapi.com/v1/cotizaciones"
# User-Agent de navegador para evitar el bloqueo 429
HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                         "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
           "Accept": "application/json"}

def _clean(t): return html.unescape(t or "").strip()

def dolar_compra():
    try:
        r = requests.get(DOLAR_API, timeout=15)
        for c in r.json():
            if c.get("moneda") == "USD":
                return float(c["compra"])
    except Exception: pass
    return 39.0

def clasificar(title, ptype):
    t = (title + " " + (ptype or "")).lower()
    # Repuestos y filtros van a Accesorios
    if any(x in t for x in ["filtro", "repuesto", "bandeja", "estante", "burlete", "manija"]):
        return ["Accesorios", "Repuestos"]
    # Electrodomesticos por tipo
    if "freezer" in t or "freezer" in t: return ["Electro", "Heladeras"]
    if "cervecera" in t: return ["Electro", "Heladeras"]
    if "heladera" in t or "refriger" in t: return ["Electro", "Heladeras"]
    if "microonda" in t: return ["Electro", "Cocinas"]
    if "cocina" in t or "anafe" in t or "horno" in t: return ["Electro", "Cocinas"]
    if "lavarropa" in t or "lavavajilla" in t: return ["Electro", "Lavarropas"]
    return ["Electro", "Otros"]

def _handle(hdl):
    return "cs-" + re.sub(r'[^a-z0-9]+', '-', hdl.lower()).strip('-')

def _traer_feed():
    """Trae todas las paginas del feed con reintento ante 429."""
    prods = []
    page = 1
    while True:
        for intento in range(2):
            r = requests.get(FEED, headers=HEADERS,
                             params={"limit": 250, "page": page}, timeout=30)
            if r.status_code == 200:
                break
            if r.status_code == 429:
                time.sleep(5 * (intento + 1))  # 5s, luego 10s. Maximo ~15s
                continue
            break
        if r.status_code != 200:
            if page == 1:
                raise RuntimeError(f"Consul: feed status {r.status_code}")
            break
        data = r.json().get("products", [])
        if not data:
            break
        prods.extend(data)
        page += 1
        if page > 30:
            break
        time.sleep(1)  # respetar el ritmo del servidor
    return prods

COLS = ["Handle","Title","Body HTML","Vendor","Type","Tags","Published",
        "Option1 Name","Option1 Value","Variant SKU","Variant Price",
        "Variant Compare At Price","Variant Inventory Qty",
        "Variant Inventory Policy","Image Src","Image Position"]

def obtener():
    dolar = dolar_compra()
    productos = _traer_feed()
    if not productos:
        raise RuntimeError("Consul: feed sin productos")

    def usd(p):
        try: return f"{round(float(p)/dolar, 2)}"
        except Exception: return ""

    filas = []
    for p in productos:
        title = _clean(p.get("title"))
        madre, sub = clasificar(title, p.get("product_type"))
        sub = unificar(sub)
        h = _handle(p.get("handle") or str(p.get("id")))
        body = p.get("body_html") or title
        variantes = p.get("variants", [])
        imgs = [im.get("src") for im in p.get("images", []) if im.get("src")]

        base = len(filas)
        primera = True
        for v in variantes:
            precio = usd(v.get("price"))
            compare = v.get("compare_at_price")
            hay_stock = v.get("available", False)
            fila = {c: "" for c in COLS}
            if primera:
                tg = ", ".join([t for t in [sub, "Consul"] + (["stock-verificado"] if hay_stock else []) if t])
                fila.update({"Handle": h, "Title": title, "Body HTML": body,
                             "Vendor": "Consul", "Type": madre, "Tags": tg,
                             "Published": "TRUE", "Option1 Name": "Modelo"})
                primera = False
            else:
                fila["Handle"] = h
            fila.update({
                "Option1 Value": _clean(v.get("title")) or "Único",
                "Variant SKU": v.get("sku") or str(v.get("id")),
                "Variant Price": precio,
                "Variant Compare At Price": usd(compare) if compare else "",
                "Variant Inventory Qty": "10" if hay_stock else "0",
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
    print(f"Consul: {n} productos, {len(filas)} filas")
