# -*- coding: utf-8 -*-
import re
from unidecode import unidecode
from collections import defaultdict

def normalize_street(raw_name: str) -> str:
    """
    Quita puntuación y acentos, unifica abreviaturas y espacios:
    'Avda. Independencia' → 'independencia'
    """
    # 1. minúsculas
    s = raw_name.lower()
    # 2. quitar tildes/caracteres especiales
    s = unidecode(s)
    # 3. eliminar puntuación
    s = re.sub(r'[^\w\s]', '', s)
    # 4. eliminar prefijos comunes
    s = re.sub(r'^(calle|avda\.?|avenida|plaza|pza)\s+', "", s)
    # 5. colapsar espacios
    s = re.sub(r'\s+', ' ', s).strip()
    return s

def group_by_street(incidences):
    buckets = defaultdict(list)
    for inc in incidences:
        # primero intentamos la versión acentuada, si no existe usamos la sin acento
        loc = inc.get("Ubicación", inc.get("Ubicacion", ""))
        street_raw = loc.split(",")[0]
        norm = normalize_street(street_raw)
        buckets[norm].append(inc)

    result = []
    for street, items in buckets.items():
        if len(items) >= 2:
            result.append({
                "street": street,
                "incidencias": items,
                "count": len(items)
            })
    return result