"""
Combina todas las fuentes en un unico CSV (mega-CSV) para Matrixify.
Red de seguridad: si una fuente falla o viene vacia, se reutiliza
el respaldo de la corrida anterior de esa fuente, para no borrar
productos en Shopify por un error puntual.
"""

import csv, os, sys, importlib

# Lista de fuentes activas. Para sumar una tienda nueva:
# crear fuentes/nombre.py con una funcion obtener() y agregarla aca.
FUENTES = [
    "joacamar",
]

COLS = ["Handle", "Title", "Body HTML", "Vendor", "Type", "Tags", "Published",
        "Option1 Name", "Option1 Value", "Variant SKU", "Variant Price",
        "Variant Compare At Price", "Variant Inventory Qty",
        "Variant Inventory Policy", "Image Src", "Image Position"]

BACKUP_DIR = "respaldos"
SALIDA = "edifica_todos.csv"


def guardar_csv(path, filas):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        w.writerows(filas)


def leer_csv(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def main():
    os.makedirs(BACKUP_DIR, exist_ok=True)
    todas_las_filas = []
    hubo_error = False

    for nombre in FUENTES:
        backup = os.path.join(BACKUP_DIR, f"{nombre}.csv")
        try:
            mod = importlib.import_module(f"fuentes.{nombre}")
            filas, n = mod.obtener()
            if not filas:
                raise RuntimeError("sin filas")
            guardar_csv(backup, filas)  # respaldo fresco
            todas_las_filas.extend(filas)
            print(f"OK {nombre}: {n} productos, {len(filas)} filas")
        except Exception as e:
            hubo_error = True
            print(f"ERROR en {nombre}: {e}")
            if os.path.exists(backup):
                filas = leer_csv(backup)
                todas_las_filas.extend(filas)
                print(f"  -> uso respaldo anterior de {nombre}: {len(filas)} filas")
            else:
                print(f"  -> sin respaldo de {nombre}, se omite esta fuente")

    guardar_csv(SALIDA, todas_las_filas)
    print(f"\nMEGA-CSV generado: {SALIDA} ({len(todas_las_filas)} filas totales)")

    # Si TODAS las fuentes fallaron y no hay nada, salir con error
    if not todas_las_filas:
        print("Nada que subir. Abortando.")
        sys.exit(1)


if __name__ == "__main__":
    main()
