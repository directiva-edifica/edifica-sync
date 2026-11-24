"""
Fuente: VIVION HAUS (vivionhaus.com) - climatizacion y confort
Calefactores a pellet, estufas a lena, aire acondicionado, bombas de
calor para piscina, barbacoas y accesorios.

La web nueva publica JSON-LD (schema.org Product) en cada ficha, de donde
salen nombre, descripcion, SKU, marca, categoria, imagen y PRECIO.

PRECIO: el JSON-LD trae DOS ofertas por producto. La primera es el precio
normal; la segunda se llama "Precio con descuento Banco Santander". Se
publica SIEMPRE la normal; la del Santander se descarta porque solo
aplica pagando con ese banco.

IMAGENES: el pie de cada ficha tiene un bloque "Productos relacionados"
con miniaturas de OTROS productos (tamano 306x430). Si se toman todas las
imagenes de la pagina, un aire acondicionado termina con fotos de bombas
de piscina. Por eso se corta el HTML antes de ese bloque y se descartan
las miniaturas de ese tamano.

Precios en USD. Sin margen (precio de lista de Vivion).
Scraping permitido: su robots.txt habilita explicitamente a ClaudeBot.
"""
import re
import json
import time
import requests
from concurrent.futures import ThreadPoolExecutor
from bs4 import BeautifulSoup
from fuentes.unificar import unificar

NOMBRE = "vivion"
SITEMAP = "https://www.vivionhaus.com/sitemap.xml"
BASE = "https://www.vivionhaus.com"
HILOS = 5
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; EdificaBot/1.0; +https://edifica.uy)",
    "Accept-Language": "es-UY,es;q=0.9",
}

# Categoria de Vivion -> (Type, subcategoria de Edifica)
MAPEO = {
    "Confort Frío":                        ("Electro", "Climatización"),
    "Calefactores a pellets de madera":    ("Electro", "Climatización"),
    "Estufas de alto rendimiento a leña":  ("Electro", "Climatización"),
    "Hornos a pellets y hornos a leña":    ("Electro", "Cocinas"),
    "Barbacoas a pellets de madera":       ("Electro", "Parrillas"),
    "Bombas de calor para piscina":        ("Hogar", "Piscinas"),
    "Pellets de madera certificados":      ("Hogar", "Pellets"),
    "Accesorios para equipos":             ("Accesorios", ""),
}

COLS = ["Handle", "Title", "Body HTML", "Vendor", "Type", "Tags", "Published",
        "Option1 Name", "Option1 Value", "Option2 Name", "Option2 Value",
        "Option3 Name", "Option3 Value", "Variant SKU", "Variant Price",
        "Variant Compare At Price", "Variant Inventory Qty",
        "Variant Inventory Policy", "Image Src", "Image Position"]


def clasificar(cat, nombre=""):
    if cat in MAPEO:
        return MAPEO[cat]
    t = (str(cat) + " " + nombre).lower()
    if "piscina" in t:   return ("Hogar", "Piscinas")
    if "barbacoa" in t or "bbq" in t: return ("Electro", "Parrillas")
    if "horno" in t:     return ("Electro", "Cocinas")
    if "pellet" in t and "calefactor" not in t: return ("Hogar", "Pellets")
    if any(x in t for x in ("aire", "inverter", "btu", "split", "piso-techo")):
        return ("Electro", "Climatización")
    if any(x in t for x in ("estufa", "calefactor", "caldera")):
        return ("Electro", "Climatización")
    if any(x in t for x in ("tubo", "accesorio", "porta", "jarra", "aspiradora")):
        return ("Accesorios", "")
    return ("Electro", "Climatización")


def _handle(sku, url):
    base = url.rstrip("/").split("/")[-1] or sku
    return "vh-" + re.sub(r'[^a-z0-9]+', '-', base.lower()).strip('-')


def _absolut(u):
    if not u:
        return ""
    if u.startswith("http"):
        return u
    return BASE + ("" if u.startswith("/") else "/") + u


def _listar_urls():
    r = requests.get(SITEMAP, headers=HEADERS, timeout=60)
    r.raise_for_status()
    urls = [u for u in re.findall(r'<loc>([^<]+)</loc>', r.text)
            if "/es/productos/" in u and "?" not in u]
    return sorted(set(urls))


def _producto_jsonld(html):
    for bloque in re.findall(r'<script[^>]*ld\+json[^>]*>(.*?)</script>', html, re.S):
        try:
            d = json.loads(bloque.strip())
        except Exception:
            continue
        for x in d.get("@graph", []) if isinstance(d, dict) else []:
            if isinstance(x, dict) and x.get("@type") == "Product":
                return x
    return None


def _precio_normal(prod):
    """Devuelve el precio de lista, NUNCA el del Banco Santander."""
    offs = prod.get("offers") or []
    if isinstance(offs, dict):
        offs = [offs]
    for o in offs:
        etiqueta = (o.get("name") or "") + " " + (o.get("description") or "")
        if "santander" in etiqueta.lower():
            continue
        if (o.get("priceCurrency") or "USD").upper() != "USD":
            continue
        try:
            v = float(o.get("price") or 0)
        except (TypeError, ValueError):
            continue
        if v > 0:
            return v
    return None


