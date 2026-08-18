"""
Combina todas las fuentes en un unico CSV (mega-CSV) para Matrixify.

Red de seguridad: si una fuente falla o viene vacia, se reutiliza el
respaldo de la corrida anterior, para no borrar productos por un error.

Baja automatica: si un producto estaba en la corrida anterior (respaldo)
y hoy ya no aparece en la fuente, se agrega al CSV con Status=draft para
que Matrixify lo pase a BORRADOR (no visible, pero no se borra; si el
producto vuelve al feed, la corrida siguiente lo reactiva solo).
Proteccion: si una fuente hoy trae menos del 70% de lo que traia antes,
se asume que fallo y NO se da de baja nada de esa fuente ese dia.

Conversion de moneda: los proveedores entregan precios en USD. La tienda
Shopify tiene su moneda base en UYU (pesos), porque dLocal solo procesa
pagos en pesos. Por eso, apenas se obtienen los precios de cada fuente
(en USD), se convierten a UYU usando la cotizacion del dia ANTES de
guardarlos en el respaldo o en el mega-CSV. De esta forma, tanto el CSV
final como los respaldos quedan siempre expresados en pesos, listos
para subir a Shopify tal cual.

Registro de cotizacion: cada corrida deja constancia en
'respaldos/historial_cotizacion.csv' de si se pudo usar la API de
cotizacion o si se tuvo que reutilizar la ultima conocida, junto con el
valor exacto usado. Sirve para detectar si el dolar se esta
desactualizando (por ejemplo, varios dias seguidos usando respaldo).
"""
import csv, os, sys, importlib, requests
from datetime import datetime, timezone

FUENTES = [
    "joacamar", "uruimporta", "midea", "miuruguay", "consul",
    "ltienda", "vstore", "fymelco", "enko", "iluminica", "beko", "vivion", "mvdindustrial",
]

COLS = ["Handle","Title","Body HTML","Vendor","Type","Tags","Published",
        "Option1 Name","Option1 Value","Variant SKU","Variant Price",
        "Variant Compare At Price","Variant Inventory Qty",
        "Variant Inventory Policy","Image Src","Image Position",
        "Status","Command"]

BACKUP_DIR = "respaldos"
SALIDA = "edifica_todos.csv"
UMBRAL_PROTECCION = 0.70  # si hoy trae < 70% de ayer, no da de baja nada

COTIZACION_URL = "https://uy.dolarapi.com/v1/cotizaciones/usd"
COTIZACION_RESPALDO = os.path.join(BACKUP_DIR, "ultima_cotizacion.txt")
HISTORIAL_COTIZACION = os.path.join(BACKUP_DIR, "historial_cotizacion.csv")


