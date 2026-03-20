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

# Estilos e Interfaz
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

# --- 2. FUNCIONES TÉCNICAS (AUDITORÍA DETALLADA) ---
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

def auditar_detallado(reporte, taf):
    motivos = []
    dr, vr = parse_viento(reporte)
    dt, vt = parse_viento(taf)
    vis_r, ceil_r = parse_vis_ceil(reporte)
    vis_t, ceil_t = parse_vis_ceil(taf)
    
    # 1. Viento
    if vr is not None and vt is not None:
        diff = abs(dr - dt)
        if (diff if diff <= 180 else 360 - diff) >= 60 and (vr >= 10 or vt >= 10):
            motivos.append("GIRO VTO >= 60°")
        if abs(vr - vt) >= 10:
            motivos.append(f"DIF INTENSIDAD {abs(vr-vt)}kt")
    
    # 2. Visibilidad (Umbrales SMN)
    for u in [150, 350, 600, 800, 1500, 3000, 5000]:
