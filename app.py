import streamlit as st
import requests
import re
import random
import pandas as pd
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

# --- 1. CONFIGURACIÓN ---
st.set_page_config(page_title="Vigilancia FIR SAVC", page_icon="✈️", layout="wide")

# Inicializar el historial
if 'historial_alertas' not in st.session_state:
    st.session_state.historial_alertas = []

# ESTILO CSS
hide_st_style = """
            <style>
            .stDeployButton {display:none;}
            footer {visibility: hidden;}
            .st-emotion-cache-1wbqy5l {display:none;}
            .block-container {padding-top: 1rem;}
            .copyright { text-align: center; color: #888; font-size: 0.8rem; margin-top: 50px; border-top: 1px solid #444; padding-top: 10px; }
            </style>
            """
st.markdown(hide_st_style, unsafe_allow_html=True)

# REFRESH CADA 30 MINUTOS
st_autorefresh(interval=1800000, key="datarefresh")

API_KEY = "8e7917816866402688f805f637eb54d3"
AERODROMOS = ["SAVV","SAVE","SAVT","SAWC","SAVC","SAWG","SAWE","SAWH"]

# --- 2. FUNCIONES DE EXTRACCIÓN Y AUDITORÍA (SEGÚN TABLA SMN) ---

def parse_viento(texto):
    if not texto or "Sin datos" in texto: return None, None, None
    match = re.search(r'(\d{3})(\d{2,3})(G\d{2,3})?KT', texto)
    if match:
        d = int(match.group(1))
        v = int(match.group(2))
        g = int(match.group(3)[1:]) if match.group(3) else 0
        return d, v, g
    return None, None, None

def parse_visibilidad(texto):
    match = re.search(r'\s(\d{4})\s', texto)
    return int(match.group(1)) if match else 9999

def parse_nubes(texto):
    capas = re.findall(r'(BKN|OVC)(\d{3})', texto)
    if capas:
        return min(int(c[1]) * 100 for c in capas)
    return 9999

def obtener_icono_clima(metar_text):
    if "TS" in metar_text: return "⛈️" 
    if "VA" in metar_text: return "🌋"
    if "RA" in metar_text or "DZ" in metar_text: return "🌧️"
    if "FG" in metar_text or "BR" in metar_text: return "🌫️"
    if "SKC" in metar_text or "CLR" in metar_text or "NSC" in metar_text: return "☀️"
    return "✈️"

def auditar(icao, metar, taf):
    enmiendas = []
    # Parsers
    dr, vr, gr = parse_viento(metar)
    vis_r = parse_visibilidad(metar)
    techo_r = parse_nubes(metar)
    dt, vt, gt = parse_viento(taf)
    vis_t = parse_visibilidad(taf)
    techo_t = parse_nubes(taf)

    if vr is not None and vt is not None:
        # Viento: Giro >= 60° (vto >= 10kt)
        if (vr >= 10 or vt >= 10) and abs(dr - dt) >= 60:
            enmiendas.append(f"VIENTO: Giro >= 60° ({dr}° vs {dt}°)")
        # Viento: Intensidad media >= 10kt
        if abs(vr - vt) >= 10:
            enmiendas.append(f"VIENTO: Dif. Vel. >= 10kt")
        # Viento: Ráfagas (si media >= 15kt y ráfaga supera en 10kt)
        if (gr > 0) and (vr >= 15 or vt >= 15) and (gr - vr >= 10):
            enmiendas.append(f"VIENTO: Ráfaga crítica (+{gr-vr}kt)")

    # Visibilidad (Umbrales SMN)
    umbrales_vis = [150, 350, 600, 800, 1500, 3000, 5000]
    for u in umbrales_vis:
        if (vis_r <= u < vis_t) or (vis_t <= u < vis_r):
            enmiendas.append(f"VIS: Cruzó umbral {u}m")
            break

    # Techos (BKN/OVC)
    umbrales_nubes = [100, 200, 500, 1000, 1500]
    for u in umbrales_nubes:
        if (techo_r <= u < techo_t) or (techo_t <= u < techo_r):
            enmiendas.append(f"NUBES: Techo cruzó
