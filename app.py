import streamlit as st
import requests
import re
import random
import pandas as pd
from datetime import datetime, timezone
from streamlit_autorefresh import st_autorefresh

# --- 1. CONFIGURACIÓN ---
st.set_page_config(page_title="Vigilancia FIR SAVC - v3.0", page_icon="✈️", layout="wide")

if 'historial_alertas' not in st.session_state:
    st.session_state.historial_alertas = []

hide_st_style = """
            <style>
            .stDeployButton {display:none;}
            footer {visibility: hidden;}
            .st-emotion-cache-1wbqy5l {display:none;}
            .block-container {padding-top: 1rem;}
            .copyright { text-align: center; color: #888; font-size: 0.8rem; margin-top: 50px; border-top: 1px solid #444; padding-top: 10px; }
            </style>
            """
st.markdown(hide_st_style, unsafe_allow_html=True)

st_autorefresh(interval=1800000, key="datarefresh")

API_KEY = "8e7917816866402688f805f637eb54d3"
AERODROMOS = ["SAVV","SAVE","SAVT","SAWC","SAVC","SAWG","SAWE","SAWH"]

# --- 2. MOTOR DE PROCESAMIENTO TAF (NUEVA LÓGICA SECUENCIAL) ---

def extraer_grupos_taf(taf_text):
    """Divide el TAF en bloques lógicos respetando el orden cronológico"""
    # Limpiamos el texto y eliminamos el encabezado OACI/Fecha
    taf_clean = re.sub(r'^(TAF\s+)?([A-Z]{4})\s+\d{6}Z\s+', '', taf_text)
    
    # Buscamos los índices de cada indicador de cambio
    indices = [(m.start(), m.group()) for m in re.finditer(r'\b(FM|BECMG|TEMPO|PROB\d{2})\b', taf_clean)]
    
    bloques = []
    inicio_base = 0
    
    if not indices:
        return [{"tipo": "BASE", "contenido": taf_clean}]

    # El primer bloque es siempre la BASE (desde el inicio hasta el primer indicador)
    bloques.append({"tipo": "BASE", "contenido": taf_clean[:indices[0][0]].strip()})
    
    # Extraemos el resto de los bloques
    for i in range(len(indices)):
        start_pos = indices[i][0]
        end_pos = indices[i+1][0] if i+1 < len(indices) else len(taf_clean)
        tipo = indices[i][1]
        contenido = taf_clean[start_pos:end_pos].strip()
        bloques.append({"tipo": tipo, "contenido": contenido})
    
    return bloques

def obtener_periodo_activo(taf_text):
    """Determina qué parte del TAF manda ahora mismo basado en UTC"""
    ahora_utc = datetime.now(timezone.utc)
    hora_actual = ahora_utc.hour
    dia_actual = ahora_utc.day
    minuto_actual = ahora_utc.minute
    tiempo_ref = dia_actual * 10000 + hora_actual * 100 + minuto_actual

    bloques = extraer_grupos_taf(taf_text)
    periodo_dominante = bloques[0]["contenido"] # Empezamos con la BASE

    for b in bloques[1:]:
        # Buscamos el rango horario ej: 2012/2018 o 201200
        match_rango = re.search(r'(\d{2})(\d{2})/(\d{2})(\d{2})', b["contenido"])
        match_fm = re.search(r'FM(\d{2})(\d{2})(\d{2})', b["contenido"])
        
        valido = False
        if match_rango:
            d_i, h_i, d_f, h_f = map(int, match_rango.groups())
            inicio = d_i * 10000 + h_i * 100
            fin = d_f * 10000 + h_f * 100
            if inicio <= tiempo_ref < fin:
                valido = True
        elif match_fm:
            d_i, h_i, m_i = map(int, match_fm.groups())
            inicio = d_i * 10000 + h_i * 100 + m_i
            if tiempo_ref >= inicio:
                valido = True

        if valido:
            # Si es FM o BECMG, este bloque se convierte en la nueva base
            if b["tipo"] in ["FM", "BECMG"]:
                periodo_dominante = b["contenido"]
            # Si es TEMPO, solo lo tomamos si estamos en ese horario exacto
            elif b["tipo"] == "TEMPO":
                periodo_dominante = b["contenido"]

    return periodo_dominante

# --- 3. AUDITORÍA Y CRITERIOS SMN ---

def parse_val(texto, regex, mult=1):
    m = re.search(regex, texto)
    return int(m.group(1)) * mult if m else 9999

def auditar_estricto(icao, metar, taf_completo):
    periodo = obtener_periodo_activo(taf_completo)
    enmiendas = []
    
    # 1. Visibilidad (Umbrales SMN)
    def get_vis(t):
        if "CAVOK" in t: return 9999
        m = re.search(r'\b(\d{4})\b', t)
        return int(m.group(1)) if m else 9999
    
    vm, vp = get_vis(metar), get_vis(periodo)
    for u in [150, 350, 600, 800, 1500, 3000, 5000]:
        if (vm < u <= vp) or (vp < u <= vm):
            enmiendas.append(f"VIS: Cruzó umbral {u}m")
            break

    # 2. Techos (BKN/OVC)
    def get_ceiling(t):
        capas = re.findall(r'\b(BKN|OVC)(\d{3})\b', t)
        return min(int(c[1]) * 100 for c in capas) if capas else 9999
    
    nm, np = get_ceiling(metar), get_ceiling(periodo)
    for u in [100, 200, 500, 1000, 1500]:
        if (nm < u <= np) or (np < u <= nm):
            enmiendas.append(f"NUBES: Techo cruzó {u}ft")
            break

    # 3. Viento
    def get_wind(t):
        m = re.search(r'\b(\d{3})(\d{2,3})(G\d{2,3})?KT\b', t)
        return (int(m.group(1)), int(m.group(2)), int(m.group(3)[1:]) if m.group(3) else 0) if m else (None, None, None)
    
    dr, vr, gr = get_wind(metar)
    dt, vt, gt = get_wind(periodo)
    if vr is not None and vt is not None:
        if (vr >= 10 or vt >= 10) and abs(dr - dt) >= 60: enmiendas.append("VIENTO: Giro >= 60°")
        if abs(vr - vt) >= 10: enmiendas.append("VIENTO: Dif. Vel. media >= 10kt")

    return enmiendas, periodo

# --- 4. INTERFAZ ---
st.
