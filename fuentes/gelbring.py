"""
Fuente: GELBRING (WooCommerce Store API) - Enxuta / Queen
La web NO publica precios: se toman de las listas oficiales que estan
en la carpeta listas/ (PDF o XLSX). Se cruza por Codigo del Articulo,
que aparece en el nombre del producto web.
Precio usado: columna "PVP Min Sugerido" (en USD). Sin margen.
Los productos sin precio en las listas NO se publican.
Esta fuente NO lleva el tag stock-verificado.
"""
import requests, re, html, os, glob, time
from collections import defaultdict
from fuentes.unificar import unificar

NOMBRE = "gelbring"
API = "https://gelbring.com.uy/wp-json/wc/store/v1/products"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "es-UY,es;q=0.9",
    "Referer": "https://gelbring.com.uy/",
}
LISTAS_DIR = "listas"

# ---------- LECTURA DE LISTAS ----------

def _num(txt):
    if txt is None: return None
    s = str(txt).strip().replace(".", "").replace(",", ".")
    try: return float(s)
    except Exception: return None

def _leer_pdf(path):
    """PDF Gelbring: los digitos vienen separados, se lee por posicion de columna."""
    precios = {}
    try:
        import pdfplumber
    except ImportError:
        return precios
    with pdfplumber.open(path) as pdf:
        for pg in pdf.pages:
            filas = defaultdict(list)
            for w in pg.extract_words():
                filas[round(w["top"])].append(w)
            tops = sorted(filas.keys())
            grupos, actual = [], []
            for t in tops:
                if actual and t - actual[-1] <= 2: actual.append(t)
                else:
                    if actual: grupos.append(actual)
                    actual = [t]
            if actual: grupos.append(actual)
            for g in grupos:
                palabras = []
                for t in g: palabras.extend(filas[t])
                palabras.sort(key=lambda w: w["x0"])
                ean = next((w["text"] for w in palabras if re.fullmatch(r'\d{13}', w["text"])), None)
                if not ean: continue
                cod = next((w["text"] for w in palabras if 135 <= w["x0"] <= 222 and w["text"] != ean), None)
                pvp = "".join(w["text"] for w in palabras if w["x0"] >= 722)
                pvp = pvp.replace(".", "").replace(",", ".")
                if cod and re.fullmatch(r'[\d\.]+', pvp or ""):
                    try: precios[cod] = float(pvp)
                    except Exception: pass
    return precios

def _leer_xlsx(path):
    """XLSX Gelbring: col C = Codigo, col H = PVP Min Sugerido."""
    precios = {}
    try:
        import openpyxl
    except ImportError:
        return precios
    wb = openpyxl.load_workbook(path, data_only=True)
    for ws in wb.worksheets:
        for row in ws.iter_rows(values_only=True):
            if len(row) < 8: continue
            cod, pvp = row[2], row[7]
            if not cod or not isinstance(cod, str): continue
            if cod.strip().lower().startswith("código"): continue
            v = _num(pvp) if not isinstance(pvp, (int, float)) else float(pvp)
            if v and v > 0:
                precios[cod.strip()] = round(v, 2)
    return precios

def cargar_listas():
    """Lee TODOS los archivos de listas/ (pdf y xlsx) -> dict codigo: precio."""
    precios = {}
    if not os.path.isdir(LISTAS_DIR):
        return precios
    for path in sorted(glob.glob(os.path.join(LISTAS_DIR, "*"))):
        ext = path.lower().rsplit(".", 1)[-1]
        if ext == "pdf": nuevos = _leer_pdf(path)
        elif ext in ("xlsx", "xlsm"): nuevos = _leer_xlsx(path)
        else: continue
        for c, p in nuevos.items():
            precios.setdefault(c, p)
        print(f"  lista {os.path.basename(path)}: {len(nuevos)} codigos")
    return precios

# ---------- CLASIFICACION ----------

def clasificar(nombre, cats):
    t = (nombre + " " + cats).lower()
    if any(x in t for x in ["cortadora de c", "cortacesped", "motosierra", "bordeadora",
                            "desmalezadora", "sopladora", "cortacerco", "hidrolavadora",
                            "linea jard", "línea jard"]):
        return ["Jardín", ""]
    if any(x in t for x in ["soporte", "articulado para pared", "basculante"]):
        return ["Accesorios", ""]
    if any(x in t for x in ["monitor", "gamer"]): return ["Electro", "Tecnología"]
    if any(x in t for x in ["smart tv", "televisor", "led ", "qled", "pulgadas"]):
        return ["Electro", "TV"]
    if any(x in t for x in ["barra de sonido", "parlante", "sonido", "audio", "home theater"]):
        return ["Electro", "Audio"]
    if any(x in t for x in ["secador de pelo", "planchita", "depiladora", "afeitadora",
                            "cortapelo", "cepillo secador", "beauty"]):
        return ["Electro", "Cuidado Personal"]
    if any(x in t for x in ["refrigerador", "heladera", "frigobar", "freezer", "vitrina",
                            "enfriadora de vino", "enfriador de bebidas", "fabricadora de hielo",
                            "side by side", "french door", "multidoor", "combi"]):
        return ["Electro", "Heladeras"]
    if "lavavajilla" in t: return ["Electro", "Lavavajillas"]
    if any(x in t for x in ["lavarropa", "lavasecarropa", "secarropa", "centrifugadora",
                            "torre de lavado"]):
        return ["Electro", "Lavarropas"]
    if "campana" in t: return ["Electro", "Campanas"]
    if any(x in t for x in ["cocina", "anafe", "horno", "microonda"]):
        return ["Electro", "Cocinas"]
    if any(x in t for x in ["termotanque", "calentador a gas", "calefon"]):
        return ["Electro", "Calefones"]
    if any(x in t for x in ["aire acondicionado", "caloventilador", "radiador", "panel convector",
                            "estufa", "calefactor", "ventilador", "turbocirculador",
                            "deshumidificador", "purificador de aire", "enfriador de aire",
                            "climatiz", "calienta cama", "calienta pies", "manta t"]):
        return ["Electro", "Climatización"]
    if "aspiradora" in t or "trapeadora" in t: return ["Electro", "Aspiradoras"]
    if "freidora" in t: return ["Electro", "Freidoras"]
    if "cafetera" in t: return ["Electro", "Cafeteras"]
    if "licuadora" in t or "mixer" in t: return ["Electro", "Licuadoras"]
    if "batidora" in t: return ["Electro", "Batidoras"]
    if "sandwichera" in t: return ["Electro", "Sandwicheras"]
    if "tostadora" in t: return ["Electro", "Tostadoras"]
    if "plancha" in t: return ["Electro", "Planchas"]
    if "jarra" in t: return ["Electro", "Jarras"]
    if "juguera" in t or "exprimidor" in t: return ["Electro", "Exprimidores"]
    return ["Electro", "Otros"]

