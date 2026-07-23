"""
Fuente: BEKO (tienda oficial, plataforma Fenicio, comercio 'bekouy')
Electrodomesticos de cocina. Marca Beko. Precios ya en USD (sin margen).
Todo el catalogo. Lleva tag stock-verificado.
"""
import requests, re
import xml.etree.ElementTree as ET
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from bs4 import BeautifulSoup
from fuentes.unificar import unificar

NOMBRE = "beko"
FEED_URL = "https://www.tiendabeko.com.uy/feeds/productos/bekouy/fenicio"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; EdificaBot/1.0)"}
NS = {"a": "http://www.w3.org/2005/Atom"}

MAPEO = {
    "Cocina > Anafes": ["Electro", "Cocinas"],
    "Cocina > Cocinas": ["Electro", "Cocinas"],
    "Cocina > Hornos": ["Electro", "Cocinas"],
    "Cocina > Microondas": ["Electro", "Cocinas"],
    "Cocina > Campanas": ["Electro", "Campanas"],
    "Lavavajillas > Lavavajillas libre instalación": ["Electro", "Lavavajillas"],
    "Lavavajillas > Lavavajillas panelable": ["Electro", "Lavavajillas"],
}

def clasificar(cat):
    if cat in MAPEO: return MAPEO[cat]
    c = cat.lower()
    if "lavavajilla" in c: return ["Electro", "Lavavajillas"]
    if "campana" in c: return ["Electro", "Campanas"]
    if "heladera" in c or "refriger" in c: return ["Electro", "Heladeras"]
    if "lavarropa" in c or "secarropa" in c: return ["Electro", "Lavarropas"]
    if any(x in c for x in ["anafe", "cocina", "horno", "microonda"]):
        return ["Electro", "Cocinas"]
    return ["Electro", "Otros"]

def _g(item, tag):
    el = item.find("a:"+tag, NS)
    return (el.text or "").strip() if el is not None and el.text else ""

def _precio(txt): return txt.split()[0] if txt else ""
def _handle(code): return "bk-" + re.sub(r'[^a-z0-9]+','-', code.lower()).strip('-')

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
    resp = requests.get(FEED_URL, headers=HEADERS, timeout=60); resp.encoding="utf-8"
    root = ET.fromstring(resp.text)
    productos = OrderedDict()
    for item in root.findall(".//a:item", NS):
        productos.setdefault(_g(item,"productCode"), []).append(item)
    if not productos:
        raise RuntimeError("Beko: feed vacio")

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
        marca = _g(v0,"brand") or "Beko"
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
                             "Type":madre,"Tags":tg,"Published":"TRUE","Option1 Name":"Modelo"})
            else:
                fila["Handle"]=h
            fila.update({"Option1 Value":_g(v,"variantName") or "Único","Variant SKU":_g(v,"sku"),
                         "Variant Price":_precio(_g(v,"salePrice")),
                         "Variant Compare At Price":_precio(_g(v,"listPrice")) if oferta else "",
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
    print(f"Beko: {n} productos, {len(filas)} filas")
