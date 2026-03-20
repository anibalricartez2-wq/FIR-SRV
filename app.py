import streamlit as st
import requests
import re
import pandas as pd
from datetime import datetime, timezone

# --- 1. CONFIGURACIÓN DE PÁGINA Y TEMA ---
st.set_page_config(page_title="Vigilancia FIR SAVC", page_icon="✈️", layout="wide")

if 'tema_oscuro' not in st.session_state:
    st.session_state.tema_oscuro = True

def toggle_tema():
    st.session_state.tema_oscuro = not st.session_state.tema_oscuro

bg, txt, card = ("#0E1117", "#FFFFFF", "#1E1E1E") if st.session_state.tema_oscuro else ("#F8F9FA", "#000000", "#FFFFFF")
st.markdown(f"""
    <style>
    .stApp {{ background-color: {bg}; color: {txt}; }}
    .stDeployButton, footer {{display:none !important;}}
    .stExpander {{ background-color: {card}; border: 1px solid #444; border-radius: 8px; }}
    </style>
    """, unsafe_allow_html=True)

# --- 2. DATOS TÉCNICOS Y CRITERIOS (SMN) ---
API_KEY = "8e7917816866402688f805f637eb54d3"
AERODROMOS = {
    "SAVV": "07/25", "SAVE": "01/19", "SAVT": "06/24", "SAWC": "07/25",
    "SAVC": "07/25", "SAWG": "07/25", "SAWE": "06/24", "SAWH": "07/25"
}

UMBRALES_VIS = [150, 350, 600, 800, 1500, 3000, 5000]
UMBRALES_CEIL = [100, 200, 500, 1000, 1500]

# --- 3. PROCESAMIENTO DE MENSAJES ---
def parse_msg(texto):
    if not texto or "Sin datos" in texto: return None
    d = {'v_dir': 0, 'v_spd': 0, 'vis': 9999, 'ceil': 9999, 'raw': texto}
    
    # Viento
    v = re.search(r'(\d{3})(\d{2,3})KT', texto)
    if v: d['v_dir'], d['v_spd'] = int(v.group(1)), int(v.group(2))
    
    # Visibilidad
    vis = re.search(r'\b(\d{4})\b', texto)
    if vis: d['vis'] = int(vis.group(1))
    elif "CAVOK" in texto: d['vis'] = 9999
    
    # Techos (BKN/OVC)
    nubes = re.search(r'(BKN|OVC)(\d{3})', texto)
    if nubes: d['ceil'] = int(nubes.group(2)) * 100
    
    return d

def verificar_desviacion(m_txt, t_txt):
    m, t = parse_msg(m_txt), parse_msg(t_txt)
    if not m or not t: return False

    # Viento: Giro 60° y V >= 10kt o Dif Int 10kt
    diff_d = abs(m['v_dir'] - t['v_dir'])
    if (diff_d if diff_d <= 180 else 360 - diff_d) >= 60 and (m['v_spd'] >= 10 or t['v_spd'] >= 10):
        return True
    if abs(m['v_spd'] - t['v_spd']) >= 10: return True

    # Visibilidad
    for u in UMBRALES_VIS:
        if (t['vis'] < u <= m['vis']) or (t['vis'] >= u > m['vis']): return True

    # Techos
    for u in UMBRALES_CEIL:
        if (t['ceil'] < u <= m['ceil']) or (t['ceil'] >= u > m['ceil']): return True
    
    # Fenómenos (TS, RA, FG, etc.)
    for f in ['TS', 'RA', 'FG', 'SN', 'DZ', 'GR', 'VA']:
        if (f in m_txt) != (f in t_txt): return True

    return False

# --- 4. INTERFAZ ---
st.sidebar.title("🎛️ CONTROLES")
st.sidebar.button("🌓 CAMBIAR TEMA", on_click=toggle_tema)
if 'log' not in st.session_state: st.session_state.log = []

st.title("✈️ Monitoreo TAF vs METAR/SPECI")
st.write(f"Sincronización: **{datetime.now(timezone.utc).strftime('%H:%M')} UTC**")

cols = st.columns(2)
headers = {"X-API-Key": API_KEY}

for i, (icao, rwy) in enumerate(AERODROMOS.items()):
    try:
        # Obtener reportes (La API incluye SPECI en la ruta de metar)
        res_m = requests.get(f"https://api.checkwx.com/metar/{icao}", headers=headers).json()
        metar = res_m.get('data', ['Sin datos'])[0]
        res_t = requests.get(f"https://api.checkwx.com/taf/{icao}", headers=headers).json()
        taf = res_t.get('data', ['Sin datos'])[0]
        
        # Validar periodo de tiempo del TAF
        periodo_match = re.search(r'(\d{4})/(\d{4})', taf)
        periodo = periodo_match.group(0) if periodo_match else "N/A"
        
        # Comparación
        desviado = verificar_desviacion(metar, taf)
        
        with cols[i % 2]:
            status_color = "#FF4B4B" if desviado else "#00FF00"
            status_text = "🚨 ENMIENDA REQUERIDA" if desviado else "✅ COINCIDE"
            
            with st.expander(f"📍 {icao} | RWY {rwy} 🛫", expanded=True):
                st.markdown(f"**Periodo:** `{periodo}Z` | <span style='color:{status_color}; font-weight:bold;'>{status_text}</span>", unsafe_allow_html=True)
                
                st.caption("MENSAJE TAF VIGENTE")
                st.code(taf, language="markdown")
                
                st.caption("MENSAJE METAR / SPECI ACTUAL")
                st.code(metar, language="markdown")
                
                if desviado:
                    log_msg = f"{datetime.now().strftime('%H:%M')} - {icao}: Desviación detectada."
                    if not st.session_state.log or st.session_state.log[-1] != log_msg:
                        st.session_state.log.append(log_msg)
                st.markdown("---")
                
    except Exception:
        st.error(f"Error de comunicación con {icao}")

# --- 5. REGISTRO Y CRÉDITOS ---
if st.session_state.log:
    with st.expander("📋 HISTORIAL DE DESVIACIONES DEL TURNO"):
        for item in reversed(st.session_state.log): st.text(item)

st.
