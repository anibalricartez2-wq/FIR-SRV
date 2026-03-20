import streamlit as st
import requests
import re
import random
import pandas as pd
from datetime import datetime, timezone
from streamlit_autorefresh import st_autorefresh

# --- 1. CONFIGURACIÓN Y TEMA ---
st.set_page_config(page_title="Vigilancia FIR SAVC", page_icon="✈️", layout="wide")

if 'tema_oscuro' not in st.session_state:
    st.session_state.tema_oscuro = True

if 'historial_alertas' not in st.session_state:
    st.session_state.historial_alertas = []

def toggle_tema():
    st.session_state.tema_oscuro = not st.session_state.tema_oscuro

# Estilo para ocultar menús y aplicar tema
bg, txt, card = ("#0E1117", "#FFFFFF", "#1E1E1E") if st.session_state.tema_oscuro else ("#F8F9FA", "#000000", "#FFFFFF")
st.markdown(f"""
    <style>
    .stApp {{ background-color: {bg}; color: {txt}; }}
    .stDeployButton, footer {{visibility: hidden !important;}}
    .st-emotion-cache-1wbqy5l {{display:none;}}
    .block-container {{padding-top: 1rem;}}
    .stExpander {{ background-color: {card}; border: 1px solid #444; border-radius: 8px; }}
    </style>
    """, unsafe_allow_html=True)

st_autorefresh(interval=120000, key="datarefresh")

API_KEY = "8e7917816866402688f805f637eb54d3"
AERODROMOS = ["SAVV","SAVE","SAVT","SAWC","SAVC","SAWG","SAWE","SAWH"]

# --- 2. FUNCIONES TÉCNICAS (CRITERIOS SMN) ---
def parse_viento(texto):
    if not texto or "Sin datos" in texto: return None, None
    match = re.search(r'(\d{3})(\d{2,3})KT', texto)
    if match:
        return int(match.group(1)), int(match.group(2))
    return None, None

def parse_vis_ceil(texto):
    vis, ceil = 9999, 9999
    # Visibilidad
    v = re.search(r'\b(\d{4})\b', texto)
    if v: vis = int(v.group(1))
    elif "CAVOK" in texto: vis = 9999
    # Techo (BKN/OVC)
    c = re.search(r'(BKN|OVC)(\d{3})', texto)
    if c: ceil = int(c.group(2)) * 100
    return vis, ceil

def auditar_binario(icao, reporte, taf):
    """Retorna True si requiere enmienda según criterios SMN"""
    dr, vr = parse_viento(reporte)
    dt, vt = parse_viento(taf)
    vis_r, ceil_r = parse_vis_ceil(reporte)
    vis_t, ceil_t = parse_vis_ceil(taf)
    
    # 1. Viento (Giro 60°/10kt o Dif 10kt)
    if vr is not None and vt is not None:
        diff = abs(dr - dt)
        if (diff if diff <= 180 else 360 - diff) >= 60 and (vr >= 10 or vt >= 10): return True
        if abs(vr - vt) >= 10: return True
    
    # 2. Visibilidad y Techos (Cruce de umbrales)
    for u in [150, 350, 600, 800, 1500, 3000, 5000]:
        if (vis_t < u <= vis_r) or (vis_t >= u > vis_r): return True
    for u in [100, 200, 500, 1000, 1500]:
        if (ceil_t < u <= ceil_r) or (ceil_t >= u > ceil_r): return True
        
    # 3. Fenómenos
    for f in ['TS', 'RA', 'SN', 'FG', 'DZ']:
        if (f in reporte) != (f in taf): return True
        
    return False

def get_icon(msg):
    if "TS" in msg: return "⛈️"
    if "RA" in msg or "DZ" in msg: return "🌧️"
    if "FG" in msg or "BR" in msg: return "🌫️"
    return "☀️" if "CAVOK" in msg or "CLR" in msg else "☁️"

# --- 3. INTERFAZ ---
st.sidebar.title("CONTROLES")
st.sidebar.button(f"🌓 MODO {'DÍA' if st.session_state.tema_oscuro else 'NOCHE'}", on_click=toggle_tema)

st.title("🖥️ Vigilancia FIR SAVC")

# Registro de Desvíos
with st.container():
    if st.session_state.historial_alertas:
        with st.expander("📊 Registro de Desvíos del Turno"):
            df_log = pd.DataFrame(st.session_state.historial_alertas)
            st.table(df_log.tail(5))
            if st.button("🗑️ Limpiar historial"):
                st.session_state.historial_alertas = []
                st.rerun()

st.divider()
st.write(f"Sincronizado: **{datetime.now(timezone.utc).strftime('%H:%M:%S')} UTC**")

cols = st.columns(2)
headers = {"X-API-Key": API_KEY}

for i, icao in enumerate(AERODROMOS):
    try:
        r_hash = random.randint(1, 999999)
        res_m = requests.get(f"https://api.checkwx.com/metar/{icao}?cache={r_hash}", headers=headers).json()
        metar = res_m.get('data', ['Sin datos'])[0]
        
        res_t = requests.get(f"https://api.checkwx.com/taf/{icao}?cache={r_hash}", headers=headers).json()
        taf = res_t.get('data', ['Sin datos'])[0]
        
        enmienda = auditar_binario(icao, metar, taf) if "Sin datos" not in [metar, taf] else False
        icono = get_icon(metar)
        tipo_msg = "SPECI" if "SPECI" in metar else "METAR"

        with cols[i % 2]:
            color = "#FF4B4B" if enmienda else "#00FF00"
            estado = "🚨 ENMENDAR" if enmienda else "✅ COINCIDE"
            
            with st.expander(f"{icono} {icao} - {estado}", expanded=True):
                st.markdown(f"**Estado:** <span style='color:{color}; font-weight:bold;'>{estado}</span>", unsafe_allow_html=True)
                
                st.caption("MENSAJE TAF:")
                st.code(taf, language="markdown")
                
                st.caption(f"MENSAJE {tipo_msg}:")
                st.code(metar, language="markdown")
                
                if enmienda:
                    entry = {"H_UTC": datetime.now(timezone.utc).strftime("%H:%M"), "OACI": icao, "Estado": "ENMIENDA"}
                    if not st.session_state.historial_alertas or st.session_state.historial_alertas[-1]['OACI'] != icao:
                        st.session_state.historial_alertas.append(entry)
    except:
        st.error(f"Falla de conexión en {icao}")

st.markdown(f"""
    <div style="text-align: center; color: gray; font-size: 0.8rem; margin-top: 50px;">
        <hr>
        <b>SISTEMA DE VIGILANCIA TÉCNICA SAVC</b><br>
        Desarrollado por: Operaciones & Gemini AI
    </div>
    """, unsafe_allow_html=True)
