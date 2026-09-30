"""
Fuente: BIOMASSA URUGUAY (biomassa.com.uy)
Plataforma Odoo. No hay feed ni API publica, pero cada ficha del shop
emite JSON-LD (ProductGroup con hasVariant), de donde salen nombre,
descripcion, imagen, precio, moneda y stock de cada variante.

Rubro: morteros, pinturas, revestimientos, impermeabilizantes,
selladores PU y steel framing.

MONEDA: Biomassa publica en PESOS URUGUAYOS. Por eso declara
MONEDA = "UYU" y combinar.py NO le aplica la conversion USD->UYU.
Si se saca esa marca, los precios quedan multiplicados por la cotizacion.

MARGEN: se publica el precio de Biomassa tal cual, sin recargo (0%).
"""
import re
import json
import time
import requests
from concurrent.futures import ThreadPoolExecutor
from fuentes.unificar import unificar

NOMBRE = "biomassa"
MONEDA = "UYU"       # <-- evita la conversion de moneda en combinar.py
MARGEN = 0.0         # se publica el precio de lista de Biomassa
HILOS = 5

SITEMAP = "https://www.biomassa.com.uy/sitemap.xml"
HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                         "AppleWebKit/537.36 (KHTML, like Gecko) "
                         "Chrome/120.0.0.0 Safari/537.36",
           "Accept-Language": "es-UY,es;q=0.9"}

# Palabras del nombre/descripcion -> (Type, subcategoria).
# Biomassa no expone la categoria en la ficha, asi que se deduce del
# nombre del producto. El orden importa: gana la primera que coincide.
REGLAS = [
    (("sellador pu", "sellador poliuretanico"), ("Construcción", "Selladores")),
    (("membrana", "impermeabiliz", "bioblock", "bloqueador de humedad"),
     ("Construcción", "Impermeabilizantes")),
    (("barniz", "proteccion de superficie", "protector"),
     ("Construcción", "Protección de Superficies")),
    (("enduido", "masilla", "fondo fijador", "sellador acrilico",
      "pre-pintura", "pre pintura", "promotor de adherencia"),
     ("Construcción", "Masillas y Pre-pintura")),
    (("aislante", "biotherm", "steel framing", "basecoat", "bioflex"),
     ("Construcción", "Steel Framing")),
    (("pintura", "esmalte"), ("Construcción", "Pinturas")),
    (("revestimiento", "texturado", "piedras lamato", "efecto cemento",
      "efecto decorativo", "marmol"), ("Construcción", "Revestimientos")),
    (("revoque", "mezcla pronta", "nivelante", "mortero"),
     ("Construcción", "Morteros")),
]

COLS = ["Handle", "Title", "Body HTML", "Vendor", "Type", "Tags", "Published",
        "Option1 Name", "Option1 Value", "Option2 Name", "Option2 Value",
        "Option3 Name", "Option3 Value", "Variant SKU", "Variant Price",
        "Variant Compare At Price", "Variant Inventory Qty",
        "Variant Inventory Policy", "Image Src", "Image Position"]


def clasificar(texto):
    t = (texto or "").lower()
    for claves, destino in REGLAS:
        if any(k in t for k in claves):
            return destino
    return ("Construcción", "Otros")


def _handle(url):
    slug = url.rstrip("/").split("/shop/")[-1]
    return "bm-" + re.sub(r'[^a-z0-9]+', '-', slug.lower()).strip('-')


MEDIDA = re.compile(r'\d+([.,]\d+)?\s*(kg|g|l|lt|lts|litros?|ml|cc|m2|unidades?|u)\b',
                    re.I)