def registrar_historial_cotizacion(origen, cotizacion, detalle=""):
    """
    Agrega una linea al historial persistente de cotizaciones, para poder
    revisar despues (incluso dias mas tarde) si un dia en particular se
    uso la API o el respaldo, y que valor se aplico.
    """
    existe = os.path.exists(HISTORIAL_COTIZACION)
    with open(HISTORIAL_COTIZACION, "a", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        if not existe:
            w.writerow(["Fecha y hora (UTC)", "Origen", "Cotizacion usada", "Detalle"])
        w.writerow([
            datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
            origen,
            cotizacion,
            detalle,
        ])


def obtener_cotizacion_dolar():
    """
    Devuelve la cotizacion de venta del dolar en pesos uruguayos.
    Si la API falla, reutiliza la ultima cotizacion guardada para no
    frenar todo el sync ni publicar precios en cero.
    Deja constancia en el historial de cual de los dos casos ocurrio.
    """
    try:
        resp = requests.get(COTIZACION_URL, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        cotizacion = float(data["venta"])
        if cotizacion <= 0:
            raise ValueError("cotizacion invalida (<= 0)")

        # guarda la cotizacion de hoy para usarla como respaldo si mañana falla la API
        with open(COTIZACION_RESPALDO, "w") as f:
            f.write(str(cotizacion))

        registrar_historial_cotizacion("API", cotizacion, "dolarapi.com respondio correctamente")
        return "API", cotizacion

    except Exception as e:
        print(f"ERROR obteniendo cotizacion del dolar: {e}")
        if os.path.exists(COTIZACION_RESPALDO):
            with open(COTIZACION_RESPALDO) as f:
                cotizacion = float(f.read().strip())
            registrar_historial_cotizacion(
                "RESPALDO", cotizacion, f"Fallo la API ({e}); se reutilizo la ultima cotizacion conocida"
            )
            return "RESPALDO", cotizacion
        else:
            registrar_historial_cotizacion(
                "SIN DATOS", "", f"Fallo la API ({e}) y no hay respaldo previo. Sync abortado."
            )
            print("  -> sin cotizacion de respaldo disponible. Abortando.")
            sys.exit(1)


def convertir_precios_a_pesos(filas, cotizacion):
    """
    Convierte Variant Price y Variant Compare At Price de USD a UYU,
    multiplicando por la cotizacion del dia. Redondea a numero entero
    de pesos (sin centavos), que es como se maneja el precio en Uruguay.
    """
    for fila in filas:
        for campo in ("Variant Price", "Variant Compare At Price"):
            valor = fila.get(campo, "").strip()
            if not valor:
                continue
            try:
                usd = float(valor)
                pesos = round(usd * cotizacion)
                fila[campo] = f"{pesos}.00"
            except ValueError:
                # si el valor no es un numero valido, se deja como estaba
                continue
    return filas


def guardar_csv(path, filas):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        for fila in filas:
            w.writerow({c: fila.get(c, "") for c in COLS})

def leer_csv(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))

def handles_de(filas):
    """Handles unicos de productos (filas con Title, no las de solo-imagen)."""
    return set(f.get("Handle", "").strip() for f in filas
              if f.get("Handle", "").strip() and f.get("Title", "").strip())

def main():
    os.makedirs(BACKUP_DIR, exist_ok=True)
    origen_cotizacion, cotizacion = obtener_cotizacion_dolar()

    todas = []
    bajas_totales = 0

    for nombre in FUENTES:
        backup = os.path.join(BACKUP_DIR, f"{nombre}.csv")
        # handles que habia en la corrida anterior (para detectar bajas)
        handles_anteriores = set()
        if os.path.exists(backup):
            try:
                handles_anteriores = handles_de(leer_csv(backup))
            except Exception:
                handles_anteriores = set()

        try:
            mod = importlib.import_module(f"fuentes.{nombre}")
            filas, n = mod.obtener()
            if not filas:
                raise RuntimeError("sin filas")

            # --- conversion USD -> UYU, apenas se obtienen los datos crudos ---
            filas = convertir_precios_a_pesos(filas, cotizacion)

            handles_hoy = handles_de(filas)

            # --- deteccion de bajas ---
            desaparecidos = handles_anteriores - handles_hoy
            bajas = []
            if desaparecidos and handles_anteriores:
                ratio = len(handles_hoy) / max(len(handles_anteriores), 1)
                if ratio >= UMBRAL_PROTECCION:
                    for h in desaparecidos:
                        bajas.append({"Handle": h, "Status": "draft", "Command": "UPDATE"})
                    print(f"OK {nombre}: {n} productos, {len(filas)} filas "
                          f"| {len(bajas)} dados de baja (borrador)")
                    bajas_totales += len(bajas)
                else:
                    print(f"OK {nombre}: {n} productos, {len(filas)} filas "
                          f"| PROTECCION: trajo {ratio*100:.0f}% de lo habitual, "
                          f"no se da de baja nada ({len(desaparecidos)} faltantes ignorados)")
            else:
                print(f"OK {nombre}: {n} productos, {len(filas)} filas")

            guardar_csv(backup, filas)  # respaldo fresco (sin las bajas), ya en pesos
            # marcar Status=active en las filas de producto (para que un
            # producto que revive vuelva a estar visible automaticamente)
            for f in filas:
                if f.get("Title", "").strip():
                    f["Status"] = "active"
            todas.extend(filas)
            todas.extend(bajas)         # las bajas van al mega-CSV pero no al respaldo

        except Exception as e:
            print(f"ERROR en {nombre}: {e}")
            if os.path.exists(backup):
                filas = leer_csv(backup)
                # el respaldo ya esta en pesos (se convirtio la vez que se guardo),
                # asi que NO se vuelve a convertir aca para no duplicar la conversion
                todas.extend(filas)
                print(f"  -> uso respaldo anterior de {nombre}: {len(filas)} filas")
            else:
                print(f"  -> sin respaldo de {nombre}, se omite")

    guardar_csv(SALIDA, todas)

    # --- resumen final, bien visible, con lo mas importante arriba de todo ---
    print("\n" + "=" * 60)
    print("RESUMEN DE COTIZACION USADA HOY")
    print("=" * 60)
    if origen_cotizacion == "API":
        print(f"Origen: API (dolarapi.com) - cotizacion obtenida con exito")
    else:
        print(f"Origen: RESPALDO - la API fallo, se reutilizo la ultima cotizacion conocida")
        print(f"ATENCION: revisar si dolarapi.com esta funcionando correctamente")
    print(f"Cotizacion aplicada a todos los precios de hoy: $ {cotizacion} UYU por USD")
    print(f"Historial completo disponible en: {HISTORIAL_COTIZACION}")
    print("=" * 60)

    print(f"\nMEGA-CSV generado: {SALIDA} ({len(todas)} filas totales)")
    if bajas_totales:
        print(f"TOTAL dados de baja hoy: {bajas_totales} productos")
    if not todas:
        print("Nada que subir. Abortando.")
        sys.exit(1)

if __name__ == "__main__":
    main()
