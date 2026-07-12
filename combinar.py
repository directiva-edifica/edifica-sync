"""
Combina todas las fuentes en un unico CSV (mega-CSV) para Matrixify.
Red de seguridad: si una fuente falla, reutiliza el respaldo anterior.
"""
import csv, os, sys, importlib

FUENTES = [
    "joacamar",
    "uruimporta",
    "midea",
    "miuruguay",
    "consul",
    "ltienda",
    "vstore",
    "fymelco",
]

COLS = ["Handle","Title","Body HTML","Vendor","Type","Tags","Published",
        "Option1 Name","Option1 Value","Variant SKU","Variant Price",
        "Variant Compare At Price","Variant Inventory Qty",
        "Variant Inventory Policy","Image Src","Image Position"]

BACKUP_DIR = "respaldos"
SALIDA = "edifica_todos.csv"

def guardar_csv(path, filas):
    with open(path,"w",newline="",encoding="utf-8-sig") as f:
        w=csv.DictWriter(f,fieldnames=COLS); w.writeheader(); w.writerows(filas)

def leer_csv(path):
    with open(path,newline="",encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))

def main():
    os.makedirs(BACKUP_DIR,exist_ok=True)
    todas=[]
    for nombre in FUENTES:
        backup=os.path.join(BACKUP_DIR,f"{nombre}.csv")
        try:
            mod=importlib.import_module(f"fuentes.{nombre}")
            filas,n=mod.obtener()
            if not filas: raise RuntimeError("sin filas")
            guardar_csv(backup,filas)
            todas.extend(filas)
            print(f"OK {nombre}: {n} productos, {len(filas)} filas")
        except Exception as e:
            print(f"ERROR en {nombre}: {e}")
            if os.path.exists(backup):
                filas=leer_csv(backup); todas.extend(filas)
                print(f"  -> uso respaldo anterior de {nombre}: {len(filas)} filas")
            else:
                print(f"  -> sin respaldo de {nombre}, se omite")
    guardar_csv(SALIDA,todas)
    print(f"\nMEGA-CSV generado: {SALIDA} ({len(todas)} filas totales)")
    if not todas:
        print("Nada que subir. Abortando."); sys.exit(1)

if __name__=="__main__":
    main()
