# --- PARÁMETROS OFICIALES DE ENMIENDA (SMN ARGENTINA) ---

# Umbrales de visibilidad en metros
VIS_THRESHOLDS = [150, 350, 600, 800, 1500, 3000, 5000]

# Umbrales de altura (Nubes BKN/OVC y Visibilidad Vertical) en pies
HEIGHT_THRESHOLDS = [100, 200, 500, 1000, 1500]

# Fenómenos que requieren enmienda inmediata
SIG_PHENOMENA = ['TS', 'GR', 'RA', 'SN', 'DZ', 'FG', 'FC', 'SS', 'DS', 'SQ', 'VA']

def check_amendment_criteria(taf, metar):
    """
    Compara el pronóstico (TAF) contra la realidad (METAR)
    y devuelve una lista con los motivos de enmienda encontrados.
    """
    alerts = []

    # 1. VALIDACIÓN DE VIENTO
    # Cambio de dirección >= 60° con velocidad >= 10kt
    dir_diff = abs(taf['w_dir'] - metar['w_dir'])
    if dir_diff >= 60 and (taf['w_spd'] >= 10 or metar['w_spd'] >= 10):
        alerts.append(f"VIENTO: Cambio de dirección de {dir_diff}° (Umbral 60° con >10kt)")

    # Cambio de velocidad media >= 10kt
    if abs(taf['w_spd'] - metar['w_spd']) >= 10:
        alerts.append(f"VIENTO: Cambio de intensidad media >= 10kt")

    # Variación de ráfagas >= 10kt si la media es >= 15kt
    if abs(taf['w_gst'] - metar['w_gst']) >= 10:
        if taf['w_spd'] >= 15 or metar['w_spd'] >= 15:
            alerts.append(f"VIENTO: Ráfaga varió >= 10kt con viento medio >= 15kt")

    # 2. VALIDACIÓN DE VISIBILIDAD
    for limit in VIS_THRESHOLDS:
        # Detecta si la visibilidad cruzó (subió o bajó) un umbral
        if (taf['vis'] < limit <= metar['vis']) or (taf['vis'] >= limit > metar['vis']):
            alerts.append(f"VISIBILIDAD: Cruzó el umbral crítico de {limit}m")

    # 3. VALIDACIÓN DE NUBES Y VISIBILIDAD VERTICAL
    for limit in HEIGHT_THRESHOLDS:
        # Detecta si el techo (BKN/OVC) cruzó un umbral
        if (taf['ceil'] < limit <= metar['ceil']) or (taf['ceil'] >= limit > metar['ceil']):
            alerts.append(f"NUBES/VV: La base de la capa cruzó los {limit}ft")

    # Cambio de cobertura (de pocas a muchas o viceversa) bajo 1500ft
    if (taf['ceil'] <= 1500 or metar['ceil'] <= 1500):
        if taf['is_bkn_ovc'] != metar['is_bkn_ovc']:
            alerts.append("NUBES: Cambio de cobertura (SCT/FEW <-> BKN/OVC) bajo 1500ft")

    # 4. FENÓMENOS SIGNIFICATIVOS
    for p in SIG_PHENOMENA:
        if (p in taf['wx']) != (p in metar['wx']):
            accion = "Inicia" if p in metar['wx'] else "Termina"
            alerts.append(f"FENÓMENO: {accion} {p}")

    return alerts

# --- BLOQUE DE PRUEBA (ESTO ES LO QUE SE MOSTRARÁ EN PANTALLA) ---

# Simulamos un TAF vigente
taf_actual = {
    'w_dir': 100, 'w_spd': 5, 'w_gst': 0,
    'vis': 5000, 'ceil': 2000, 'is_bkn_ovc': False,
    'wx': []
}

# Simulamos un METAR que acaba de salir y rompe los criterios
metar_nuevo = {
    'w_dir': 170, 'w_spd': 15, 'w_gst': 0, # Cambio > 60° y > 10kt
    'vis': 800, 'ceil': 400,              # Bajó de 1500m y de 500ft
    'is_bkn_ovc': True,                   # Pasó a estar nublado
    'wx': ['RA', 'TS']                    # Empezó a llover y tormenta
}

print("--- COMPROBACIÓN DE ENMIENDA TAF ---")
motivos = check_amendment_criteria(taf_actual, metar_nuevo)

if motivos:
    print(f"SE REQUIERE ENMIENDA. Motivos ({len(motivos)}):")
    for m in motivos:
        print(f" -> {m}")
else:
    print("No se requiere enmienda. Las condiciones están dentro de los parámetros.")