def _imagenes(html, principal):
    """Solo las imagenes del producto. Se corta antes de 'Productos
    relacionados' y se descartan las miniaturas 306x430, que son de otros
    productos."""
    corte = html.find("Productos relacionados")
    cab = html[:corte] if corte > 0 else html
    imgs = []
    if principal:
        imgs.append(_absolut(principal))
    for m in re.findall(r'/storage/uploads/[A-Za-z0-9_\-\.]+\.(?:png|jpg|jpeg|webp)', cab):
        if re.search(r'306[xX]430', m):      # miniatura de producto relacionado
            continue
        u = _absolut(m)
        if u not in imgs:
            imgs.append(u)
    return imgs[:8]


def _ficha_y_descripcion(soup):
    """Saca la ficha tecnica (pares dato/valor), la descripcion y los
    beneficios, y arma el Body HTML."""
    for tag in soup(["script", "style", "nav", "footer", "svg"]):
        tag.decompose()
    texto = soup.get_text("\n", strip=True)
    lineas = [l.strip() for l in texto.split("\n") if l.strip()]

    def bloque(desde, hasta):
        try:
            i = lineas.index(desde)
        except ValueError:
            return []
        out = []
        for l in lineas[i + 1:]:
            if l in hasta:
                break
            out.append(l)
        return out

    LIMITES = {"FICHA TÉCNICA", "DESCRIPCIÓN", "BENEFICIOS",
               "Productos relacionados", "Visitanos", "PRODUCTOS RELACIONADOS"}
    ficha = bloque("FICHA TÉCNICA", LIMITES)
    desc = bloque("DESCRIPCIÓN", LIMITES)
    benef = bloque("BENEFICIOS", LIMITES)

    partes = []
    if desc:
        partes.append("<p>" + " ".join(desc) + "</p>")
    if benef:
        partes.append("<h3>Beneficios</h3><ul>" +
                      "".join(f"<li>{b}</li>" for b in benef) + "</ul>")
    if ficha:
        filas = ""
        # la ficha viene como dato, valor, dato, valor...
        for i in range(0, len(ficha) - 1, 2):
            filas += f"<tr><td><strong>{ficha[i]}</strong></td><td>{ficha[i+1]}</td></tr>"
        if filas:
            partes.append("<h3>Ficha técnica</h3><table>" + filas + "</table>")

    sku = ""
    if "SKU" in ficha:
        i = ficha.index("SKU")
        if i + 1 < len(ficha):
            sku = ficha[i + 1].strip()
    return "".join(partes), sku


def _ficha_producto(url):
    for intento in range(1, 4):
        try:
            r = requests.get(url, headers=HEADERS, timeout=45)
        except Exception:
            time.sleep(3 * intento)
            continue
        if r.status_code == 404:
            return None
        if r.status_code != 200:
            time.sleep(3 * intento)
            continue
        r.encoding = "utf-8"
        prod = _producto_jsonld(r.text)
        if not prod:
            return None
        prod["_html"] = r.text
        prod["_url"] = url
        return prod
    return None


def obtener():
    urls = _listar_urls()
    if not urls:
        raise RuntimeError("Vivion: el sitemap no devolvio productos")

    fichas = []
    with ThreadPoolExecutor(max_workers=HILOS) as ex:
        for d in ex.map(_ficha_producto, urls):
            if d:
                fichas.append(d)

    if len(fichas) < len(urls) * 0.6:
        raise RuntimeError(
            f"Vivion: solo se leyeron {len(fichas)} de {len(urls)} fichas; "
            f"se usa el respaldo")

    filas, publicados, sin_precio = [], 0, 0
    for d in fichas:
        title = (d.get("name") or "").strip()
        if not title:
            continue
        precio = _precio_normal(d)
        if precio is None:
            sin_precio += 1
            continue

        soup = BeautifulSoup(d["_html"], "html.parser")
        body, sku_ficha = _ficha_y_descripcion(soup)
        if not body:
            body = (d.get("description") or title)

        sku = sku_ficha or str(d.get("sku") or d.get("mpn") or "").strip()
        madre, sub = clasificar(d.get("category"), title)
        sub = unificar(sub)
        h = _handle(sku, d["_url"])
        imgs = _imagenes(d["_html"], d.get("image"))
        hay_stock = "InStock" in str(d.get("offers"))

        fila = {c: "" for c in COLS}
        fila.update({
            "Handle": h, "Title": title, "Body HTML": body,
            "Vendor": "Vivion Haus", "Type": madre,
            "Tags": ", ".join([t for t in [sub, "Vivion Haus"] if t]),
            "Published": "TRUE",
            "Option1 Name": "Título", "Option1 Value": "Default Title",
            "Variant SKU": sku,
            "Variant Price": f"{round(precio, 2)}",
            "Variant Inventory Qty": "10" if hay_stock else "0",
            "Variant Inventory Policy": "deny",
        })
        if imgs:
            fila["Image Src"] = imgs[0]
            fila["Image Position"] = "1"
        filas.append(fila)
        publicados += 1

        for pos, u in enumerate(imgs[1:], 2):
            filas.append({**{c: "" for c in COLS}, "Handle": h,
                          "Image Src": u, "Image Position": str(pos)})

    print(f"  vivion: {publicados} con precio, {sin_precio} sin precio (no se publican)")
    return filas, publicados


if __name__ == "__main__":
    f, n = obtener()
    print(f"Vivion: {n} productos, {len(f)} filas")
