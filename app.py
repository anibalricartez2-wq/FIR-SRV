import streamlit as st
import requests
import re
import random
import pandas as pd
from datetime import datetime, timezone
from streamlit_autorefresh import st_autorefresh

# --- 1. CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Vigilancia FIR SAVC", page_icon="✈️", layout="wide")

if 'tema_oscuro' not in st.session_state:
    st.session_state.tema_oscuro = True

def toggle_tema():
    st.session_state.tema_oscuro = not st.session_state.tema_oscuro

# CSS para limpieza visual
bg, txt, card = ("#0E1117", "#FFFFFF", "#1E1E1E") if st.session_state.tema_oscuro else ("#F8F9FA", "#000000", "#FFFFFF")
st.markdown(f"""
    <style>
    .stApp {{ background-color: {bg}; color: {txt}; }}
    .stDeployButton, footer {{visibility: hidden !important;}}
    .block-container {{padding-top: 1rem;}}
    .stExpander {{ background-color: {card}; border: 1px solid #444; border-radius: 8px; }}
    pre {{ white-space: pre-wrap !important; }} 
    </style>
    """, unsafe_allow_html=True)

st_autorefresh(interval=120000, key="datarefresh")

API_KEY = "8e7917816866402688f805f637eb54d3"
AERODROMOS = ["SAVV","SAVE","SAVT","SAWC","SAVC","SAWG","SAWE","SAWH"]

# --- 2. LÓGICA DE VIGILANCIA (TOLERANCIAS OPERATIVAS) ---
def parse_viento(texto):
    if not texto or "Sin datos" in texto: return None, None
    match = re.search(r'(\d{3})(\d{2,3})KT', texto)
    if match: return int(match.group(1)), int(match.group(2))
    return None, None

def parse_vis_ceil(texto):
    vis, ceil = 9999, 9999
    v = re.search(r'\b(\d{4})\b', texto)
    if v: vis = int(v.group(1))
    elif "CAVOK" in texto: vis = 9999
    c = re.search(r'(BKN|OVC)(\d{3})', texto)
    if c: ceil = int(c.group(2)) * 100
    return vis, ceil

def auditar_vigilante(metar_txt, taf_txt):
    motivos = []
    dm, vm = parse_viento(metar_txt)
    dt, vt = parse_viento(taf_txt)
    vism, ceilm = parse_vis_ceil(metar_txt)
    vist, ceilt = parse_vis_ceil(taf_txt)
    
    # 1. VIENTO: Solo alerta si Giro >= 60° (con viento >= 10kt) o Dif Intensidad >= 10kt
    if vm is not None and vt is not None:
        diff_ang = abs(dm - dt)
        ang = diff_ang if diff_ang <= 180 else 360 - diff_ang
        if ang >= 60 and (vm >= 10 or vt >= 10):
            motivos.append(f"GIRO VTO: {ang}° (Límite 60°)")
        if abs(vm - vt) >= 10:
            motivos.append(f"INTENSIDAD: Dif {abs(vm-vt)}kt (Límite 10kt)")

    # 2. VISIBILIDAD: Solo si se cruza un umbral de enmienda
    umbrales_vis = [150, 350, 600, 800, 1500, 3000, 5000]
    for u in umbrales_vis:
        if (vist < u <= vism) or (vist >= u > vism):
            motivos.append(f"VISIBILIDAD: Cambio de rango en umbral {u}m")
            break

    # 3. TECHOS (BKN/OVC): Solo si se cruza un umbral de enmienda
    umbrales_ceil = [100, 200, 500, 1000, 1500]
    for u in umbrales_ceil:
        if (ceilt < u <= ceilm) or (ceilt >= u > ceilm):
            motivos.append(f"TECHO: Cambio de rango en umbral {u}ft")
            break
        
    # 4. FENÓMENOS: Aparición o cese de tiempo significativo
    for f in ['TS', 'RA', 'SN', 'FG', 'DZ', 'VA', 'GR']:
        if (f in metar_txt) != (f in taf_txt):
            estado = "NUEVO" if f in metar_txt else "CESÓ"
            motivos.append(f"FENÓMENO {f}: {estado}")
            
    return motivos

# --- 3. INTERFAZ ---
st.sidebar.button(f"🌓 MODO {'DÍA' if st.session_state.tema_oscuro else 'NOCHE'}", on_click=toggle_tema)
st.title("🛡️ Vigilante FIR SAVC")

cols = st.columns(2)
headers = {"X-API-Key": API_KEY}

for i, icao in enumerate(AERODROMOS):
    try:
        r_hash = random.randint(1, 999999)
        res_m = requests.get(f"https://api.checkwx.com/metar/{icao}?cache={r_hash}", headers=headers).json()
        metar = res_m.get('data', ['Sin datos'])[0]
        res_t = requests.get(f"https://api.checkwx.com/taf/{icao}?cache={r_hash}", headers=headers).json()
        taf = res_t.get('data', ['Sin datos'])[0]
        
        motivos = auditar_vigilante(metar, taf)
        enmendar = len(motivos) > 0
        tipo = "SPECI" if "SPECI" in metar else "METAR"

        with cols[i % 2]:
            color = "#FF4B4B" if enmendar else "#00FF00"
            estado = "🚨 ENMENDAR" if enmendar else "✅ COINCIDE"
            
            with st.expander(f"{icao} - {estado}", expanded=True):
                st.markdown(f"**Estado:** <span style='color:{color}; font-weight:bold; font-size:1.1rem;'>{estado}</span>", unsafe_allow_html=True)
                
                if enmendar:
                    for m in motivos:
                        st.error(f"⚠️ {m}")
                
                st.caption("TAF VIGENTE")
                st.code(taf, language="markdown")
                st.caption(f"{tipo} ACTUAL")
                st.code(metar, language="markdown")
    except Exception:
        st.error(f"Falla de conexión en {icao}")

st.markdown(f"""
    <div style="text-align: center; color: gray; font-size: 0.8rem; margin-top: 30px;">
        <hr>
        <b>VIGILANCIA TÉCNICA OPERATIVA</b><br>
        Filtro de Desvíos Significativos (Márgenes SMN/OACI)
    </div>
    """, unsafe_allow_html=True)
