"""
DIEGO - lectura desde la Mac, no desde GitHub Actions.

POR QUE EXISTE ESTE ARCHIVO
---------------------------
diego.com.uy responde 403 a los servidores de GitHub Actions (datacenters
de Microsoft en EE.UU.). No es un bloqueo contra nosotros: rechaza rangos
de IP enteros, tanto que ni el robots.txt se puede leer desde ahi. Desde
una conexion uruguaya normal el sitio sirve las fichas sin problema.

Por eso la lectura de Diego sale de la Mac y no del servidor. Este script
baja el catalogo, escribe cache/diego.csv y lo sube al repo. Despues
fuentes/diego.py lee ese cache cuando no puede alcanzar la web.

AUTORIZACION
------------
El gerente de desarrollo de Diego nos confirmo su politica: no entregan
un archivo ni una API, pero habilitan a cualquier comercio a armar su
propia conexion contra el sitio. Trabajan con miles de revendedores y
estan a favor; simplemente no quieren dedicar recursos de sus
programadores a integrar con cada empresa una por una. En resumen: cada
uno se conecta con su propio sistema y ellos no tocan nada.

Igual ANTES DE LEER NADA se consulta el robots.txt. Es el canal formal
donde un sitio declara que permite, y si alguna vez cambian de politica
va a aparecer ahi antes que en una conversacion. Si dice que no, el
script se detiene. Tambien se respeta el Crawl-delay que declare, se usan
pocos hilos y nos identificamos como EdificaBot con la direccion de la
tienda, para que puedan contactarnos o limitarnos cuando quieran.

COMO SE USA
-----------
    cd ~/edifica-sync
    python3 diego_local.py              # solo escribe el cache
    python3 diego_local.py --push       # escribe el cache y lo sube al repo

Para que corra solo todas las mananas, ver el final del archivo.
"""
import argparse
import csv
import json
import os
import re
import subprocess
import sys
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import requests

# La clasificacion, los margenes y las columnas salen del modulo del repo,
# asi no hay dos copias del mapeo de categorias que se puedan desincronizar.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fuentes.diego import (CATEGORIAS, COLS, MARGEN, SITEMAP,
                           clasificar, _handle)
from fuentes.unificar import unificar

BASE = "https://www.diego.com.uy"
ROBOTS = BASE + "/robots.txt"
CACHE_CSV = "cache/diego.csv"
CACHE_META = "cache/diego_meta.json"

# Nos identificamos de verdad. No imitamos un Chrome: si Diego alguna vez
# quiere limitarnos, tiene un nombre concreto para poner en su robots.txt.
AGENTE = "EdificaBot"
HEADERS = {
    "User-Agent": f"Mozilla/5.0 (compatible; {AGENTE}/1.0; +https://edifica.uy)",
    "Accept-Language": "es-UY,es;q=0.9",
}

HILOS = 4            # suave a proposito: no queremos cargarles el servidor
ESPERA_MIN = 0.3     # segundos entre pedidos de cada hilo


# ----------------------------------------------------------------------
# robots.txt
# ----------------------------------------------------------------------
def _parsear_robots(texto):
    """Version simple y correcta del parseo por grupos."""
    grupos = {}
    actuales = []
    esperando_reglas = False
    for linea in texto.splitlines():
        linea = linea.split("#", 1)[0].strip()
        if not linea or ":" not in linea:
            continue
        campo, valor = linea.split(":", 1)
        campo, valor = campo.strip().lower(), valor.strip()
        if campo == "user-agent":
            if esperando_reglas:
                actuales = []          # arranca un grupo nuevo
            ua = valor.lower()
            actuales.append(ua)
            grupos.setdefault(ua, {"disallow": [], "allow": [], "crawl_delay": None})
            esperando_reglas = False
        else:
            esperando_reglas = True
            for ua in actuales:
                if campo == "disallow":
                    grupos[ua]["disallow"].append(valor)
                elif campo == "allow":
                    grupos[ua]["allow"].append(valor)
                elif campo == "crawl-delay":
                    try:
                        grupos[ua]["crawl_delay"] = float(valor.replace(",", "."))
                    except ValueError:
                        pass
    return grupos


def _regla_mas_larga(reglas, ruta):
    """Longitud del patron mas largo de `reglas` que matchea `ruta`."""
    mejor = -1
    for patron in reglas:
        if patron == "":
            continue
        p = patron.rstrip("$")
        if ruta.startswith(p) and len(p) > mejor:
            mejor = len(p)
    return mejor


