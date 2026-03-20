import streamlit as st
import requests
import re
import random
import pandas as pd
from datetime import datetime, timezone
from streamlit_autorefresh import st_autorefresh

# --- 1. CONFIGURACIÓN DE PÁGINA Y TEMA ---
st.set_page_config(page_title="Vigilancia FIR SAVC", page_icon="✈️", layout="wide")

if 'tema_oscuro' not in st.session_state:
    st.session_state.tema_oscuro = True

if 'historial_alertas' not in st.session_state:
    st.session_state.historial_alertas = []

def toggle_tema():
    st.session_state.tema_oscuro = not st.session_state.tema_oscuro

# CSS para ocultar menús de Streamlit y aplicar el tema visual
bg, txt, card = ("#0E1117", "#FFFFFF", "#1E1E1E") if st.session_state.tema_oscuro else ("#F8F9FA", "#000000", "#FFFFFF")
st.markdown(f"""
    <style>
    .stApp {{ background-color: {bg}; color: {txt}; }}
    .stDeployButton, footer {{visibility: hidden !important;}}
    .st-emotion-cache-1wbqy5l {{display:none;}}
    .block-container {{padding-top: 1rem;}}
    .stExpander {{ background-color: {card}; border: 1px solid #444; border-radius: 8px; }}
    pre {{ white-space: pre-wrap !important; }} 
    </style>
    """, unsafe_allow_html=True)

st_autorefresh(interval=120000, key="datarefresh")

API_KEY = "8e7917816866402688f805f637eb54d3"
AERODROMOS = ["SAVV","SAVE","SAVT","SAWC","SAVC","SAWG","SAWE","SAWH"]

# --- 2. FUNCIONES DE PROCESAMIENTO TÉCNICO ---
def parse_viento(texto):
    if not texto or "Sin datos" in texto: return None, None
    match = re.search(r'(\d{3})(\d{2,3})KT', texto)
    if match: return int(match.group(1)), int(match.group(2))
    return None, None

def parse_vis_ceil(texto):
    vis, ceil = 9999, 9999
    # Visibilidad
    v = re.search(r'\b(\d{4})\b', texto)
    if v: vis = int(v.group(1))
    elif "CAVOK" in texto: vis = 9999
    # Techos
    c = re.search(r'(BKN|OVC)(\d{3})', texto)
    if c: ceil = int(c.group(2)) * 100
    elif "CAVOK" in texto or "NSC" in texto: ceil = 9999
    return vis, ceil

def auditar_detallado(reporte, taf):
    motivos = []
    dr, vr = parse_viento(reporte)
    dt, vt = parse_viento(taf)
    vis_r, ceil_r = parse_vis_ceil(reporte)
    vis_t, ceil_t = parse_vis_ceil(taf)
    
    # COMPARACIÓN DIRECTA (Diferencia = Alerta)
    
    # 1. Viento: Si dirección o intensidad no coinciden
    if vr is not None and vt is not None:
        if dr != dt:
            motivos.append(f"VTO DIR: TAF {dt}° vs ACT {dr}°")
        if vr != vt:
            motivos.append(f"VTO INT: TAF {vt}kt vs ACT {vr}kt")
    
    # 2. Visibilidad: Si el valor reportado es distinto al pronosticado
    if vis_r != vis_t:
        motivos.append(f"VISIBILIDAD: TAF {vis_t}m vs ACT {vis_r}m")
            
    # 3. Techos: Si la altura de nubes cambió
    if ceil_r != ceil_t:
        t_val = f"{ceil_t}ft" if ceil_t < 9999 else "S/T"
        r_val = f"{ceil_r}ft" if ceil_r < 9999 else "S/T"
        motivos.append(f"TECHO: TAF {t_val} vs ACT {r_val}")
        
    # 4. Fenómenos: Si hay algo en el METAR que no estaba en el TAF (o viceversa)
    for f in ['TS', 'RA', 'SN', 'FG', 'DZ', 'VA', 'GR']:
        if (f in reporte) != (f in taf):
            estado = "NUEVO" if f in reporte else "CESÓ"
            motivos.append(f"FENÓMENO: {f} ({estado})")
            
    return motivos

def get_icon(msg):
    if "TS" in msg: return "⛈️"
    if "RA" in msg or "DZ" in msg: return "🌧️"
    if "FG" in msg or "BR" in msg: return "🌫️"
    if "SN" in msg: return "❄️"
    return "☀️" if "CAVOK" in msg or "CLR" in msg else "☁️"

# --- 3. INTERFAZ ---
st.sidebar.title("CONTROLES")
st.sidebar.button(f"🌓 MODO {'DÍA' if st.session_state.tema_oscuro else 'NOCHE'}", on_click=toggle_tema)

st.title("✈️ Vigilancia FIR SAVC")

with st.container():
    if st.session_state.historial_alertas:
        with st.expander("📋 Historial de Discrepancias (Turno)"):
            st.table(pd.DataFrame(st.session_state.historial_alertas).tail(10))
            if st.button("🗑️ Limpiar historial"):
                st.session_state.historial_alertas = []
                st.rerun()

st.divider()
st.write(f"Actualizado: **{datetime.now(timezone.utc).strftime('%H:%M:%S')} UTC**")

cols = st.columns(2)
headers = {"X-API-Key": API_KEY}

for i, icao in enumerate(AERODROMOS):
    try:
        r_hash = random.randint(1, 999999)
        res_m = requests.get(f"https://api.checkwx.com/metar/{icao}?cache={r_hash}", headers=headers).json()
        metar = res_m.get('data', ['Sin datos'])[0]
        res_t = requests.get(f"https://api.checkwx.com/taf/{icao}?cache={r_hash}", headers=headers).json()
        taf = res_t.get('data', ['Sin datos'])[0]
        
        motivos = auditar_detallado(metar, taf) if "Sin datos" not in [metar, taf] else []
        enmendar = len(motivos) > 0
        icono = get_icon(metar)
        tipo_msg = "SPECI" if "SPECI" in metar else "METAR"

        with cols[i % 2]:
            color = "#FF4B4B" if enmendar else "#00FF00"
            estado = "🚨 ENMENDAR" if enmendar else "✅ COINCIDE"
            
            with st.expander(f"{icono} {icao} - {estado}", expanded=True):
                st.markdown(f"**Estado:** <span style='color:{color}; font-weight:bold; font-size:1.1rem;'>{estado}</span>", unsafe_allow_html=True)
                
                if enmendar:
                    for m in motivos:
                        st.warning(f"⚠️ {m}")
                
                st.caption("TAF VIGENTE")
                st.code(taf, language="markdown")
                
                st.caption(f"{tipo_msg} ACTUAL")
                st.code(metar, language="markdown")
                
                if enmendar:
                    entry = {"H_UTC": datetime.now(timezone.utc).strftime("%H:%M"), "OACI": icao, "Diferencias": " | ".join(motivos)}
                    # Evitar duplicados seguidos del mismo error
                    if not st.session_state.historial_alertas or st.session_state.historial_alertas[-1]['Diferencias'] != entry['Diferencias']:
                        st.session_state.historial_alertas.append(entry)
    except Exception:
        st.error(f"Falla de conexión en {icao}")

st.markdown(f"""
    <div style="text-align: center; color: gray; font-size: 0.8rem; margin-top: 30px;">
        <hr>
        <b>VIGILANCIA COMPARATIVA SAVC</b><br>
        Desarrollado por: Operaciones & Gemini AI | Análisis Directo TAF vs METAR
    </div>
    """, unsafe_allow_html=True)
