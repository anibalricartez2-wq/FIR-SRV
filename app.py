import streamlit as st
import requests
import re
import pandas as pd
from datetime import datetime, timezone

# --- 1. CONFIGURACIÓN Y ESTILO ---
st.set_page_config(page_title="Vigilancia FIR SAVC - Pro", page_icon="✈️", layout="wide")

# Gestión de Modo Día/Noche
if 'tema_oscuro' not in st.session_state:
    st.session_state.tema_oscuro = False

def toggle_tema():
    st.session_state.tema_oscuro = not st.session_state.tema_oscuro

# Aplicación de CSS para el tema y ocultar elementos de Streamlit
if st.session_state.tema_oscuro:
    bg, txt, card = "#0E1117", "#FFFFFF", "#262730"
else:
    bg, txt, card = "#F0F2F6", "#000000", "#FFFFFF"

st.markdown(f"""
    <style>
    .stApp {{ background-color: {bg}; color: {txt}; }}
    .stDeployButton, footer {{display:none !important;}}
    .st-emotion-cache-1wbqy5l {{display:none;}}
    </style>
    """, unsafe_allow_html=True)

if 'historial_alertas' not in st.session_state:
    st.session_state.historial_alertas = []

# --- 2. CONSTANTES Y CRITERIOS SMN ---
API_KEY = "8e7917816866402688f805f637eb54d3"
AERODROMOS = ["SAVV","SAVE","SAVT","SAWC","SAVC","SAWG","SAWE","SAWH"]
VIS_THRESHOLDS = [150, 350, 600, 800, 1500, 3000, 5000]
CLOUD_THRESHOLDS = [100, 200, 500, 1000, 1500]

# --- 3. FUNCIONES DE PARSEO Y LÓGICA ---
def get_icono(reporte):
    if "TS" in reporte: return "⛈️"
    if "RA" in reporte: return "🌧️"
    if "SN" in reporte: return "❄️"
    if "FG" in reporte: return "🌫️"
    if "VCFG" in reporte or "BR" in reporte: return "🌁"
    return "☀️" if "SKC" in reporte or "CLR" in reporte or "NSC" in reporte else "☁️"

def parse_metar_data(texto):
    """Extrae viento, visibilidad y techo (BKN/OVC) de un reporte."""
    if not texto or "Sin datos" in texto: return None
    
    data = {'vto_dir': 0, 'vto_spd': 0, 'vis': 9999, 'ceil': 9999, 'is_bkn': False, 'raw': texto}
    
    # Viento
    vto = re.search(r'(\d{3})(\d{2,3})(G\d{2,3})?KT', texto)
    if vto:
        data['vto_dir'], data['vto_spd'] = int(vto.group(1)), int(vto.group(2))
    
    # Visibilidad
    vis = re.search(r'\b(\d{4})\b', texto)
    if vis: data['vis'] = int(vis.group(1))
    elif "CAVOK" in texto: data['vis'] = 9999
    
    # Techo (BKN u OVC)
    nubes = re.search(r'(BKN|OVC)(\d{3})', texto)
    if nubes:
        data['is_bkn'] = True
        data['ceil'] = int(nubes.group(2)) * 100
        
    return data

def auditar_smn(icao, m_raw, t_raw):
    alertas = []
    m = parse_metar_data(m_raw)
    t = parse_metar_data(t_raw)
    
    if not m or not t: return []

    # CRIT A: Giro de viento >= 60° con >= 10kt
    diff_vto = abs(m['vto_dir'] - t['vto_dir'])
    diff_vto = diff_vto if diff_vto <= 180 else 360 - diff_vto
    if diff_vto >= 60 and (m['vto_spd'] >= 10 or t['vto_spd'] >= 10):
        alertas.append(f"GIRO VTO: {diff_vto}°")

    # CRIT B: Intensidad de viento >= 10kt
    if abs(m['vto_spd'] - t['vto_spd']) >= 10:
        alertas.append(f"INT VTO: {abs(m['vto_spd'] - t['vto_spd'])}kt")

    # CRIT E/F: Umbrales de Visibilidad
    for u in VIS_THRESHOLDS:
        if (t['vis'] < u <= m['vis']) or (t['vis'] >= u > m['vis']):
            alertas.append(f"VISIB: Cruzó umbral {u}m")

    # CRIT I/J: Umbrales de Techo
    for u in CLOUD_THRESHOLDS:
        if (t['ceil'] < u <= m['ceil']) or (t['ceil'] >= u > m['ceil']):
            alertas.append(f"TECHO: Cruzó umbral {u}ft")

    # Registro en historial si hay alertas nuevas
    for a in alertas:
        log_entry = {"Hora": datetime.now().strftime("%H:%M"), "OACI": icao, "Motivo": a}
        if log_entry not in st.session_state.historial_alertas:
            st.session_state.historial_alertas.append(log_entry)
            
    return alertas

# --- 4. INTERFAZ ---
st.sidebar.title("⚙️ PANEL CONTROL")
st.sidebar.button("🌓 CAMBIAR MODO DÍA/NOCHE", on_click=toggle_tema)

if st.session_state.historial_alertas:
    with st.sidebar.expander("📋 LOG DE ENMIENDAS (Turno)", expanded=False):
        st.table(pd.DataFrame(st.session_state.historial_alertas).tail(10))
        if st.sidebar.button("🗑️ Limpiar Log"):
            st.session_state.historial_alertas = []
            st.rerun()

st.subheader("📊 Vigilancia Técnica FIR SAVC")
st.caption(f"Sincronización UTC: {datetime.now(timezone.utc).strftime('%H:%M:%S')} Z")

cols = st.columns(2)
headers = {"X-API-Key": API_KEY}

for i, icao in enumerate(AERODROMOS):
    try:
        # Fetch Data
        res_m = requests.get(f"https://api.checkwx.com/metar/{icao}", headers=headers).json()
        metar_txt = res_m.get('data', ['Sin datos'])[0]
        res_t = requests.get(f"https://api.checkwx.com/taf/{icao}", headers=headers).json()
        taf_txt = res_t.get('data', ['Sin datos'])[0]
        
        alertas = auditar_smn(icao, metar_txt, taf_txt)
        icono = get_icono(metar_txt)
        
        with cols[i % 2]:
            color = "red" if alertas else "green"
            with st.container():
                st.markdown(f"### {icono} {icao} | <span style='color:{color}'>{'ENMENDAR' if alertas else 'ESTABLE'}</span>", unsafe_allow_html=True)
                with st.expander("Ver Reportes", expanded=alertas):
                    st.text(f"TAF: {taf_txt}")
                    st.text(f"MET: {metar_txt}")
                    for a in alertas:
                        st.error(f"⚠️ {a}")
                st.markdown("---")
                
    except:
        st.error(f"Error en {icao}")

# --- 5. CRÉDITOS (PIE DE PÁGINA) ---
st.markdown("---")
c1, c2 = st.columns(2)
with c1:
    st.markdown("**SISTEMA DE VIGILANCIA AERONÁUTICA**")
    st.markdown("Criterios de Enmienda según SMN Argentina.")
with c2:
    st.markdown(f"<div style='text-align: right'>Desarrollado por: <b>{st.session_state.get('user_name', 'Operaciones')}</b> & Gemini AI 🤖</div>", unsafe_allow_html=True)
