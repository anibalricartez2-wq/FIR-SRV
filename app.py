import streamlit as st
import requests
import re
import random
import pandas as pd
from datetime import datetime, timezone
from streamlit_autorefresh import st_autorefresh

# --- 1. CONFIGURACIÓN ---
st.set_page_config(page_title="Vigilancia FIR SAVC", page_icon="✈️", layout="wide")

if 'historial_alertas' not in st.session_state:
    st.session_state.historial_alertas = []

hide_st_style = """
            <style>
            .stDeployButton {display:none;}
            footer {visibility: hidden;}
            .st-emotion-cache-1wbqy5l {display:none;}
            .block-container {padding-top: 1rem;}
            .copyright { text-align: center; color: #888; font-size: 0.8rem; margin-top: 50px; border-top: 1px solid #444; padding-top: 10px; }
            .taf-box { background-color: #f0f2f6; padding: 10px; border-radius: 5px; border-left: 5px solid #007bff; margin-bottom: 10px; }
            </style>
            """
st.markdown(hide_st_style, unsafe_allow_html=True)

# Refresco cada 30 minutos
st_autorefresh(interval=1800000, key="datarefresh")

API_KEY = "8e7917816866402688f805f637eb54d3"
AERODROMOS = ["SAVV","SAVE","SAVT","SAWC","SAVC","SAWG","SAWE","SAWH"]

# --- 2. LÓGICA DE PARSEO TEMPORAL ---

def obtener_periodo_vigente(taf_text):
    ahora_utc = datetime.now(timezone.utc)
    hora_actual = ahora_utc.hour
    dia_actual = ahora_utc.day
    
    # Dividimos el TAF por grupos de cambio
    partes = re.split(r'\b(FM|BECMG|TEMPO|PROB\d{2})\b', taf_text)
    vigente = partes[0] # Por defecto la base
    
    for i in range(1, len(partes), 2):
        indicador = partes[i]
        contenido = partes[i+1]
        # Buscamos el rango horario (ej: 2012/2014)
        match = re.search(r'(\d{2})(\d{2})/(\d{2})(\d{2})', contenido)
        if match:
            d_ini, h_ini, d_fin, h_fin = map(int, match.groups())
            if d_ini <= dia_actual <= d_fin:
                if h_ini <= hora_actual < h_fin:
                    vigente = f"{indicador} {contenido}"
    return vigente.strip()

def parse_viento(texto):
    match = re.search(r'\b(\d{3})(\d{2,3})(G\d{2,3})?KT\b', texto)
    return (int(match.group(1)), int(match.group(2)), int(match.group(3)[1:]) if match.group(3) else 0) if match else (None, None, None)

def parse_visibilidad(texto):
    if "CAVOK" in texto: return 9999
    match = re.search(r'\b(\d{4})\b', texto)
    return int(match.group(1)) if match else 9999

def parse_nubes(texto):
    capas = re.findall(r'\b(BKN|OVC)(\d{3})\b', texto)
    return min(int(c[1]) * 100 for c in capas) if capas else 9999

def extraer_fenos(texto):
    codigos = ["TS", "VA", "RA", "SN", "DZ", "FG", "BR", "HZ", "FU", "SQ", "FZRA"]
    palabras = texto.split()
    return set(p for p in palabras if any(c in p.replace("+","").replace("-","") for c in codigos) and len(p) <= 5)

def auditar(icao, metar, taf_completo):
    periodo = obtener_periodo_vigente(taf_completo)
    enmiendas = []
    
    # Datos para comparar
    dr, vr, gr = parse_viento(metar)
    dt, vt, gt = parse_viento(periodo)
    vm, vt_vis = parse_visibilidad(metar), parse_visibilidad(periodo)
    nm, nt = parse_nubes(metar), parse_nubes(periodo)
    fm, ft = extraer_fenos(metar), extraer_fenos(periodo)

    # Viento (Giro 60° o Int 10kt)
    if vr is not None and vt is not None:
        if (vr >= 10 or vt >= 10) and abs(dr - dt) >= 60: enmiendas.append(f"VIENTO: Giro >= 60°")
        if abs(vr - vt) >= 10: enmiendas.append(f"VIENTO: Dif. Vel. >= 10kt")
    
    # Visibilidad (Umbrales SMN)
    for u in [150, 350, 600, 800, 1500, 3000, 5000]:
        if (vm <= u < vt_vis) or (vt_vis <= u < vm):
            enmiendas.append(f"VIS: Pasó umbral {u}m")
            break

    # Techos
    for u in [100, 200, 500, 1000, 1500]:
        if (nm <= u < nt) or (nt <= u < nm):
            enmiendas.append(f"NUBES: Techo pasó {u}ft")
            break

    # Fenómenos
    cambios = fm.symmetric_difference(ft)
    if cambios:
        for c in cambios:
            enmiendas.append(f"FENÓMENO: Cambio en {c}")

    return enmiendas, periodo

# --- 3. INTERFAZ ---
st.title("🖥️ Monitor FIR SAVC - Vigilancia por Periodo")

cols = st.columns(2)
headers = {"X-API-Key": API_KEY}

for i, icao in enumerate(AERODROMOS):
    try:
        r_hash = random.randint(1, 999999)
        m_raw = requests.get(f"https://api.checkwx.com/metar/{icao}?cache={r_hash}", headers=headers).json().get('data',['-'])[0]
        t_raw = requests.get(f"https://api.checkwx.com/taf/{icao}?cache={r_hash}", headers=headers).json().get('data',['-'])[0]
        
        if m_raw != '-' and t_raw != '-':
            alertas, periodo_v = auditar(icao, m_raw, t_raw)
            estado = "⚠️ ENMIENDA" if alertas else "✅ OK"
            
            with cols[i % 2]:
                with st.expander(f"{icao} - {estado}", expanded=True):
                    # T
