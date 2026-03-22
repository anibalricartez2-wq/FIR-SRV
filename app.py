import streamlit as st
import requests
import re
import random
import pandas as pd
import io
from datetime import datetime, timezone
from streamlit_autorefresh import st_autorefresh

# --- 1. CONFIGURACIÓN Y ESTILOS DINÁMICOS ---
st.set_page_config(page_title="Vigilancia SAVC v5.2", page_icon="✈️", layout="wide")

# Barra lateral: Configuración y Modo Pantalla
st.sidebar.title("Configuración")
tema = st.sidebar.selectbox("Modo de Pantalla:", ["🌙 Noche", "☀️ Día"])

# CSS Dinámico para Modo Día/Noche y limpieza de interfaz
if tema == "🌙 Noche":
    st.markdown("""<style>
        .stApp { background-color: #0e1117; color: #ffffff; }
        .stExpander { background-color: #1d2129 !important; border: 1px solid #333; }
        .stCode { background-color: #111 !important; color: #0f0 !important; }
        #MainMenu, footer, .stDeployButton, header {visibility: hidden;}
    </style>""", unsafe_allow_html=True)
else:
    st.markdown("""<style>
        .stApp { background-color: #ffffff; color: #000000; }
        .stExpander { background-color: #f0f2f6 !important; border: 1px solid #ddd; }
        #MainMenu, footer, .stDeployButton, header {visibility: hidden;}
    </style>""", unsafe_allow_html=True)

st.sidebar.divider()
if st.sidebar.button("🔄 Actualizar Ahora"):
    st.rerun()

# Inicializar log de alertas si no existe
if 'log_alertas' not in st.session_state:
    st.session_state.log_alertas = []

# Auto-refresco cada 30 minutos
st_autorefresh(interval=1800000, key="auto_refresh")

API_KEY = "8e7917816866402688f805f637eb54d3"
AERODROMOS = ["SAVV","SAVE","SAVT","SAWC","SAVC","SAWG","SAWE","SAWH"]
ICAO_STRING = ",".join(AERODROMOS)

# --- 2. FUNCIONES DE PROCESAMIENTO ---

def get_clima_icon(metar):
    if "TS" in metar: return "⛈️"
    if "RA" in metar: return "🌧️"
    if "FG" in metar or "BR" in metar: return "🌫️"
    if "CAVOK" in metar: return "☀️"
    return "✈️"

def get_token_vis(texto):
    if any(x in texto for x in ["CAVOK", "SKC", "NSC", "CLR"]): return 9999
    t_limpio = re.sub(r'\d{4}/\d{4}', '', texto)
    tokens = t_limpio.split()
    for t in tokens:
        if "/" in t or "Z" in t or t.startswith("FM") or len(t) != 4: continue
        if re.fullmatch(r'\d{4}', t): return int(t)
    return 9999

def obtener_bloque_vigente(taf_raw):
    ahora = datetime.now(timezone.utc)
    ref = ahora.day * 10000 + ahora.hour * 100 + ahora.minute
    cuerpo = re.sub(r'^(TAF\s+)?([A-Z]{4})\s+\d{6}Z\s+', '', taf_raw)
    partes = re.split(r'\b(FM|BECMG|TEMPO|PROB\d{2})\b', cuerpo)
    vigente = partes[0] 
    for i in range(1, len(partes), 2):
        ind, cont = partes[i], partes[i+1]
        m_r = re.search(r'(\d{2})(\d{2})/(\d{2})(\d{2})', cont)
        m_f = re.search(r'FM(\d{2})(\d{2})(\d{2})', cont)
        if m_r:
            di, hi, df, hf = map(int, m_r.groups())
            if (di * 10000 + hi * 100) <= ref < (df * 10000 + hf * 100): vigente = f"{ind} {cont}"
        elif m_f:
            di, hi, mi = map(int, m_f.groups())
            if ref >= (di * 10000 + hi * 100 + mi): vigente = f"FM {cont}"
    return vigente.strip()

def auditar_v52(icao, metar, taf):
    p_vigente = obtener_bloque_vigente(taf)
    alertas = []
    vm, vp = get_token_vis(metar), get_token_vis(p_vigente)
    umbrales_v = [150, 350, 600, 800, 1500, 3000, 5000]
    ev_m = next((i for i, u in enumerate(umbrales_v) if vm < u), 8)
    ev_p = next((i for i, u in enumerate(umbrales_v) if vp < u), 8)
    if ev_m != ev_p and not (vm >= 9999 and vp >= 5000):
        alertas.append(f"VIS: Cambio umbral SMN (M: {vm}m / TAF: {vp}m)")
    return alertas, p_vigente

# --- 3. INTERFAZ Y RENDERIZADO ---
st.title("🖥️ Monitor de Vigilancia Meteorológica - SAVC")
st.write(f"**Hora Actual (UTC):** {datetime.now(timezone.utc).strftime('%H:%M:%S')}")

cols = st.columns(2)
headers = {"X-API-Key": API_KEY}

try:
    r_id = random.randint(1, 99999)
    res_metar_raw = requests.get(f"https://api.checkwx.com/metar/{ICAO_STRING}?cache={r_id}", headers=headers).json().get('
