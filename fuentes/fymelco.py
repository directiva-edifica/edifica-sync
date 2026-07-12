"""
Fuente: FYMELCO (WooCommerce Store API) - cocina de alta gama
Electrodomesticos empotrables, piletas, griferia, accesorios.
Precios en USD (sin margen). Todo el catalogo.
Marcas: TEKA, Tramontina, Köök (detectadas de la descripcion).
Piletas/fregaderos -> Hogar.
"""
import requests, re, html
from fuentes.unificar import unificar

NOMBRE = "fymelco"
API = "https://fymelco.com.uy/wp-json/wc/store/v1/products"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; EdificaBot/1.0)"}

def _limpiar(t):
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', html.unescape(t or ""))).strip()

def detectar_marca(nombre, short, desc, cats):
    t = (nombre + " " + short + " " + desc + " " + cats).lower()
    if "tramontina" in t: return "Tramontina"
    if "köök" in t or "kook" in t or "köok" in t: return "Köök"
    if "teka" in t: return "TEKA"
    if "quadrum" in t or "universo" in t or "stylo" in t: return "Köök"
    if "luna" in t or "lavínia" in t or "lavinia" in t: return "Tramontina"
    if re.search(r'\b(clc|hlb|jzc|hsb|izf|cnl|dfs|dsh|dbp|fih|izc|hcb)\b', t): return "TEKA"
    cl = cats.lower()
    if any(x in cl for x in ["anafe","horno","campana","lavavajilla","microonda","cafetera","calienta","vinoteca"]):
        return "TEKA"
    if any(x in t for x in ["fregadero","cubeta","pileta","bacha","mesada","cuba "]): return "Köök"
    return "TEKA"

def clasificar(nombre, cats):
    t = (nombre + " " + cats).lower()
    # Piletas de cocina y fregaderos -> Hogar
    if any(x in t for x in ["pileta","fregadero","cubeta","bacha","mesada","cuba de","desague","desagüe","triturador"]):
        return ["Hogar", "Piletas"]
    # Griferia -> Baño
    if "griferia" in t or "grifería" in t or "canilla" in t or "grifo" in t or "mezclador" in t:
        return ["Baño", "Grifería"]
    # Electro empotrable
    if "anafe" in t: return ["Electro", "Cocinas"]
    if "horno" in t: return ["Electro", "Cocinas"]
    if "microonda" in t: return ["Electro", "Cocinas"]
    if "campana" in t: return ["Electro", "Campanas"]
    if "heladera" in t or "refriger" in t: return ["Electro", "Heladeras"]
    if "lavavajilla" in t: return ["Electro", "Lavavajillas"]
    if "lavarropa" in t: return ["Electro", "Lavarropas"]
    if "cafetera" in t or "café" in t or "cafe" in t: return ["Electro", "Cafeteras"]
    if "vinoteca" in t: return ["Electro", "Heladeras"]
    if "calienta" in t: return ["Electro", "Otros"]
    # Accesorios de cocina / bazar
    if any(x in t for x in ["sarten","sartén","olla","cacerola","grill","set de cocina","cuchill","basurero","accesorio","desagü","desagu"]):
        return ["Accesorios", ""]
    return ["Electro", "Otros"]

def _handle(sku, slug):
    base = slug or sku
    return "fy-" + re.sub(r'[^a-z0-9]+', '-', base.lower()).strip('-')

COLS = ["Handle","Title","Body HTML","Vendor","Type","Tags","Published",
        "Option1 Name","Option1 Value","Variant SKU","Variant Price",
        "Variant Compare At Price","Variant Inventory Qty",
        "Variant Inventory Policy","Image Src","Image Position"]

def obtener():
    productos = []
    page = 1
    while True:
        r = requests.get(API, headers=HEADERS, params={"per_page":100,"page":page}, timeout=90)
        if r.status_code != 200: break
        d = r.json()
        if not d: break
        productos.extend(d); page += 1
        if page > 30: break
    if not productos:
        raise RuntimeError("Fymelco: API sin productos")

    filas = []
    publicados = 0
    for p in productos:
        title = _limpiar(p.get("name"))
        if title == "Test Plexo (QA Cygnus)":  # producto de prueba
            continue
        pr = p.get("prices", {})
        precio_raw = pr.get("price", "0")
        regular_raw = pr.get("regular_price", precio_raw)
        try:
            precio = f"{round(float(precio_raw),2)}"
            regular = f"{round(float(regular_raw),2)}"
        except Exception:
            continue
        if precio in ("0","0.0","1","1.0"): continue

        short = _limpiar(p.get("short_description"))
        desc_raw = p.get("description") or ""
        cats = ", ".join(c["name"] for c in p.get("categories", []))
        marca = detectar_marca(title, short, _limpiar(desc_raw), cats)
        madre, sub = clasificar(title, cats)
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
