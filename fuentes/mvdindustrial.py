"""
Fuente: MONTEVIDEO INDUSTRIAL (WooCommerce Store API)
La web tiene fotos, fichas y categorias pero NO publica precios.
Los precios son PVP de la lista propia (tabla PRECIOS de este archivo) y
solo se publican los SKU que figuran ahi. Los demas productos de la tienda
(mas de 2000) no se tocan.
Esta fuente NO lleva tag stock-verificado.
"""
import requests, re, html
from concurrent.futures import ThreadPoolExecutor
from fuentes.unificar import unificar

NOMBRE = "mvdindustrial"
API = "https://montevideoindustrial.com.uy/wp-json/wc/store/v1/products"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; EdificaBot/1.0)"}

# SKU de la lista : PVP final en USD (ya con IVA y margen incluidos)
PRECIOS = {
    "16-178-09-430": 3913.15,
    "16-002-09-005": 158.97,
    "16-045-09-020": 45.87,
    "16-045-09-010": 201.82,
    "16-178-09-405": 76.10,
    "16-178-09-410": 47.08,
    "16-165-09-002": 216.34,
    "20-141-09-010": 837.23,
    "20-141-09-012": 450.41,
    "23-101-09-004": 396.33,
    "20-603-09-028": 332.25,
    "20-603-09-030": 555.10,
    "20-604-09-005": 1059.88,
    "20-604-09-010": 1472.69,
    "20-604-09-015": 1921.50,
    "20-204-09-020": 367.02,
    "20-503-09-010": 378.76,
    "20-501-09-022": 222.74,
    "20-180-09-005": 56.61,
    "20-153-09-005": 95.31,
    "20-402-09-005": 524.20,
    "20-803-09-020": 147.16,
    "20-506-09-005": 119.44,
}

# categoria de la web -> subcategoria de Edifica (todas bajo Herramientas)
MAPEO = {
    "Taladros electricos": "Taladros – Rotomartillos",
    "Taladros de Banco Electricos": "Taladros – Rotomartillos",
    "Taladros Magnéticos Electricos": "Taladros – Rotomartillos",
    "Amoladoras 9\" Eléctricas": "Amoladoras – Lijadoras",
    "Lijadoras Electricas": "Amoladoras – Lijadoras",
    "Lijadoras de concreto Electricas": "Amoladoras – Lijadoras",
    "Rectificadoras Electricas": "Amoladoras – Lijadoras",
    "Dados y accesorios de encastre": "Dados",
    "Juegos de Dados": "Dados",
    "Almacenamiento y transporte de herramientas": "Cajas de Herramientas",
    "Juegos de Herramientas Master": "Cajas de Herramientas",
    "Medición y nivelación": "Cintas Métricas – Agrimensor",
    "Medidores de Distancia Laser": "Cintas Métricas – Agrimensor",
    "Sierras de Mesa para Madera Electricas": "Sierras – Serruchos",
    "Sierras Circulares Electrica": "Sierras – Serruchos",
    "Ingletadoras Electricas": "Sierras – Serruchos",
    "Garlopas Electricas": "Sierras – Cepillos",
    "Afilador de Mechas": "Mechas",
    "Elevacion y Sujecion de Carga": "Gatos Hidráulicos",
    "Guinches Electricos": "Gatos Hidráulicos",
    "Automotriz": "Taller",
    "Herramientas Manuales": "Taller",
}

MARCAS = ["VONDER", "CELO", "BOSTIK", "HEPYC", "DCK", "METALBO", "STANLEY"]

def _clean(t): return html.unescape(t or "").strip()

def clasificar(cats):
    """Devuelve (madre, sub) usando la categoria mas especifica que mapee."""
    for c in cats:
        c = c.strip()
        if c in MAPEO:
            return "Herramientas", MAPEO[c]
    # fallback: herramientas sin categoria especifica -> Taller
    return "Herramientas", "Taller"

def marca_de(nombre):
    n = nombre.upper()
    for m in MARCAS:
        if m in n:
            return m.capitalize() if m not in ("DCK",) else m
    return "Montevideo Industrial"

def _handle(sku):
    return "mi-" + re.sub(r'[^a-z0-9]+', '-', sku.lower()).strip('-')

COLS = ["Handle","Title","Body HTML","Vendor","Type","Tags","Published",
        "Option1 Name","Option1 Value","Variant SKU","Variant Price",
        "Variant Compare At Price","Variant Inventory Qty",
        "Variant Inventory Policy","Image Src","Image Position"]

def _buscar(sku):
    """Busca el producto por SKU exacto en la Store API."""
    try:
        r = requests.get(API, headers=HEADERS,
                         params={"search": sku, "per_page": 10}, timeout=40)
        if r.status_code != 200:
            return sku, None
        norm = re.sub(r'[^0-9A-Za-z]', '', sku)
        for p in r.json():
            if (p.get("sku") or "").strip() == sku:
                return sku, p
        for p in r.json():
            if re.sub(r'[^0-9A-Za-z]', '', p.get("sku") or "") == norm:
                return sku, p
    except Exception:
        pass
    return sku, None

def obtener():
    skus = list(PRECIOS.keys())
    encontrados = {}
    with ThreadPoolExecutor(max_workers=6) as ex:
        for sku, prod in ex.map(_buscar, skus):
            if prod:
                encontrados[sku] = prod

    if not encontrados:
        raise RuntimeError("MvdIndustrial: no se encontro ningun producto (API sin respuesta)")

    filas = []
    publicados = 0
    for sku, precio in PRECIOS.items():
        p = encontrados.get(sku)
        if not p:
            continue
        title = _clean(p.get("name"))
        cats = [c["name"].strip() for c in p.get("categories", [])]
        madre, sub = clasificar(cats)
        sub = unificar(sub)
        marca = marca_de(title)
        h = _handle(sku)
        body = p.get("description") or title
        imgs = [im.get("src") for im in p.get("images", []) if im.get("src")]
        hay_stock = p.get("is_in_stock", True)

        # SIN stock-verificado en esta fuente
        tg = ", ".join([t for t in [sub, marca] if t])
        fila = {c: "" for c in COLS}
        fila.update({
            "Handle": h, "Title": title, "Body HTML": body, "Vendor": marca,
            "Type": madre, "Tags": tg, "Published": "TRUE",
            "Option1 Name": "Título", "Option1 Value": "Default Title",
            "Variant SKU": sku, "Variant Price": f"{round(precio, 2)}",
            "Variant Compare At Price": "",
            "Variant Inventory Qty": "10" if hay_stock else "0",
            "Variant Inventory Policy": "deny",
        })
        if imgs:
            fila["Image Src"] = imgs[0]
            fila["Image Position"] = "1"
        filas.append(fila); publicados += 1
        for pos, url in enumerate(imgs[1:], 2):
            filas.append({**{c: "" for c in COLS}, "Handle": h,
                          "Image Src": url, "Image Position": str(pos)})

    faltan = len(PRECIOS) - publicados
    if faltan:
        print(f"  mvdindustrial: {faltan} SKU de la lista no se encontraron en la web")
    return filas, publicados

if __name__ == "__main__":
    filas, n = obtener()
    print(f"MvdIndustrial: {n} productos, {len(filas)} filas")
