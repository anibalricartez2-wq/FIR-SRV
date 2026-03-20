import streamlit as st
import requests
import re
import random
import pandas as pd
from datetime import datetime, timezone
from streamlit_autorefresh import st_autorefresh

# --- 1. CONFIGURACIÓN Y ESTILOS ---
st.set_page_config(page_title="Vigilancia SAVC v5.1", page_icon="✈️", layout="wide")

# Selector de Pantalla en barra lateral
layout_choice = st.sidebar.radio("Disposición de Pantalla:", ["Ancho (Filtro total)", "Centrado (Lectura)"])
if layout_choice == "Centrado (Lectura)":
    st.markdown("""<style>.block-container {max-width: 900px;}</style>""", unsafe_allow_html=True)

if 'log_alertas' not in st.session_state:
    st.session_state.log_alertas = []

# Ocultar elementos de Streamlit y definir pie de página
st.markdown("""
    <style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    .stDeployButton {display:none;}
    .reportview-container .main .block-container {padding-top: 1rem;}
    </style>
""", unsafe_allow_html=True)

st_autorefresh(interval=1800000, key="auto_refresh")

API_KEY = "8e7917816866402688f805f637eb54d3"
AERODROMOS = ["SAVV","SAVE","SAVT","SAWC","SAVC","SAWG","SAWE","SAWH"]

# --- 2. MOTOR DE PARSEO (FILTRO DE TOKENS) ---

def get_token_vis(texto):
    """Halla la visibilidad ignorando grupos de tiempo (/) o (Z)"""
    if any(x in texto for x in ["CAVOK", "SKC", "NSC", "CLR"]): return 9999
    tokens = texto.split()
    for t in tokens:
        if "/" in t or "Z" in t or t.startswith("FM") or len(t) > 4: continue
        if re.fullmatch(r'\d{4}', t): return int(t)
    return 9999

def obtener_bloque_vigente(taf_raw):
    """Lógica cronológica para extraer el tramo del TAF que aplica ahora"""
    ahora = datetime.now(timezone.utc)
    ref = ahora.day * 10000 + ahora.hour * 100 + ahora.minute
    
    # Limpieza de cabecera
    cuerpo = re.sub(r'^(TAF\s+)?([A-Z]{4})\s+\d{6}Z\s+', '', taf_raw)
    partes = re.split(r'\b(FM|BECMG|TEMPO|PROB\d{2})\b', cuerpo)
    
    vigente = partes[0] # Base
    for i in range(1, len(partes), 2):
        ind, cont = partes[i], partes[i+1]
        m_r = re.search(r'(\d{2})(\d{2})/(\d{2})(\d{2})', cont)
        m_f = re.search(r'FM(\d{2})(\d{2})(\d{2})', cont)
        
        valido = False
        if m_r:
            di, hi, df, hf = map(int, m_r.groups())
            if (di * 10000 + hi * 100) <= ref < (df * 10000 + hf * 100): valido = True
        elif m_f:
            di, hi, mi = map(int, m_f.groups())
            if ref >= (di * 10000 + hi * 100 + mi): valido = True
            
        if valido:
            vigente = f"{ind} {cont}" if ind != "FM" else f"FM {cont}"
            
    return vigente.strip()

def get_clima_icon(metar):
    if "TS" in metar: return "⛈️"
    if "VA" in metar: return "🌋"
    if "SN" in metar: return "❄️"
    if "RA" in metar or "DZ" in metar: return "🌧️"
    if "FG" in metar or "BR" in metar: return "🌫️"
    if "CAVOK" in metar: return "☀️"
    return "✈️"

# --- 3. AUDITORÍA (CRITERIOS PDF) ---

def auditar_v51(icao, metar, taf):
    p_vigente = obtener_bloque_vigente(taf)
    alertas = []
    
    # Visibilidad (Escalones SMN)
    vm, vp = get_token_vis(metar), get_token_vis(p_vigente)
    umbrales_v = [150, 350, 600, 800, 1500, 3000, 5000]
    ev_m = next((i for i, u in enumerate(umbrales_v) if vm < u), 8)
    ev_p = next((i for i, u in enumerate(umbrales_v) if vp < u), 8)
    
    if ev_m != ev_p and not (vm >= 9999 and vp >= 5000):
        alertas.append(f"VIS: Cambio umbral SMN (M: {vm}m / TAF: {vp}m)")

    # Techos (BKN/OVC)
    def get_c(t):
        capas = re.findall(r'\b(BKN|OVC)(\d{3})\b', t)
        return min(int(c[1]) * 100 for c in capas) if capas else 9999
    nm, np = get_c(metar), get_c(p_vigente)
    for u in [100, 200, 500, 1000, 1500]:
        if (nm < u <= np) or (np < u <= nm):
            alertas.append(f"NUBES: Techo cruzó {u}ft")
            break
            
    return alertas, p_vigente

# --- 4. INTERFAZ ---
st.title("🖥️ Monitor de Vigilancia Meteorológica - SAVC")
st.write(f"Actualización (UTC): {datetime.now(timezone.utc).strftime('%H:%M')}")

cols = st.columns(2)
headers = {"X-API-Key": API_KEY}

for i, icao in enumerate(AERODROMOS):
    try:
        r_id = random.randint(1, 9999)
        m_r = requests.get(f"https://api.checkwx.com/metar/{icao}?cache={r_id}", headers=headers).json().get('data',['-'])[0]
        t_r = requests.get(f"https://api.checkwx.com/taf/{icao}?cache={r_id}", headers=headers).json().get('data',['-'])[0]
        
        if m_r != '-' and t_r != '-':
            alertas, p_vigente = auditar_v51(icao, m_r, t_r)
            status_icon = "🟥" if alertas else "✅"
            weather_icon = get_clima_icon(m_r)
            
            with cols[i % 2]:
                with st.expander(f"{status_icon} {weather_icon} {icao}", expanded=True):
                    # Informe TAF Vigente
                    st.markdown(f"**INFORME TAF VIGENTE:**")
                    st.code(p_vigente, language=None)
                    
                    # METAR
                    st.markdown(f"**METAR ACTUAL:**")
                    st.success(m_r
