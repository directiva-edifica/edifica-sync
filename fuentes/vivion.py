"""
Fuente: VIVION HAUS (aires acondicionados)
La web no publica precios ni stock: los datos (nombre, fotos, ficha tecnica)
se scrapean de cada pagina de producto, y los precios son fijos (lista PVP
sin IVA + 22% de IVA), definidos en la tabla PRECIOS de este archivo.
Los multisplit NO se publican. Esta fuente NO lleva tag stock-verificado.
"""
import requests, re
from concurrent.futures import ThreadPoolExecutor
from bs4 import BeautifulSoup
from fuentes.unificar import unificar

NOMBRE = "vivion"
BASE = "https://www.vivionhaus.com/producto/"
HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                         "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
IVA = 1.22  # PVP de lista viene sin IVA

# slug: (nombre publicado, precio de lista SIN IVA en USD)
PRECIOS = {
    "aa-stratos-9-btu-dc-inverter":  ("Aire Acondicionado Smart Stratos Inverter 9.000 BTU UVC", 420),
    "aa-stratos-12-btu-dc-inverter": ("Aire Acondicionado Smart Stratos Inverter 12.000 BTU UVC", 454),
    "aa-stratos-18-btu-dc-inverter": ("Aire Acondicionado Smart Stratos Inverter 18.000 BTU UVC", 667),
    "aa-stratos-24-btu-dc-inverter": ("Aire Acondicionado Smart Stratos Inverter 24.000 BTU UVC", 904),
    "aa-vivion-on-off-12000-btu":    ("Aire Acondicionado Smart Vivion On-Off 12.000 BTU", 338),
    "aa-vivion-on-off-18000-btu":    ("Aire Acondicionado Smart Vivion On-Off 18.000 BTU", 536),
    "aa-vivion-on-off-24000-btu":    ("Aire Acondicionado Smart Vivion On-Off 24.000 BTU", 693),
}

MARCA = "Vivion Haus"

COLS = ["Handle","Title","Body HTML","Vendor","Type","Tags","Published",
        "Option1 Name","Option1 Value","Variant SKU","Variant Price",
        "Variant Compare At Price","Variant Inventory Qty",
        "Variant Inventory Policy","Image Src","Image Position"]

def _handle(slug): return "vh-" + re.sub(r'[^a-z0-9]+','-', slug.lower()).strip('-')

def _scrape(slug):
    """Devuelve (imagenes, specs) de la pagina del producto."""
    try:
        r = requests.get(BASE + slug, headers=HEADERS, timeout=40)
        if r.status_code != 200:
            return [], []
        t = r.text
        soup = BeautifulSoup(t, "html.parser")
        imgs = sorted(set(re.findall(
            r'https://www\.vivionhaus\.com/uploads/(?:crop_|cp_)[^"\'\s)]+\.(?:jpg|jpeg|png|webp)',
            t, re.I)))
        txt = re.sub(r'\s+', ' ', soup.get_text(" | ", strip=True))
        specs = []
        m = re.search(r'(Voltaje / Frecuencia.*?)(?:Voltaje / Frecuencia|CONSULTE|HACÉ TU CONSULTA|$)',
                      txt, re.S)
        if m:
            partes = [p.strip() for p in m.group(1).split("|") if p.strip()]
            for i in range(0, len(partes) - 1, 2):
                specs.append((partes[i], partes[i + 1]))
        return imgs, specs
    except Exception:
        return [], []

def obtener():
    slugs = list(PRECIOS.keys())
    datos = {}
    with ThreadPoolExecutor(max_workers=6) as ex:
        for slug, res in zip(slugs, ex.map(_scrape, slugs)):
            datos[slug] = res

    filas = []
    publicados = 0
    for slug, (nombre, precio_sin_iva) in PRECIOS.items():
        imgs, specs = datos.get(slug, ([], []))
        precio = f"{round(precio_sin_iva * IVA, 2)}"
        h = _handle(slug)
        if specs:
            body = "<ul>" + "".join(f"<li>{k}: {v}</li>" for k, v in specs) + "</ul>"
        else:
            body = nombre
        sub = unificar("Climatización")
        # SIN stock-verificado en esta fuente
        tg = ", ".join([t for t in [sub, MARCA] if t])
        fila = {c: "" for c in COLS}
        fila.update({
            "Handle": h, "Title": nombre, "Body HTML": body, "Vendor": MARCA,
            "Type": "Electro", "Tags": tg, "Published": "TRUE",
            "Option1 Name": "Título", "Option1 Value": "Default Title",
            "Variant SKU": slug.upper(), "Variant Price": precio,
            "Variant Compare At Price": "",
            "Variant Inventory Qty": "10", "Variant Inventory Policy": "deny",
        })
        if imgs:
            fila["Image Src"] = imgs[0]
            fila["Image Position"] = "1"
        filas.append(fila); publicados += 1
        for pos, url in enumerate(imgs[1:], 2):
            filas.append({**{c: "" for c in COLS}, "Handle": h,
                          "Image Src": url, "Image Position": str(pos)})

    if not filas:
        raise RuntimeError("Vivion: no se genero ningun producto")
    return filas, publicados

if __name__ == "__main__":
    filas, n = obtener()
    print(f"Vivion: {n} productos, {len(filas)} filas")