def permiso_robots():
    """Lee el robots.txt y decide si podemos recorrer /catalogo/.

    Devuelve (permitido: bool, crawl_delay: float, motivo: str).
    Si el archivo no existe (404) no hay politica declarada y se entiende
    que esta permitido, que es la lectura estandar. Si no se puede leer por
    otra razon, NO asumimos nada: se detiene."""
    try:
        r = requests.get(ROBOTS, headers=HEADERS, timeout=30)
    except Exception as e:
        return False, 0.0, f"no se pudo leer el robots.txt ({str(e)[:60]})"

    if r.status_code == 404:
        return True, 0.0, "el sitio no publica robots.txt (sin restricciones declaradas)"
    if r.status_code in (401, 403):
        return False, 0.0, (f"el robots.txt responde HTTP {r.status_code}: esta IP sigue "
                            f"bloqueada, hay que correrlo desde una conexion uruguaya")
    if r.status_code != 200:
        return False, 0.0, f"el robots.txt responde HTTP {r.status_code}"

    r.encoding = r.encoding or "utf-8"
    grupos = _parsear_robots(r.text)
    # nuestro nombre tiene prioridad sobre el grupo generico
    grupo = grupos.get(AGENTE.lower()) or grupos.get("*")
    if not grupo:
        return True, 0.0, "el robots.txt no fija reglas para nosotros"

    ruta = "/catalogo/"
    dis = _regla_mas_larga(grupo["disallow"], ruta)
    allw = _regla_mas_larga(grupo["allow"], ruta)
    demora = grupo["crawl_delay"] or 0.0

    if dis >= 0 and dis > allw:
        return False, demora, (f"el robots.txt de Diego no permite recorrer {ruta} "
                               f"(Disallow). No se lee nada.")
    return True, demora, "permitido por el robots.txt"


# ----------------------------------------------------------------------
# lectura del catalogo
# ----------------------------------------------------------------------
_demora = ESPERA_MIN


def _listar_urls():
    r = requests.get(SITEMAP, headers=HEADERS, timeout=90)
    r.raise_for_status()
    urls, vistos = [], set()
    for u in re.findall(r'<loc>([^<]+)</loc>', r.text):
        if "/catalogo/" not in u:
            continue
        partes = u.split("/catalogo/")[1].strip("/").split("/")
        if len(partes) < 2:
            continue
        raiz = partes[0].lower()
        if raiz not in CATEGORIAS or partes[-1] == "diego":
            continue
        u = u.replace("http://", "https://")
        if u in vistos:
            continue
        vistos.add(u)
        urls.append((u, raiz, "/".join(partes[1:-1])))
    return urls


def _ficha(args):
    url, raiz, sub = args
    for intento in range(3):
        try:
            r = requests.get(url, headers=HEADERS, timeout=40)
        except Exception:
            time.sleep(2 + intento * 3)
            continue
        time.sleep(_demora)
        if r.status_code == 404:
            return None
        if r.status_code == 403:
            # el sitio nos cerro la puerta a mitad de camino
            raise PermissionError(url)
        if r.status_code != 200:
            time.sleep(2 + intento * 3)
            continue
        r.encoding = "utf-8"
        for bloque in re.findall(r'<script[^>]*ld\+json[^>]*>(.*?)</script>', r.text, re.S):
            try:
                d = json.loads(bloque.strip())
            except Exception:
                continue
            if isinstance(d, dict) and d.get("@type") == "Product":
                d["_raiz"], d["_sub"], d["_url"] = raiz, sub, url
                return d
        return None
    return None


def _filas_desde_fichas(fichas):
    filas, publicados = [], 0
    for d in fichas:
        oferta = d.get("offers") or {}
        if isinstance(oferta, list):
            oferta = oferta[0] if oferta else {}
        if (oferta.get("priceCurrency") or "UYU").upper() != "UYU":
            continue
        try:
            precio = float(oferta.get("price") or 0)
        except (TypeError, ValueError):
            continue
        if precio <= 0:
            continue
        precio = round(precio * (1 + MARGEN))

        title = (d.get("name") or "").strip()
        sku = (d.get("sku") or "").strip()
        if not title:
            continue

        madre, sub = clasificar(d["_raiz"], d["_sub"])
        sub = unificar(sub)
        h = _handle(sku, d["_url"])

        desc = (d.get("description") or "").strip()
        lineas = [l.strip() for l in desc.split("\n") if l.strip()]
        body = ("<ul>" + "".join(f"<li>{l}</li>" for l in lineas) + "</ul>"
                if lineas else title)

        imgs = d.get("image") or []
        if isinstance(imgs, str):
            imgs = [imgs]
        hay_stock = "InStock" in (oferta.get("availability") or "")

        fila = {c: "" for c in COLS}
        fila.update({
            "Handle": h, "Title": title, "Body HTML": body,
            "Vendor": "Diego", "Type": madre,
            "Tags": ", ".join([t for t in [sub] +
                               (["stock-verificado"] if hay_stock else []) if t]),
            "Published": "TRUE",
            "Option1 Name": "Título", "Option1 Value": "Default Title",
            "Variant SKU": sku, "Variant Price": f"{precio}.00",
            "Variant Inventory Qty": "10" if hay_stock else "0",
            "Variant Inventory Policy": "deny",
        })
        if imgs:
            fila["Image Src"] = imgs[0]
            fila["Image Position"] = "1"
        filas.append(fila)
        publicados += 1
        for pos, u in enumerate(imgs[1:9], 2):
            filas.append({**{c: "" for c in COLS}, "Handle": h,
                          "Image Src": u, "Image Position": str(pos)})
    return filas, publicados


