import streamlit as st
import requests
import re
import random
import pandas as pd
import io
from datetime import datetime, timezone
from streamlit_autorefresh import st_autorefresh

# --- 1. CONFIGURACIÓN Y ESTILOS DINÁMICOS ---
st.set_page_config(page_title="Vigilancia SAVC v5.2", page_icon="✈️", layout="wide")

# Barra lateral: Configuración y Modo Pantalla
st.sidebar.title("Configuración")
tema = st.sidebar.selectbox("Modo de Pantalla:", ["🌙 Noche", "☀️ Día"])

# CSS Dinámico para Modo Día/Noche y limpieza de interfaz
if tema == "🌙 Noche":
    st.markdown("""<style>
        .stApp { background-color: #0e1117; color: #ffffff; }
        .stExpander { background-color: #1d2129 !important; border: 1px solid #333; }
        .stCode { background-color: #111 !important; color: #0f0 !important; }
        #MainMenu, footer, .stDeployButton, header {visibility: hidden;}
    </style>""", unsafe_allow_html=True)
else:
    st.markdown("""<style>
        .stApp { background-color: #ffffff; color: #000000; }
        .stExpander { background-color: #f0f2f6 !important; border: 1px solid #ddd; }
        #MainMenu, footer, .stDeployButton, header {visibility: hidden;}
    </style>""", unsafe_allow_html=True)

st.sidebar.divider()
if st.sidebar.button("🔄 Actualizar Ahora"):
    st.rerun()

# Inicializar log de alertas si no existe
if 'log_alertas' not in st.session_state:
    st.session_state.log_alertas = []

# Auto-refresco cada 30 minutos
st_autorefresh(interval=1800000, key="auto_refresh")

API_KEY = "8e7917816866402688f805f637eb54d3"
AERODROMOS = ["SAVV","SAVE","SAVT","SAWC","SAVC","SAWG","SAWE","SAWH"]
ICAO_STRING = ",".join(AERODROMOS)

# --- 2. FUNCIONES DE PROCESAMIENTO ---

def get_clima_icon(metar):
    if "TS" in metar: return "⛈️"
    if "RA" in metar: return "🌧️"
    if "FG" in metar or "BR" in metar: return "🌫️"
    if "CAVOK" in metar: return "☀️"
    return "✈️"

def get_token_vis(texto):
    if any(x in texto for x in ["CAVOK", "SKC", "NSC", "CLR"]): return 9999
    t_limpio = re.sub(r'\d{4}/\d{4}', '', texto)
    tokens = t_limpio.split()
    for t in tokens:
        if "/" in t or "Z" in t or t.startswith("FM") or len(t) != 4: continue
        if re.fullmatch(r'\d{4}', t): return int(t)
    return 9999

def obtener_bloque_vigente(taf_raw):
    ahora = datetime.now(timezone.utc)
    ref = ahora.day * 10000 + ahora.hour * 100 + ahora.minute
    cuerpo = re.sub(r'^(TAF\s+)?([A-Z]{4})\s+\d{6}Z\s+', '', taf_raw)
    part
