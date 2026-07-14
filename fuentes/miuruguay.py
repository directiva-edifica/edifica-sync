"""
Fuente: MIURUGUAY (Xiaomi Uruguay, WooCommerce Store API)
Solo publica productos de 400 USD o mas. Sin margen (precio tal cual).
UYU->USD dolar compra. Categoria por palabra clave del nombre. Marca Xiaomi/Redmi/POCO/Mijia.
"""
import requests, re, html
from fuentes.unificar import unificar

NOMBRE = "miuruguay"
API = "https://miuruguay.com.uy/wp-json/wc/store/v1/products"
DOLAR_API = "https://uy.dolarapi.com/v1/cotizaciones"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; EdificaBot/1.0)"}
MIN_USD = 400  # solo se publican productos de 400 USD o mas

def _clean(t): return html.unescape(t or "").strip()

def limpiar_desc(desc):
    """Quita shortcodes de WPBakery [vc_row] etc que Shopify no entiende."""
    if not desc: return ""
    import re as _re
    d = _re.sub(r'\[/?vc_[^\]]*\]', '', desc)      # shortcodes vc_*
    d = _re.sub(r'\[/?[a-z_]+[^\]]*\]', '', d)       # otros shortcodes
    d = _re.sub(r'<p>\s*</p>', '', d)                  # parrafos vacios
    d = _re.sub(r'\n\s*\n\s*\n+', '\n\n', d)      # saltos multiples
    return d.strip()

def dolar_compra():
    try:
        r = requests.get(DOLAR_API, headers=HEADERS, timeout=15)
        for c in r.json():
            if c.get("moneda") == "USD":
                return float(c["compra"])
    except Exception: pass
    return 39.0

def clasificar(nombre):
    n = nombre.lower()
    if "scooter" in n or "patineta" in n: return ["Accesorios", "Movilidad"]
    if "tv " in n or " tv" in n or "television" in n: return ["Electro", "TV"]
    if any(x in n for x in ["notebook","laptop","monitor","tablet","pad "]): return ["Electro", "Tecnología"]
    if any(x in n for x in ["redmi note","redmi a","redmi 1","poco","xiaomi 1","celular","smartphone"]): return ["Electro", "Tecnología"]
    if "freidora" in n or "air fryer" in n: return ["Electro", "Freidoras"]
    if "licuadora" in n or "blender" in n: return ["Electro", "Licuadoras"]
    if "aspiradora" in n or "vacuum" in n: return ["Electro", "Aspiradoras"]
    if "lavasecarropas" in n or "lavarropas" in n or "washer" in n: return ["Electro", "Lavarropas"]
    if "heladera" in n or "refrigerador" in n: return ["Electro", "Heladeras"]
    if any(x in n for x in ["aire acondicionado","estufa","calefactor","ventilador"]): return ["Electro", "Climatización"]
    if any(x in n for x in ["auricular","buds","parlante","openwear"]): return ["Electro", "Audio"]
    if "reloj" in n or "watch" in n or "band" in n: return ["Electro", "Tecnología"]
    if any(x in n for x in ["lampara","plafon","luz","light"]): return ["Iluminación", "Focos LED"]
    if any(x in n for x in ["compresor","hidrolavadora","destornillador","medidor"]): return ["Herramientas", ""]
    if "valija" in n or "mochila" in n or "equipaje" in n: return ["Accesorios", ""]
    return ["Electro", "Otros"]

def marca(nombre):
    n = nombre.lower()
    if "redmi" in n: return "Redmi"
    if "poco" in n: return "POCO"
    if "mijia" in n: return "Mijia"
    return "Xiaomi"

def _handle(sku, slug):
    base = slug or sku
    return "mu-" + re.sub(r'[^a-z0-9]+', '-', base.lower()).strip('-')

COLS = ["Handle","Title","Body HTML","Vendor","Type","Tags","Published",
        "Option1 Name","Option1 Value","Variant SKU","Variant Price",
        "Variant Compare At Price","Variant Inventory Qty",
        "Variant Inventory Policy","Image Src","Image Position"]

def obtener():
    dolar = dolar_compra()
    productos = []
    page = 1
    while True:
        r = requests.get(API, headers=HEADERS, params={"per_page":100,"page":page}, timeout=90)
        if r.status_code != 200: break
        data = r.json()
        if not data: break
        productos.extend(data); page += 1
        if page > 50: break
    if not productos:
        raise RuntimeError("MiUruguay: API sin productos")

    filas = []
    publicados = 0
    for p in productos:
        pr = p.get("prices", {})
        precio_raw = pr.get("price", "0")
        regular_raw = pr.get("regular_price", precio_raw)
        # excluir placeholders sin precio real
        if precio_raw in ("99999", "0", "", None): continue
        try:
            precio_usd = float(precio_raw) / dolar
        except Exception:
            continue
        # FILTRO: solo 400 USD o mas
        if precio_usd < MIN_USD: continue

        sku = str(p.get("sku") or p.get("id"))
        title = _clean(p.get("name"))
        madre, sub = clasificar(title)
        sub = unificar(sub)
        m = marca(title)
        body = limpiar_desc(p.get("description") or "")
        h = _handle(sku, p.get("slug"))
        oferta = p.get("on_sale", False)
        hay_stock = p.get("is_in_stock")

        precio = f"{round(precio_usd,2)}"
        try: regular = f"{round(float(regular_raw)/dolar,2)}"
        except Exception: regular = ""

        imgs = [im.get("src") for im in p.get("images", []) if im.get("src")]
        tg = ", ".join([t for t in [sub, m] + (["stock-verificado"] if hay_stock else []) if t])
        fila = {c:"" for c in COLS}
        fila.update({
            "Handle":h, "Title":title, "Body HTML":body, "Vendor":m, "Type":madre,
            "Tags":tg, "Published":"TRUE", "Option1 Name":"Título", "Option1 Value":"Default Title",
            "Variant SKU":sku, "Variant Price":precio,
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
    print(f"MiUruguay: {n} productos publicados (400+ USD), {len(filas)} filas")
