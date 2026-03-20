# --- CONFIGURACIÓN DE CRITERIOS DE ENMIENDA (SMN ARGENTINA) ---

# Umbrales de visibilidad en metros
VIS_THRESHOLDS = [150, 350, 600, 800, 1500, 3000, 5000]

# Umbrales de techo de nubes (BKN/OVC) y visibilidad vertical en pies
CEILING_THRESHOLDS = [100, 200, 500, 1000, 1500]

# Fenómenos significativos que requieren enmienda inmediata
# Se dispara si inician, terminan o cambian de intensidad
SIG_PHENOMENA = [
    'TS', 'GR', 'RA', 'SN', 'DZ', 'FG', 'FC', 'SS', 'DS', 'SQ', 'VA'
]

def check_amendment_criteria(taf, metar):
    """
    Compara un TAF (pronóstico) contra un METAR (realidad).
    Retorna una lista de alertas si se cumplen los criterios de enmienda.
    """
    alerts = []

    # 1. VIENTO
    # Cambio en dirección >= 60° con velocidad >= 10kt
    dir_diff = abs(taf['wind_dir'] - metar['wind_dir'])
    if dir_diff >= 60 and (taf['wind_speed'] >= 10 or metar['wind_speed'] >= 10):
        alerts.append(f"VIENTO: Cambio de dirección de {dir_diff}° (Umbral 60° con >10kt)")

    # Cambio en velocidad media >= 10kt
    if abs(taf['wind_speed'] - metar['wind_speed']) >= 10:
        alerts.append(f"VIENTO: Variación de velocidad media >= 10kt")

    # Variación de ráfagas (Gusts) >= 10kt con media >= 15kt
    if abs(taf['wind_gust'] - metar['wind_gust']) >= 10:
        if taf['wind_speed'] >= 15 or metar['wind_speed'] >= 15:
            alerts.append(f"VIENTO: Variación de ráfagas >= 10kt con viento medio >= 15kt")

    # 2. VISIBILIDAD HORIZONTAL
    # Cruce de umbrales operativos
    for limit in VIS_THRESHOLDS:
        if (taf['vis'] < limit <= metar['vis']) or (taf['vis'] >= limit > metar['vis']):
            alerts.append(f"VISIBILIDAD: Cruzó umbral de {limit}m")

    # 3. NUBOSIDAD (TECHO BKN/OVC)
    # Cruce de umbrales de altura
    for limit in CEILING_THRESHOLDS:
        if (taf['ceiling_alt'] < limit <= metar['ceiling_alt']) or \
           (taf['ceiling_alt'] >= limit > metar['ceiling_alt']):
            alerts.append(f"NUBES: Techo cruzó umbral de {limit}ft")

    # Cambio de cobertura (SCT/FEW a BKN/OVC o viceversa) bajo 1500ft
    if metar['ceiling_alt'] <= 1500 or taf['ceiling_alt'] <= 1500:
        if (taf['is_broken_overcast'] != metar['is_broken_overcast']):
            alerts.append("NUBES: Cambio de cobertura (SCT/FEW <-> BKN/OVC) bajo 1500ft")

    # 4. FENÓMENOS
    # Compara si el fenómeno cambió (simplificado a presencia/ausencia)
    for phenom in SIG_PHENOMENA:
        in_taf = phenom in taf['weather']
        in_metar = phenom in metar['weather']
        if in_taf != in_metar:
            status = "Inicia" if in_metar else "Termina"
            alerts.append(f"FENÓMENO: {status} {phenom}")

    return alerts

# --- EJEMPLO DE USO ---
taf_ejemplo = {
    'wind_dir': 120, 'wind_speed': 5, 'wind_gust': 0,
    'vis': 6000, 'ceiling_alt': 2000, 'is_broken_overcast': False,
    'weather': []
}

metar_ejemplo = {
    'wind_dir': 190, 'wind_speed': 12, 'wind_gust': 0, # Cambio > 60° y > 10kt
    'vis': 1200, 'ceiling_alt': 800, # Cruzó 1500m y 1000ft
    'is_broken_overcast': True,
    'weather': ['RA'] # Inicia lluvia
}

resultados = check_amendment_criteria(taf_ejemplo, metar_ejemplo)

if resultados:
    print("ALERTA DE ENMIENDA REQUERIDA:")
    for a in resultados:
        print(f"- {a}")
else:
    print("Condiciones dentro de parámetros.")
