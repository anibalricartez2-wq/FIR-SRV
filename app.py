import streamlit as st
import requests
import re
import pandas as pd
from datetime import datetime, timezone
from streamlit_autorefresh import st_autorefresh

# --- 1. CONFIGURACIÓN Y TEMA ---
st.set_page_config(page_title="Vigilancia FIR SAVC", page_icon="✈️", layout="wide")

if 'tema_oscuro' not in st.session_state:
    st.session_state.tema_oscuro = True

def toggle_tema():
    st.session_state.tema_oscuro = not st.session_state.tema_oscuro

# CSS para ocultar menús de Streamlit y aplicar el tema
bg, txt, card = ("#0E1117", "#FFFFFF", "#1E1E1E") if st.session_state.tema_oscuro else ("#F8F9FA", "#000000", "#FFFFFF")
st.markdown(f"""
    <style>
    .stApp {{ background-color: {bg}; color: {txt}; }}
    .stDeployButton, footer {{visibility: hidden !important;}}
    .stExpander {{ background-color: {card}; border: 1px solid #444; border-radius: 8px; }}
    </style>
    """, unsafe_allow_html=True)

# Refresco automático cada 2 minutos
st_autorefresh(interval=120000, key="datarefresh")

# --- 2. CONSTANTES Y CRITERIOS (SMN ARGENTINA) ---
API_KEY = "8e7917816866402688f805f637eb54d3"
AERODROMOS = {
    "SAVV": "07/25", "SAVE": "01/19", "SAVT": "06/24", "SAWC": "07/25",
    "SAVC": "07/25", "SAWG": "07/25", "SAWE": "06/24", "SAWH": "07/25"
}

# Umbrales críticos de enmienda
VIS_LIMITS = [150, 350, 600, 800, 1500, 3000, 5000]
CEIL_LIMITS = [100, 200, 500, 1000, 1500]

# --- 3. FUNCIONES DE PROCESAMIENTO ---
def parse_raw_msg(texto):
    if not texto or "Sin datos" in texto: return None
    data = {'dir': 0, 'spd': 0, 'vis': 9999, 'ceil': 9999, 'raw': texto}
    # Viento
    v = re.search(r'(\d{3})(\d{2,3})KT', texto)
    if v: data['dir'], data['spd'] = int(v.group(1)), int(v.group(2))
    # Visibilidad
    vis = re.search(r'\b(\d{4})\b', texto)
    if vis: data['vis'] = int(vis.group(1))
    elif "CAVOK" in texto: data['vis'] = 9999
    # Techo (BKN u OVC)
    c = re.search(r'(BKN|OVC)(\d{3})', texto)
    if c: data['ceil'] = int(c.group(2)) * 100
    return data

def chequear_enmienda(m_raw, t_raw):
    m, t = parse_raw_msg(m_raw), parse_raw_msg(t_raw)
    if not m or not t: return False
    # Viento (60°/10kt o Dif 10kt)
    diff_d = abs(m['dir'] - t['dir'])
    if (diff_d if diff_d <= 180 else 360 - diff_d) >= 60 and (m['spd'] >= 10 or t['spd'] >= 10): return True
    if abs(m['spd'] - t['spd']) >= 10: return True
    # Visibilidad
    for u in VIS_LIMITS:
        if (t['vis'] < u <= m['vis']) or (t['vis'] >= u > m['vis']): return True
    # Techos
    for u in CEIL_LIMITS:
        if (t['ceil'] < u <= m['ceil']) or (t['ceil'] >= u > m['ceil']): return True
    # Fenómenos (TS, RA, SN, FG, DZ, VA)
    for f in ['TS', 'RA', 'SN', 'FG', 'DZ', 'VA']:
        if (f in m_raw) != (f in t_raw): return True
    return False

def get_wx_icon(msg):
    if "TS" in msg: return "⛈️"
    if "RA" in msg or "DZ" in msg: return "🌧️"
    if "SN" in msg: return "❄️"
    if "FG" in msg or "BR" in msg: return "🌫️"
    if "VCFG" in msg: return "🌁"
    return "☀️" if "CAVOK" in msg or "CLR" in msg else "☁️"

# --- 4. INTERFAZ ---
st.sidebar.title("🎮 MENÚ")
st.sidebar.button(f"🌓 MODO {'DÍA' if st.session_state.tema_oscuro else 'NOCHE'}", on_click=toggle_tema)

st.title("🖥️ Vigilancia FIR SAVC")
st.caption(f"Última actualización: {datetime.now(timezone.utc).strftime('%H:%M')} UTC")

cols = st.columns(2)
headers = {"X-API-Key": API_KEY}

for i, (icao, rwy) in enumerate(AERODROMOS.items()):
    try:
        # Peticiones API
        res_m = requests.get(f"https://api.checkwx.com/metar/{icao}", headers=headers).json()
        metar_raw = res_m.get('data', ['Sin datos'])[0]
        res_t = requests.get(f"https://api.checkwx.com/taf/{icao}", headers=headers).json()
        taf_raw = res_t.get('data', ['Sin datos'])[0]

        # Lógica de estados e iconos
        enmendar = chequear_enmienda(metar_raw, taf_raw)
        icono = get_wx_icon(metar_raw)
        tipo_msg = "SPECI" if "SPECI" in metar_raw else "METAR"
        
        with cols[i % 2]:
            color = "#FF4B4B" if enmendar else "#00FF00"
            veredicto = "🚨 ENMENDAR" if enmendar else "✅ COINCIDE"
            
            with st.expander(f"{icono} {icao} | RWY {rwy} 🛫", expanded=True):
                st.markdown(f"**Estado:** <span style='color:{color}; font-weight:bold; font-size:1.1rem;'>{veredicto}</span>", unsafe_allow_html=True)
                
                c_taf, c_met = st.columns(2)
                with c_taf:
                    st.caption("TAF VIGENTE")
                    st.code(taf_raw, language="markdown")
                with c_met:
                    st.caption(f"{tipo_msg} ACTUAL")
                    st.code(metar_raw, language="markdown")
                st.markdown("---")
    except:
        st.error(f"Error de conexión en {icao}")

# --- 5. CRÉDITOS ---
st.markdown(f"""
    <div style="text-align: center; color: gray; font-size: 0.8rem; margin-top: 30px;">
        <hr>
        <b>SISTEMA DE VIGILANCIA TÉCNICA SAVC</b><br>
        Desarrollado por: <b>Operaciones & Gemini AI</b><br>
        Criterios: SMN Argentina | Fuente: CheckWX API
    </div>
    """, unsafe_allow_html=True)
