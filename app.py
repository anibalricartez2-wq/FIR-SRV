import streamlit as st
import requests
import re
import pandas as pd
from datetime import datetime, timezone

# --- 1. CONFIGURACIÓN DE INTERFAZ Y ESTILO ---
st.set_page_config(page_title="Vigilancia FIR SAVC", page_icon="✈️", layout="wide")

if 'tema_oscuro' not in st.session_state:
    st.session_state.tema_oscuro = True  # Por defecto modo noche para fatiga visual

def toggle_tema():
    st.session_state.tema_oscuro = not st.session_state.tema_oscuro

# CSS Personalizado: Ocultar basura de Streamlit y manejo de temas
bg, txt, card = ("#0E1117", "#FFFFFF", "#1E1E1E") if st.session_state.tema_oscuro else ("#F8F9FA", "#000000", "#FFFFFF")
st.markdown(f"""
    <style>
    .stApp {{ background-color: {bg}; color: {txt}; }}
    .stDeployButton, footer {{display:none !important;}}
    .block-container {{padding-top: 1rem;}}
    .stExpander {{ background-color: {card}; border: 1px solid #444; }}
    </style>
    """, unsafe_allow_html=True)

# --- 2. BASE DE DATOS TÉCNICA (PISTAS Y CRITERIOS) ---
API_KEY = "8e7917816866402688f805f637eb54d3"
# Diccionario de aeródromos y sus pistas principales
INFO_AD = {
    "SAVV": "07/25", "SAVE": "01/19", "SAVT": "06/24", "SAWC": "07/25",
    "SAVC": "07/25", "SAWG": "07/25", "SAWE": "06/24", "SAWH": "07/25"
}
VIS_THRESHOLDS = [150, 350, 600, 800, 1500, 3000, 5000]
CLOUD_THRESHOLDS = [100, 200, 500, 1000, 1500]

# --- 3. FUNCIONES DE PROCESAMIENTO ---
def parse_time_validity(taf_text):
    """Extrae el periodo de validez del TAF (ej. 2012/2112)."""
    match = re.search(r'(\d{2})(\d{2})/(\d{2})(\d{2})', taf_text)
    if match:
        return f"{match.group(2)}:00Z a {match.group(4)}:00Z", int(match.group(2)), int(match.group(4))
    return "N/A", None, None

def parse_metar_full(texto):
    if not texto or "Sin datos" in texto: return None
    d = {'dir': 0, 'spd': 0, 'vis': 9999, 'ceil': 9999, 'is_bkn': False, 'raw': texto}
    
    # Viento
    vto = re.search(r'(\d{3})(\d{2,3})KT', texto)
    if vto: d['dir'], d['spd'] = int(vto.group(1)), int(vto.group(2))
    
    # Visibilidad
    vis = re.search(r'\b(\d{4})\b', texto)
    if vis: d['vis'] = int(vis.group(1))
    
    # Techo BKN/OVC
    nubes = re.search(r'(BKN|OVC)(\d{3})', texto)
    if nubes:
        d['is_bkn'] = True
        d['ceil'] = int(nubes.group(2)) * 100
    return d

def auditar_smn(icao, m_raw, t_raw):
    alertas = []
    m, t = parse_metar_full(m_raw), parse_metar_full(t_raw)
    if not m or not t: return []

    # Criterio Viento (60° y 10kt)
    diff_v = abs(m['dir'] - t['dir'])
    diff_v = diff_v if diff_v <= 180 else 360 - diff_v
    if diff_v >= 60 and (m['spd'] >= 10 or t['spd'] >= 10):
        alertas.append(f"GIRO VTO: {diff_v}°")
    if abs(m['spd'] - t['spd']) >= 10:
        alertas.append(f"INT VTO: {abs(m['spd'] - t['spd'])}kt")

    # Criterio Visibilidad
    for u in VIS_THRESHOLDS:
        if (t['vis'] < u <= m['vis']) or (t['vis'] >= u > m['vis']):
            alertas.append(f"VISIB: Cruce umbral {u}m")

    # Criterio Techo
    for u in CLOUD_THRESHOLDS:
        if (t['ceil'] < u <= m['ceil']) or (t['ceil'] >= u > m['ceil']):
            alertas.append(f"TECHO: Cruce umbral {u}ft")

    return alertas

# --- 4. INTERFAZ PRINCIPAL ---
st.sidebar.title("🎮 CONTROLES")
st.sidebar.button("🌓 MODO DÍA/NOCHE", on_click=toggle_tema)

if 'log' not in st.session_state: st.session_state.log = []
if st.sidebar.button("🗑️ LIMPIAR HISTORIAL"): st.session_state.log = []

st.title("🖥️ Vigilancia FIR SAVC | Control de Enmiendas")
st.write(f"Hora Actual: **{datetime.now(timezone.utc).strftime('%H:%M')} Z**")

cols = st.columns(2)
headers = {"X-API-Key": API_KEY}

for i, icao in enumerate(INFO_AD.keys()):
    try:
        # Peticiones API
        res_m = requests.get(f"https://api.checkwx.com/metar/{icao}", headers=headers).json()
        metar_txt = res_m.get('data', ['Sin datos'])[0]
        res_t = requests.get(f"https://api.checkwx.com/taf/{icao}", headers=headers).json()
        taf_txt = res_t.get('data', ['Sin datos'])[0]
        
        # Procesamiento
        periodo, inicio, fin = parse_time_validity(taf_txt)
        alertas = auditar_smn(icao, metar_txt, taf_txt)
        
        # Validar si estamos fuera de hora del TAF
        z_ahora = datetime.now(timezone.utc).hour
        fuera_hora = False
        if inicio is not None and fin is not None:
            if not (inicio <= z_ahora < fin): fuera_hora = True

        with cols[i % 2]:
            color = "#FF4B4B" if alertas else "#00CC66"
            with st.expander(f"📍 {icao} | RWY {INFO_AD[icao]} 🛫", expanded=True):
                st.markdown(f"**Periodo TAF:** `{periodo}` {'⚠️ (FUERA DE HORA)' if fuera_hora else ''}")
                
                # Layout de reportes
                c_taf, c_met = st.columns(2)
                c_taf.caption("TAF VIGENTE")
                c_taf.code(taf_txt, language="markdown")
                c_met.caption("METAR ACTUAL")
                c_met.code(metar_txt, language="markdown")
                
                if alertas:
                    for a in alertas: st.error(f"🚨 {a}")
                    # Auto-log
                    log_entry = f"{datetime.now().strftime('%H:%M')} - {icao}: {', '.join(alertas)}"
                    if log_entry not in st.session_state.log: st.session_state.log.append(log_entry)
                else:
                    st.success("✅ Dentro de parámetros")
                
    except:
        st.error(f"Error de conexión en {icao}")

# --- 5. REGISTRO Y CRÉDITOS ---
st.divider()
with st.expander("📋 REGISTRO DE EVENTOS DEL TURNO"):
    if st.session_state.log:
        for entry in reversed(st.session_state.log): st.text(entry)
    else:
        st.write("Sin novedades en el ciclo actual.")

st.markdown(f"""
    <div style="text-align: center; color: gray; padding: 20px;">
        <hr>
        <b>SISTEMA DE VIGILANCIA TÉCNICA SAVC</b><br>
        Desarrollado por: <b>Operaciones & Gemini AI</b><br>
        Criterios: SMN Argentina | Fuente: CheckWX API
    </div>
    """, unsafe_allow_html=True)
