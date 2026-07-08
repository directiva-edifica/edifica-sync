"""
Unificacion de subcategorias entre tiendas.
Refrigeradores (Uruimporta) y Heladeras (Joacamar) quedan bajo
la MISMA subcategoria. Lo que no este en la tabla se deja igual.
"""

UNIFICAR = {
    "Refrigeradores": "Heladeras",
    "Lavadoras, Secadoras": "Lavarropas",
    "Cocinas, Hornos": "Cocinas",
    "Televisores Smart TV": "TV",
    "Audio, Proyectores": "Audio",
    "Informática": "Tecnología",
    "Celulares, Tablets, Notebooks": "Tecnología",
    "Relojes – Teléfonos": "Tecnología",
    "Canillas – Grifos": "Grifería",
    "GRIFERÍA": "Grifería",
    "Accesorios Autos": "Accesorios Auto",
    "Auto": "Accesorios Auto",
}


def unificar(subcategoria):
    if not subcategoria:
        return subcategoria
    return UNIFICAR.get(subcategoria.strip(), subcategoria.strip())
