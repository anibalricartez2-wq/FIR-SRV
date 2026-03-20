import streamlit as st
import requests
import re
import random
import pandas as pd
from datetime import datetime, timezone
from streamlit_autorefresh import st_autorefresh

# --- 1. CONFIGURACIÓN ---
st.set_page_config(page_title="Vigilancia FIR SAVC", page_icon="✈️", layout="wide")

if 'tema_oscuro' not in st.session_state:
    st.session_state.tema_oscuro = True

def toggle_tema():
    st.session_state.tema_oscuro = not st.session_state.tema_oscuro

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

# --- 2. MOTOR DE COMPARACIÓN TAF vs METAR ---
def get_values(texto):
    if not texto or "Sin datos" in texto: return None
    d = {'dir': 0, 'spd': 0, 'vis': 9999, 'ceil': 9999}
    # Viento
    v = re.search(r'(\d{3})(\d{2,3})KT', texto)
    if v: d['dir'], d['spd'] = int(v.group(1)), int(v.group(2))
    # Visibilidad
    vis = re.search(r'\b(\d{4})\b', texto)
    if vis: d['vis'] = int(vis.group(1))
    elif "CAVOK" in texto: d['vis'] = 9999
    # Techos (BKN/OVC)
    c = re.search(r'(BKN|OVC)(\d{3})', texto)
    if c: d['ceil'] = int(c.group(2)) * 100
    return d

def auditar_comparativa(metar_txt, taf_txt):
    m = get_values(metar_txt)
    t = get_values(taf_txt)
    if not m or not t: return []
    
    motivos = []
    
    # 1. COMPARACIÓN DE VIENTO (Margen 60° / 10kt)
    diff_dir = abs(m['dir'] - t['dir'])
    ang = diff_dir if diff_dir <= 180 else 360 - diff_dir
    if ang >= 60 and (m['spd'] >= 10 or t['spd'] >= 10):
        motivos.append(f"GIRO VTO: TAF {t['dir']}° vs ACT {m['dir']}° (Delta {ang}°)")
    if abs(m['spd'] - t['spd']) >= 10:
        motivos.append(f"INTENSIDAD: TAF {t['spd']}kt vs ACT {m['spd']}kt (Delta {abs(m['spd']-t['spd'])}kt)")

    # 2. COMPARACIÓN DE VISIBILIDAD (Solo si la diferencia cruza un umbral SMN)
    umbrales = [150, 350, 600, 800, 1500, 3000, 5000]
    for u in umbrales:
        # Si el pronóstico estaba de un lado del umbral y la realidad del otro
        if (t['vis'] < u <= m['vis']) or (t['vis'] >= u > m['vis']):
            motivos.append(f"VISIBILIDAD: Dif. significativa en umbral {u}m (TAF {t['vis']}m vs ACT {m['vis']}m)")
            break

    # 3. COMPARACIÓN DE TECHOS (Solo si la diferencia cruza un umbral SMN)
    umbrales_c = [100, 200, 500, 1000, 1500]
    for u in umbrales_c:
        if (t['ceil'] < u <= m['ceil']) or (t['ceil'] >= u > m['ceil']):
            motivos.append(f"TECHO: Dif. significativa en umbral {u}ft (TAF {t['ceil']}ft vs ACT {m['ceil']}ft)")
            break
        
    # 4. FENÓMENOS (Diferencia absoluta)
    for f in ['TS', 'RA', 'SN', 'FG', 'DZ', 'VA', 'GR']:
        if (f in metar_txt) != (f in taf_txt):
            motivos.append(f"FENÓMENO: {f} {'NUEVO' if f in metar_txt else 'CESÓ'}")
            
    return motivos

# --- 3. INTERFAZ ---
st.sidebar.button(f"🌓 MODO {'DÍA' if st.session_state.tema_oscuro else 'NOCHE'}", on_click=toggle_tema)
st.title("🖥️ Vigilancia FIR SAVC")

cols = st.columns(2)
headers = {"X-API-Key": API_KEY}

for i, icao in enumerate(AERODROMOS):
    try:
        r_hash = random.randint(1, 999999)
        res_m = requests.get(f"https://api.checkwx.com/metar/{icao}?cache={r_hash}", headers=headers).json()
        metar = res_m.get('data', ['Sin datos'])[0]
        res_t = requests.get(f"https://api.checkwx.com/taf/{icao}?cache={r_hash}", headers=headers).json()
        taf = res_t.get('data', ['Sin datos'])[0]
        
        # Aquí sucede la comparación real
        motivos = auditar_comparativa(metar, taf)
        enmendar = len(motivos) > 0
        tipo = "SPECI" if "SPECI" in metar else "METAR"

        with cols[i % 2]:
            color = "#FF4B4B" if enmendar else "#00FF00"
            estado = "🚨 ENMENDAR" if enmendar else "✅ COINCIDE"
            
            with st.expander(f"{icao} - {estado}", expanded=True):
                st.markdown(f"**Estado:** <span style='color:{color}; font-weight:bold;'>{estado}</span>", unsafe_allow_html=True)
                
                if enmendar:
                    for m in motivos: st.error(f"⚠️ {m}")
                
                st.caption("TAF VIGENTE")
                st.code(taf)
                st.caption(f"{tipo} ACTUAL")
                st.code(metar)
    except:
        st.error(f"Error en {icao}")