def _atributos(nombre_grupo, nombre_var):
    """Separa el nombre de la variante en sus atributos.

    Odoo los concatena entre parentesis y separados por coma:
        'Barniz PU Satinado (3,6 L, Blanco)'  -> ['3,6 L', 'Blanco']
        'Revoque pronto para uso (5 kg)'      -> ['5 kg']
    Devuelve (presentacion, color). Cualquiera de los dos puede ser "".
    """
    m = re.search(r'\(([^)]*)\)\s*$', nombre_var or "")
    if m:
        crudo = m.group(1)
    elif nombre_var and nombre_grupo and nombre_var != nombre_grupo:
        crudo = nombre_var.replace(nombre_grupo, "").strip(" -–")
    else:
        return "", ""

    # "3,6 L" viene partido por la coma decimal: se vuelve a unir antes
    # de separar los atributos.
    crudo = re.sub(r'(\d),\s*(\d)', r'\1,\2', crudo)
    crudo = re.sub(r'(?<=\d),(?=\d)', '\x00', crudo)

    presentacion, color = "", ""
    for parte in [p.strip().replace('\x00', ',') for p in crudo.split(",") if p.strip()]:
        if MEDIDA.search(parte):
            presentacion = f"{presentacion}, {parte}".strip(", ") if presentacion else parte
        else:
            color = f"{color}, {parte}".strip(", ") if color else parte
    return presentacion.strip(), color.strip()


def _listar_urls():
    r = requests.get(SITEMAP, headers=HEADERS, timeout=60)
    r.raise_for_status()
    urls = []
    for u in re.findall(r'<loc>([^<]+)</loc>', r.text):
        if "/shop/" not in u or "/category/" in u:
            continue
        if u.rstrip("/").endswith("/shop"):
            continue
        urls.append(u)
    return sorted(set(urls))


def _ficha(url):
    """Devuelve el ProductGroup (o Product) del JSON-LD de la ficha."""
    for intento in range(3):
        try:
            r = requests.get(url, headers=HEADERS, timeout=40)
        except Exception:
            time.sleep(2 + intento * 3)
            continue
        if r.status_code != 200:
            time.sleep(2 + intento * 3)
            continue
        r.encoding = "utf-8"
        for bloque in re.findall(r'<script[^>]*ld\+json[^>]*>(.*?)</script>',
                                 r.text, re.S):
            try:
                d = json.loads(bloque.strip())
            except Exception:
                continue
            # Odoo puede emitir el bloque como objeto o dentro de una lista
            for x in (d if isinstance(d, list) else [d]):
                if isinstance(x, dict) and x.get("@type") in ("ProductGroup", "Product"):
                    x["_url"] = url
                    x["_doc"] = _doc_de(r.text)
                    return x
        return None
    return None


def _doc_de(html):
    """Link a la ficha tecnica del producto. En Biomassa no son PDF sino
    paginas del propio sitio (/ficha-tecnica-...), con rendimiento, modo de
    aplicacion y datos tecnicos. 19 de los 21 productos tienen una."""
    for href in re.findall(r'href=[\'"]([^\'"]+)[\'"]', html):
        if "ficha-tecnica" in href.lower() or href.lower().endswith(".pdf"):
            if href.startswith("/"):
                href = "https://www.biomassa.com.uy" + href
            if href.startswith("http"):
                return href
    return ""


def _oferta(v):
    o = v.get("offers") or {}
    if isinstance(o, list):
        o = o[0] if o else {}
    return o