# ----------------------------------------------------------------------
# cache y git
# ----------------------------------------------------------------------
def escribir_cache(filas, publicados):
    os.makedirs("cache", exist_ok=True)
    with open(CACHE_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        w.writerows(filas)
    meta = {
        "fecha": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "productos": publicados,
        "filas": len(filas),
        "margen": MARGEN,
    }
    with open(CACHE_META, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    return meta


def subir(meta):
    """Commitea y sube el cache. Si no estamos en un clon del repo, avisa."""
    if not os.path.isdir(".git"):
        print("\n  No es un clon de git: el cache quedo escrito pero no se subio.")
        print("  Para habilitarlo:")
        print("    git clone https://github.com/directiva-edifica/edifica-sync.git")
        print("    cd edifica-sync && python3 diego_local.py --push")
        return False
    try:
        subprocess.run(["git", "add", "cache"], check=True)
        hay = subprocess.run(["git", "diff", "--cached", "--quiet"]).returncode != 0
        if not hay:
            print("  El cache no cambio: no hay nada que subir.")
            return True
        msg = (f"Diego: cache del {meta['fecha'][:10]} "
               f"({meta['productos']} productos)")
        subprocess.run(["git", "commit", "-m", msg], check=True)
        for intento in range(1, 4):
            if subprocess.run(["git", "push"]).returncode == 0:
                print("  Cache subido al repo.")
                return True
            print(f"  push falló (intento {intento}); reintento en 10s")
            time.sleep(10)
            subprocess.run(["git", "pull", "--rebase"])
        print("  No se pudo subir. Quedo commiteado: proba 'git push' a mano.")
        return False
    except subprocess.CalledProcessError as e:
        print(f"  Error de git: {e}")
        return False


def main():
    ap = argparse.ArgumentParser(description="Lee el catalogo de Diego desde esta Mac.")
    ap.add_argument("--push", action="store_true",
                    help="commitea y sube cache/diego.csv al repo")
    ap.add_argument("--limite", type=int, default=0,
                    help="leer solo N fichas (para probar)")
    args = ap.parse_args()

    global _demora
    print("Diego - lectura local\n")

    permitido, demora, motivo = permiso_robots()
    print(f"  robots.txt: {motivo}")
    if not permitido:
        print("\n  No se lee nada. Fin.")
        sys.exit(1)
    if demora:
        _demora = max(demora, ESPERA_MIN)
        print(f"  respetando Crawl-delay de {demora}s")

    print("\n  Leyendo el sitemap...")
    urls = _listar_urls()
    if not urls:
        print("  El sitemap no devolvio productos. Fin.")
        sys.exit(1)
    if args.limite:
        urls = urls[:args.limite]
    print(f"  {len(urls)} fichas para leer (con {HILOS} hilos, "
          f"{_demora}s entre pedidos)\n")

    fichas = []
    try:
        with ThreadPoolExecutor(max_workers=HILOS) as ex:
            for i, d in enumerate(ex.map(_ficha, urls), 1):
                if d:
                    fichas.append(d)
                if i % 250 == 0:
                    print(f"    {i}/{len(urls)} ({len(fichas)} con datos)")
    except PermissionError as e:
        print(f"\n  El sitio empezo a responder 403 (en {e}).")
        print("  Se corta para no insistir. El cache anterior queda intacto.")
        sys.exit(1)

    print(f"\n  {len(fichas)} fichas leidas de {len(urls)}")
    if len(fichas) < len(urls) * 0.5:
        print("  Menos de la mitad: no se sobreescribe el cache "
              "(mejor el de ayer que medio catalogo).")
        sys.exit(1)

    filas, publicados = _filas_desde_fichas(fichas)
    meta = escribir_cache(filas, publicados)
    print(f"  cache/diego.csv escrito: {publicados} productos, {len(filas)} filas")

    if args.push:
        subir(meta)
    else:
        print("\n  Para subirlo al repo: python3 diego_local.py --push")


if __name__ == "__main__":
    main()


# ----------------------------------------------------------------------
# PARA QUE CORRA SOLO TODAS LAS MANANAS (macOS)
# ----------------------------------------------------------------------
# Guardar esto como ~/Library/LaunchAgents/uy.edifica.diego.plist y
# despues: launchctl load ~/Library/LaunchAgents/uy.edifica.diego.plist
#
# <?xml version="1.0" encoding="UTF-8"?>
# <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
#   "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
# <plist version="1.0"><dict>
#   <key>Label</key>              <string>uy.edifica.diego</string>
#   <key>WorkingDirectory</key>   <string>/Users/TU_USUARIO/edifica-sync</string>
#   <key>ProgramArguments</key>
#     <array>
#       <string>/usr/bin/python3</string>
#       <string>diego_local.py</string>
#       <string>--push</string>
#     </array>
#   <key>StartCalendarInterval</key>
#     <dict><key>Hour</key><integer>7</integer><key>Minute</key><integer>0</integer></dict>
#   <key>StandardOutPath</key>    <string>/tmp/diego_local.log</string>
#   <key>StandardErrorPath</key>  <string>/tmp/diego_local.err</string>
# </dict></plist>
