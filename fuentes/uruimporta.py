"""
Fuente: URUIMPORTA (WooCommerce Store API, sin clave)
Lee ~9000 productos, convierte UYU->USD al dolar COMPRA del dia (el mas bajo,
para obtener mas dolares por peso), suma 19% de margen, y excluye Electro.
Mapea las categorias finas a las 8 categorias madre de Edifica.
"""
import requests, re, html
from fuentes.unificar import unificar

NOMBRE = "uruimporta"
API = "https://uruimporta.com.uy/wp-json/wc/store/v1/products"
DOLAR_API = "https://uy.dolarapi.com/v1/cotizaciones"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; EdificaBot/1.0)"}
MARGEN = 1.19  # 19% extra sobre el precio de Uruimporta

MADRE = {
    "Herramientas Manuales": "Herramientas", "Herramientas Eléctricas": "Herramientas",
    "Herramientas Batería": "Herramientas", "Taller": "Herramientas",
    "Taller – Neumática": "Herramientas", "Neumática": "Herramientas",
    "Llaves – Dados": "Herramientas", "Dados": "Herramientas",
    "Llaves Combinadas": "Herramientas", "Llaves Tipo L T Y": "Herramientas",
    "Llave Allen – Torx": "Herramientas", "Llaves Ajustables": "Herramientas",
    "Llaves de Caño": "Herramientas", "Discos, Mechas": "Herramientas",
    "Mechas": "Herramientas", "Puntas Rotomartillos": "Herramientas",
    "Discos Varios": "Herramientas", "Discos Madera": "Herramientas",
    "Discos Metal": "Herramientas", "Discos Concreto": "Herramientas",
    "Martillos – Prensas": "Herramientas", "Pinzas": "Herramientas",
    "Destornillador": "Herramientas", "Sierras Copas": "Herramientas",
    "Sierras – Serruchos": "Herramientas", "Sierras – Cepillos": "Herramientas",
    "Cepillos – Cizallas": "Herramientas", "Amoladoras – Lijadoras": "Herramientas",
    "Taladros – Rotomartillos": "Herramientas", "Lijas – Piedras": "Herramientas",
    "Limas – Formones": "Herramientas", "Escuadras – Fretachos": "Herramientas",
    "Corta Hierro – Cuchara": "Herramientas", "Herramientas de Corte": "Herramientas",
    "Cintas Métricas – Agrimensor": "Herramientas", "Niveles": "Herramientas",
    "Calibres – Micrómetros": "Herramientas", "Testers – Amperimétricas": "Herramientas",
    "Medición – Electrónica": "Herramientas", "Cajas de Herramientas": "Herramientas",
    "Accesorios para Herramientas": "Herramientas", "Terrajas – Balonadoras": "Herramientas",
    "Pistolas Silicona – Remachadoras": "Herramientas", "Gatos Hidráulicos": "Herramientas",
    "Escaleras": "Herramientas", "Soldadoras Inverter": "Herramientas",
    "Fresadoras – Minitornos": "Herramientas", "Bombas de Agua": "Herramientas",
    "Hidrolavadoras": "Herramientas", "Generadores – Compresores": "Herramientas",
    "Mezcladores, Vibradores": "Herramientas", "Cargadores de Batería": "Herramientas",
    "Choclas – Plomadas": "Herramientas", "Mango Criket": "Herramientas",
    "Ruedas": "Herramientas", "HERRAMIENTAS": "Herramientas",
    "Herrajes – Candados": "Construcción", "Herrajes Varios": "Construcción",
    "Candados": "Construcción", "Cerraduras": "Construcción", "Bisagras": "Construcción",
    "Pasadores": "Construcción", "Mensulas": "Construcción", "Tiradores": "Construcción",
    "Sunchos – Cuerdas": "Construcción", "Albañileria, Herreria": "Construcción",
    "Sanitaria – Adhesivo": "Construcción", "Termofusión, PPL, PVC": "Construcción",
    "Adhesivos, Siliconas": "Construcción", "Clavos – Tornillos": "Construcción",
    "Valvulas de gas": "Construcción", "Pinturas": "Construcción",
    "Pinturas – Abrasivos – Prod. Químicos": "Construcción", "Productos Químicos": "Construcción",
    "Brochas – Espatulas": "Construcción", "Rodillos": "Construcción",
    "Pinceles": "Construcción", "Bandejas – Cintas": "Construcción",
    "Seguridad": "Construcción", "FERRETERÍA": "Construcción",
    "GRIFERÍA": "Baño", "Canillas – Grifos": "Baño", "Duchas, colillas": "Baño",
    "Accesorios de Baño": "Baño", "Piletas, Sifones": "Baño", "Toallas": "Baño",
    "ILUMINACIÓN, ELECTRICIDAD": "Iluminación", "Electricidad": "Iluminación",
    "Electrónica": "Iluminación", "Luminaria – Tortugas": "Iluminación",
    "Lámparas – Tubos LED": "Iluminación", "Lámparas Colgar – Apliques": "Iluminación",
    "Artefactos – Plafones LED": "Iluminación", "Focos LED": "Iluminación",
    "Linternas, Lámparas": "Iluminación", "Pilas": "Iluminación", "Velas": "Iluminación",
    "ELECTRODOMÉSTICOS, TECNOLOGÍA": "Electro", "Pequeños Electrodomésticos": "Electro",
    "Cocinas, Hornos": "Electro", "Refrigeradores": "Electro",
    "Lavadoras, Secadoras": "Electro", "Calefones": "Electro", "Climatización": "Electro",
    "Extractores": "Electro", "Audio, Proyectores": "Electro",
    "Televisores Smart TV": "Electro", "Informática": "Electro",
    "Celulares, Tablets, Notebooks": "Electro", "Relojes – Teléfonos": "Electro",
    "Acc. Celulares, Cámaras": "Electro", "Soporte Electrodomésticos": "Electro",
    "HOGAR": "Hogar", "Cocina": "Hogar", "Bazar": "Hogar", "Loza": "Hogar",
    "Cristalería": "Hogar", "Deco, Revestimientos": "Hogar", "Organizadores": "Hogar",
    "Cortinas": "Hogar", "Alfombras": "Hogar", "Ropa de Cama": "Hogar",
    "Textiles Cocina": "Hogar", "Cotillón": "Hogar", "Ecritorio, Escolares": "Hogar",
    "Burletes – Colgadores": "Hogar", "Perchas": "Hogar", "Navidad": "Hogar",
    "Jardín, Piscina": "Jardín", "DEPORTE Y AIRE LIBRE": "Jardín", "Aire Libre": "Jardín",
    "Camping": "Jardín", "Barbacoas": "Jardín", "Fitness": "Jardín",
    "Bicicletas": "Jardín", "Acc. Bicicletas": "Jardín", "Playa": "Jardín",
    "MASCOTAS": "Jardín",
    "LIMPIEZA": "Accesorios", "Limpieza del hogar": "Accesorios",
    "Limpieza de Ropa": "Accesorios", "Limpieza de Cocina": "Accesorios",
    "Limpieza de Baños": "Accesorios", "Limpieza Pisos y Muebles": "Accesorios",
    "PERFUMERÍA Y TOCADOR": "Accesorios", "Cuidado Capilar": "Accesorios",
    "Cuidado Personal": "Accesorios", "Cuidado de la Piel": "Accesorios",
    "Desodorantes": "Accesorios", "Jabones": "Accesorios",
    "Higiene Femenina": "Accesorios", "Higiene Bucal": "Accesorios",
    "Articulos de Afeitar": "Accesorios", "Bebé": "Accesorios",
    "INDUMENTARIA": "Accesorios", "Indumentaria Casual": "Accesorios",
    "Indumentaria Trabajo": "Accesorios", "Calzado": "Accesorios",
    "Mochilas, Valijas": "Accesorios", "Paraguas": "Accesorios",
    "Accesorios Autos": "Accesorios", "Lubricantes": "Accesorios",
}