def obtener():
    urls = _listar_urls()
    if not urls:
        raise RuntimeError("El sitemap de Biomassa no devolvio productos")

    fichas = []
    with ThreadPoolExecutor(max_workers=HILOS) as ex:
        for d in ex.map(_ficha, urls):
            if d:
                fichas.append(d)

    if len(fichas) < len(urls) * 0.5:
        raise RuntimeError(f"Solo se leyeron {len(fichas)} de {len(urls)} fichas")

    filas, publicados = [], 0
    for d in fichas:
        title = (d.get("name") or "").strip()
        if not title:
            continue
        variantes = d.get("hasVariant") or [d]
        # se clasifica por el NOMBRE del producto: la descripcion menciona
        # palabras de otros rubros ("pintura", "revoque") y ensucia el match
        madre, sub = clasificar(title)
        sub = unificar(sub)
        h = _handle(d["_url"])

        desc = (variantes[0].get("description") or d.get("description") or "").strip()
        lineas = [l.strip() for l in desc.split("\n") if l.strip()]
        body = ("<ul>" + "".join(f"<li>{l}</li>" for l in lineas) + "</ul>"
                if lineas else title)

        # Ficha tecnica como boton cliqueable y destacado al final de la
        # descripcion. En este rubro el dato tecnico (rendimiento, modo de
        # aplicacion, secado) decide la compra: no se puede omitir.
        if d.get("_doc"):
            body += (
                '<p style="margin-top:20px;">'
                f'<a href="{d["_doc"]}" target="_blank" rel="noopener" '
                'style="display:inline-block;padding:12px 22px;'
                'background:#1a1a1a;color:#ffffff;text-decoration:none;'
                'border-radius:6px;font-weight:700;font-size:15px;">'
                '📄 Ver ficha técnica completa'
                '</a></p>'
            )

        # imagen del grupo y de cada variante, sin repetir
        imgs, vistas = [], set()
        for candidata in [d.get("image")] + [v.get("image") for v in variantes]:
            if isinstance(candidata, list):
                candidata = candidata[0] if candidata else None
            if candidata and candidata not in vistas:
                vistas.add(candidata)
                imgs.append(candidata)

        # Los nombres de opcion se deciden a nivel PRODUCTO: en Shopify todas
        # las variantes de un producto comparten las mismas opciones.
        attrs = [_atributos(title, v.get("name")) for v in variantes]
        hay_pres = any(p for p, _ in attrs)
        hay_color = any(c for _, c in attrs)
        if hay_pres and hay_color:
            op1, op2 = "Presentación", "Color"
        elif hay_pres:
            op1, op2 = "Presentación", ""
        elif hay_color:
            op1, op2 = "Color", ""
        else:
            op1, op2 = "Título", ""

        base = len(filas)
        hubo = False
        for i, v in enumerate(variantes):
            o = _oferta(v)
            if (o.get("priceCurrency") or "UYU").upper() != "UYU":
                continue
            try:
                precio = float(o.get("price") or 0)
            except (TypeError, ValueError):
                continue
            if precio <= 0:
                continue
            precio = round(precio * (1 + MARGEN))
            hay_stock = "InStock" in (o.get("availability") or "")

            fila = {c: "" for c in COLS}
            if not hubo:
                fila.update({
                    "Handle": h, "Title": title, "Body HTML": body,
                    "Vendor": "Biomassa", "Type": madre,
                    "Tags": ", ".join([t for t in [sub, "Biomassa"] if t]),
                    "Published": "TRUE", "Option1 Name": op1,
                })
                if op2:
                    fila["Option2 Name"] = op2
                base = len(filas)
                hubo = True
            else:
                fila["Handle"] = h
            pres, color = attrs[i]
            if op1 == "Presentación":
                v1, v2 = (pres or "Único"), (color or "Único" if op2 else "")
            elif op1 == "Color":
                v1, v2 = (color or "Único"), ""
            else:
                v1, v2 = "Default Title", ""
            fila.update({
                "Option1 Value": v1,
                "Variant SKU": (v.get("sku") or v.get("mpn") or "").strip(),
                "Variant Price": f"{precio}.00",
                "Variant Inventory Qty": "10" if hay_stock else "0",
                "Variant Inventory Policy": "deny",
            })
            if op2:
                fila["Option2 Value"] = v2
            filas.append(fila)

        if not hubo:
            continue
        publicados += 1

        if imgs:
            filas[base]["Image Src"] = imgs[0]
            filas[base]["Image Position"] = "1"
            for pos, url in enumerate(imgs[1:9], 2):
                filas.append({**{c: "" for c in COLS}, "Handle": h,
                              "Image Src": url, "Image Position": str(pos)})

    return filas, publicados


if __name__ == "__main__":
    f, n = obtener()
    print(f"Biomassa: {n} productos, {len(f)} filas")
