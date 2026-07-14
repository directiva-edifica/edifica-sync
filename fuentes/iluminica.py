"""
Fuente: ILUMINICA (plataforma Fenicio, comercio 'ilumuy')
Iluminacion LED. Marca real del feed (Chiaro, Neuhaus pure, Potenza).
Precios mixtos USD/UYU -> todo a USD (dolar compra). Sin margen. Todo el catalogo.
"""
import requests, re
import xml.etree.ElementTree as ET
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from bs4 import BeautifulSoup
from fuentes.unificar import unificar

NOMBRE = "iluminica"
FEED_URL = "https://tienda.iluminica.com/feeds/productos/ilumuy/fenicio"
DOLAR_API = "https://uy.dolarapi.com/v1/cotizaciones"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; EdificaBot/1.0)"}
NS = {"a": "http://www.w3.org/2005/Atom"}

MAPEO = {
    "Iluminación > Colgantes": ["Iluminación", "Colgantes"],
    "Iluminación > Paneles y Embutidos": ["Iluminación", "Paneles"],
    "Iluminación > Plafones diseño": ["Iluminación", "Plafones"],
    "Iluminación > Apliques y Spots": ["Iluminación", "Apliques"],
    "Iluminación > Portatiles": ["Iluminación", "Portátiles"],
    "Iluminación > Tracklight y rieles": ["Iluminación", "Rieles"],
    "Iluminación > Lámparas, tubos y regletas": ["Iluminación", "Lámparas – Tubos LED"],
    "Iluminación > Reflectores": ["Iluminación", "Reflectores"],
    "Iluminación > Pinchos": ["Iluminación", "Pinchos"],
    "Iluminación > Camineros": ["Iluminación", "Camineros"],
    "Iluminación > Palas": ["Iluminación", "Palas"],
    "Iluminación > Campanas LED": ["Iluminación", "Campanas LED"],
    "Iluminación > Lámparas de pie": ["Iluminación", "Lámparas de pie"],
    "Accesorios": ["Accesorios", ""],
    "Accesorios > Drivers": ["Accesorios", "Drivers"],
    "Accesorios > Varios": ["Accesorios", ""],
}

def clasificar(cat):
    if cat in MAPEO: return MAPEO[cat]
    if cat.startswith("Iluminación"): return ["Iluminación", "Otros"]
    if cat.startswith("Accesorios"): return ["Accesorios", ""]
    return ["Iluminación", "Otros"]

def dolar_compra():
    try:
        r = requests.get(DOLAR_API, timeout=15)
        for c in r.json():
            if c.get("moneda") == "USD":
                return float(c["compra"])
    except Exception: pass
    return 39.0

def _g(item, tag):
    el = item.find("a:"+tag, NS)
    return (el.text or "").strip() if el is not None and el.text else ""

def _handle(code): return "il-" + re.sub(r'[^a-z0-9]+','-', code.lower()).strip('-')

def _get_descripcion(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=30); r.encoding="utf-8"
        soup = BeautifulSoup(r.text, "html.parser")
        bloque = soup.find("div", class_="blkDetalle")
        if bloque:
            t = bloque.find("div", class_="text")
            if t: return t.decode_contents().strip()
    except Exception:
        pass
    return ""

COLS = ["Handle","Title","Body HTML","Vendor","Type","Tags","Published",
        "Option1 Name","Option1 Value","Variant SKU","Variant Price",
        "Variant Compare At Price","Variant Inventory Qty",
        "Variant Inventory Policy","Image Src","Image Position"]

def obtener():
    dolar = dolar_compra()
    resp = requests.get(FEED_URL, timeout=60); resp.encoding="utf-8"
    root = ET.fromstring(resp.text)
    productos = OrderedDict()
    for item in root.findall(".//a:item", NS):
        productos.setdefault(_g(item,"productCode"), []).append(item)
    if not productos:
        raise RuntimeError("Iluminica: feed vacio")

    def a_usd(precio_txt):
        # precio_txt = "5550.00 USD" o "20120.00 UYU"
        if not precio_txt: return ""
        partes = precio_txt.split()
        try:
            valor = float(partes[0])
        except Exception:
            return ""
        moneda = partes[1] if len(partes) > 1 else "UYU"
        if moneda == "USD":
            return f"{round(valor,2)}"
        return f"{round(valor/dolar,2)}"  # UYU -> USD

    links = {p:_g(v[0],"link") for p,v in productos.items()}
    descripciones = {}
    with ThreadPoolExecutor(max_workers=8) as ex:
        for p,d in ex.map(lambda kv:(kv[0],_get_descripcion(kv[1])), links.items()):
            descripciones[p]=d

    filas=[]
    for pcode, variantes in productos.items():
        v0 = variantes[0]
        madre, sub = clasificar(_g(v0,"productType"))
        sub = unificar(sub)
        marca = _g(v0,"brand") or "Iluminica"
        title = _g(v0,"productName") or _g(v0,"name")
        h = _handle(pcode)
        desc = descripciones.get(pcode,"")
        if desc:
            lineas=[l.strip() for l in BeautifulSoup(desc,"html.parser").get_text("\n").split("\n") if l.strip()]
            body="<ul>"+"".join(f"<li>{l}</li>" for l in lineas)+"</ul>"
        else:
            body=title
        imgs=[]
        for v in variantes:
            for l in v.findall("a:images/a:link", NS):
                if l.text and l.text.strip() not in imgs: imgs.append(l.text.strip())
        base=len(filas)
        for i,v in enumerate(variantes):
            oferta=_g(v,"sale")=="YES"
            hay_stock=_g(v,"availability")=="IN_STOCK"
            fila={c:"" for c in COLS}
            if i==0:
                tg=", ".join([t for t in [sub,marca]+(["stock-verificado"] if hay_stock else []) if t])
                fila.update({"Handle":h,"Title":title,"Body HTML":body,"Vendor":marca,
                             "Type":madre,"Tags":tg,"Published":"TRUE","Option1 Name":"Color"})
            else:
                fila["Handle"]=h
            fila.update({"Option1 Value":_g(v,"variantName") or "Único","Variant SKU":_g(v,"sku"),
                         "Variant Price":a_usd(_g(v,"salePrice")),
                         "Variant Compare At Price":a_usd(_g(v,"listPrice")) if oferta else "",
                         "Variant Inventory Qty":"10" if hay_stock else "0",
                         "Variant Inventory Policy":"deny"})
            filas.append(fila)
        for pos,url in enumerate(imgs,1):
            if pos==1:
                filas[base]["Image Src"]=url; filas[base]["Image Position"]="1"
            else:
                filas.append({**{c:"" for c in COLS},"Handle":h,"Image Src":url,"Image Position":str(pos)})
    return filas, len(productos)

if __name__=="__main__":
    filas,n=obtener()
    print(f"Iluminica: {n} productos, {len(filas)} filas")