def _clean(t):
    return html.unescape(t or "").strip()


def dolar_compra():
    # Dolar COMPRA (el mas bajo) para obtener mas dolares por peso
    try:
        r = requests.get(DOLAR_API, headers=HEADERS, timeout=15)
        for c in r.json():
            if c.get("moneda") == "USD":
                return float(c["compra"])
    except Exception:
        pass
    return 39.0


def clasificar(cat_nombre):
    madre = MADRE.get(cat_nombre, "Hogar")
    return madre, cat_nombre


def _handle(sku, slug):
    base = slug or sku
    return "ui-" + re.sub(r'[^a-z0-9]+', '-', base.lower()).strip('-')


COLS = ["Handle", "Title", "Body HTML", "Vendor", "Type", "Tags", "Published",
        "Option1 Name", "Option1 Value", "Variant SKU", "Variant Price",
        "Variant Compare At Price", "Variant Inventory Qty",
        "Variant Inventory Policy", "Image Src", "Image Position"]


def obtener():
    dolar = dolar_compra()
    productos = []
    page = 1
    while True:
        r = requests.get(API, headers=HEADERS,
                         params={"per_page": 100, "page": page}, timeout=90)
        if r.status_code != 200:
            break
        data = r.json()
        if not data:
            break
        productos.extend(data)
        page += 1
        if page > 150:
            break

    if not productos:
        raise RuntimeError("Uruimporta: API sin productos")

    def usd(precio_uyu):
        # Convierte pesos a USD (dolar compra) y aplica el margen 19%
        try:
            return f"{round((float(precio_uyu) / dolar) * MARGEN, 2)}"
        except Exception:
            return ""

    def usd_directo(precio_usd):
        # Si ya viene en USD, solo aplica el margen 19%
        try:
            return f"{round(float(precio_usd) * MARGEN, 2)}"
        except Exception:
            return ""

    filas = []
    for p in productos:
        sku = str(p.get("sku") or p.get("id"))
        pr = p.get("prices", {})
        cur = pr.get("currency_code", "UYU")
        precio_raw = pr.get("price", "0")
        regular_raw = pr.get("regular_price", precio_raw)

        if cur == "USD":
            precio = usd_directo(precio_raw)
            regular = usd_directo(regular_raw)
        else:
            precio = usd(precio_raw)
            regular = usd(regular_raw)

        cats = p.get("categories", [])
        cat_nombre = _clean(cats[0]["name"]) if cats else ""
        madre, sub = clasificar(cat_nombre)

        if madre == "Electro":
            continue  # Uruimporta: no cargamos electro (lo cubre Joacamar)

        sub = unificar(sub)

        title = _clean(p.get("name"))
        body = p.get("description") or ""
        h = _handle(sku, p.get("slug"))
        oferta = p.get("on_sale", False)

        imgs = [im.get("src") for im in p.get("images", []) if im.get("src")]

        fila = {c: "" for c in COLS}
        fila.update({
            "Handle": h, "Title": title, "Body HTML": body,
            "Vendor": "Uruimporta", "Type": madre,
            "Tags": sub, "Published": "TRUE",
            "Option1 Name": "Título", "Option1 Value": "Default Title",
            "Variant SKU": sku, "Variant Price": precio,
            "Variant Compare At Price": regular if oferta else "",
            "Variant Inventory Qty": "10" if p.get("is_in_stock") else "0",
            "Variant Inventory Policy": "deny",
        })
        if imgs:
            fila["Image Src"] = imgs[0]
            fila["Image Position"] = "1"
        filas.append(fila)

        for pos, url in enumerate(imgs[1:], 2):
            filas.append({**{c: "" for c in COLS}, "Handle": h,
                          "Image Src": url, "Image Position": str(pos)})

    return filas, len(productos)


if __name__ == "__main__":
    filas, n = obtener()
    print(f"Uruimporta: {n} productos, {len(filas)} filas")
