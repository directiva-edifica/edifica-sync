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
"""
import csv, os, sys, importlib

FUENTES = [
    "joacamar", "uruimporta", "midea", "miuruguay", "consul",
    "ltienda", "vstore", "fymelco", "enko", "iluminica", "gelbring", "beko", "vivion", "mvdindustrial",
]

COLS = ["Handle","Title","Body HTML","Vendor","Type","Tags","Published",
        "Option1 Name","Option1 Value","Variant SKU","Variant Price",
        "Variant Compare At Price","Variant Inventory Qty",
        "Variant Inventory Policy","Image Src","Image Position",
        "Status","Command"]

BACKUP_DIR = "respaldos"
SALIDA = "edifica_todos.csv"
UMBRAL_PROTECCION = 0.70  # si hoy trae < 70% de ayer, no da de baja nada

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

            guardar_csv(backup, filas)  # respaldo fresco (sin las bajas)
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
                todas.extend(filas)
                print(f"  -> uso respaldo anterior de {nombre}: {len(filas)} filas")
            else:
                print(f"  -> sin respaldo de {nombre}, se omite")

    guardar_csv(SALIDA, todas)
    print(f"\nMEGA-CSV generado: {SALIDA} ({len(todas)} filas totales)")
    if bajas_totales:
        print(f"TOTAL dados de baja hoy: {bajas_totales} productos")
    if not todas:
        print("Nada que subir. Abortando.")
        sys.exit(1)

if __name__ == "__main__":
    main()