def marca_de(nombre):
    return "Queen" if "queen" in nombre.lower() else "Enxuta"

def _norm(s): return re.sub(r'[^A-Z0-9]', '', (s or "").upper())

def _handle(sku, slug):
    base = slug or sku
    return "gb-" + re.sub(r'[^a-z0-9]+', '-', base.lower()).strip('-')

COLS = ["Handle","Title","Body HTML","Vendor","Type","Tags","Published",
        "Option1 Name","Option1 Value","Variant SKU","Variant Price",
        "Variant Compare At Price","Variant Inventory Qty",
        "Variant Inventory Policy","Image Src","Image Position"]

def _traer_web():
    """Intenta la API. Gelbring suele bloquear IPs de servidor (403)."""
    productos = []
    page = 1
    try:
        while True:
            r = requests.get(API, headers=HEADERS,
                             params={"per_page": 100, "page": page}, timeout=45)
            if r.status_code != 200:
                if page == 1:
                    print(f"  gelbring: la web respondio HTTP {r.status_code}")
                break
            d = r.json()
            if not d: break
            productos.extend(d); page += 1
            if page > 40: break
            time.sleep(0.5)
    except Exception as e:
        print(f"  gelbring: fallo la web ({str(e)[:60]})")
    return productos

def _leer_snapshot():
    """Foto del catalogo guardada en listas/gelbring_web.json."""
    path = os.path.join(LISTAS_DIR, "gelbring_web.json")
    if not os.path.isfile(path): return []
    import json
    with open(path, encoding="utf-8") as f:
        datos = json.load(f)
    # adaptar al formato de la API
    return [{
        "name": d.get("name", ""),
        "sku": d.get("sku", ""),
        "slug": d.get("slug", ""),
        "description": d.get("description", ""),
        "categories": [{"name": c} for c in d.get("categories", [])],
        "images": [{"src": u} for u in d.get("images", [])],
        "is_in_stock": d.get("is_in_stock", True),
    } for d in datos]

def obtener():
    precios = cargar_listas()
    if not precios:
        raise RuntimeError("Gelbring: no se pudo leer ninguna lista de precios en listas/")
    pdf_norm = {_norm(c): (c, p) for c, p in precios.items()}
    codigos = sorted(pdf_norm.keys(), key=len, reverse=True)

    productos = _traer_web()
    if not productos:
        productos = _leer_snapshot()
        if productos:
            print(f"  gelbring: la web bloqueo el acceso, se usa la foto local ({len(productos)} productos)")
    if not productos:
        raise RuntimeError("Gelbring: ni la web ni la foto local (listas/gelbring_web.json) dieron productos")

    filas = []
    publicados = 0
    sin_precio = 0
    for p in productos:
        title = html.unescape(p.get("name", "") or "").strip()
        sku_web = p.get("sku") or ""
        campo = _norm(title + " " + sku_web)
        hit = None
        for cn in codigos:
            if cn in campo:
                hit = pdf_norm[cn]; break
        if not hit:
            sin_precio += 1
            continue
        codigo, precio = hit

        cats = ", ".join(c["name"] for c in p.get("categories", []))
        madre, sub = clasificar(title, cats)
        sub = unificar(sub)
        marca = marca_de(title)
        h = _handle(codigo, p.get("slug"))
        body = p.get("description") or title
        imgs = [im.get("src") for im in p.get("images", []) if im.get("src")]
        hay_stock = p.get("is_in_stock")

        # SIN tag stock-verificado en esta fuente
        tg = ", ".join([t for t in [sub, marca] if t])
        fila = {c: "" for c in COLS}
        fila.update({
            "Handle": h, "Title": title, "Body HTML": body, "Vendor": marca,
            "Type": madre, "Tags": tg, "Published": "TRUE",
            "Option1 Name": "Título", "Option1 Value": "Default Title",
            "Variant SKU": codigo, "Variant Price": f"{round(precio,2)}",
            "Variant Compare At Price": "",
            "Variant Inventory Qty": "10" if hay_stock else "0",
            "Variant Inventory Policy": "deny",
        })
        if imgs: fila["Image Src"] = imgs[0]; fila["Image Position"] = "1"
        filas.append(fila); publicados += 1
        for pos, url in enumerate(imgs[1:], 2):
            filas.append({**{c: "" for c in COLS}, "Handle": h,
                          "Image Src": url, "Image Position": str(pos)})

    print(f"  gelbring: {publicados} con precio, {sin_precio} sin precio (no se publican)")
    return filas, publicados

if __name__ == "__main__":
    filas, n = obtener()
    print(f"Gelbring: {n} productos, {len(filas)} filas")
