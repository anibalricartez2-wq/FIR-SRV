import streamlit as st
import requests
import re
import random
import pandas as pd
from datetime import datetime, timezone
from streamlit_autorefresh import st_autorefresh

# --- 1. CONFIGURACIÓN ---
st.set_page_config(page_title="Vigilancia FIR SAVC - Visual", page_icon="✈️", layout="wide")

if 'historial_alertas' not in st.session_state:
    st.session_state.historial_alertas = []

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

# Refresco cada 30 minutos (1.800.000 ms)
st_autorefresh(interval=1800000, key="datarefresh")

API_KEY = "8e7917816866402688f805f637eb54d3"
AERODROMOS = ["SAVV","SAVE","SAVT","SAWC","SAVC","SAWG","SAWE","SAWH"]

# --- 2. MOTOR DE LÓGICA Y TIEMPO ---

def obtener_periodo_vigente(taf_text):
    """Detecta el grupo TAF FM/BECMG/TEMPO que aplica AHORA (UTC)"""
    ahora_utc = datetime.now(timezone.utc)
    h_actual, d_actual = ahora_utc.hour, ahora_utc.day
    partes = re.split(r'\b(FM|BECMG|TEMPO|PROB\d{2})\b', taf_text)
    vigente = partes[0] # Base
    for i in range(1, len(partes), 2):
        indicador, contenido = partes[i], partes[i+1]
        match = re.search(r'(\d{2})(\d{2})/(\d{2})(\d{2})', contenido)
        if match:
            d_i, h_i, d_f, h_f = map(int, match.groups())
            if d_i <= d_actual <= d_f:
                if h_i <= h_actual < h_f: vigente = f"{indicador} {contenido}"
    return vigente.strip()

def parse_viento(texto):
    match = re.search(r'\b(\d{3})(\d{2,3})(G\d{2,3})?KT\b', texto)
    return (int(match.group(1)), int(match.group(2)), int(match.group(3)[1:]) if match.group(3) else 0) if match else (None, None, None)

def parse_visibilidad(texto):
    if "CAVOK" in texto: return 9999
    match = re.search(r'\b(\d{4})\b', texto)
    return int(match.group(1)) if match else 9999

def parse_nubes(texto):
    capas = re.findall(r'\b(BKN|OVC)(\d{3})\b', texto)
    return min(int(c[1]) * 100 for c in capas) if capas else 9999

def extraer_fenos(texto):
    codigos = ["TS", "VA", "RA", "SN", "DZ", "FG", "BR", "HZ", "FU", "SQ", "FC", "FZRA"]
    palabras = texto.split()
    return set(p for p in palabras if any(c in p.replace("+","").replace("-","") for c in codigos) and len(p) <= 5)

def obtener_icono_condicion(metar_text):
    """Mapeo avanzado: Icono de condición + Icono de intensidad (+)"""
    icon_cond = "✈️" # Default aviación
    icon_int = "⚠️ " if "+" in metar_text else "" # Triángulo de advertencia para Fuerte
    
    # Prioridad de Fenómenos
    if "TS" in metar_text: icon_cond = "⛈️" # Tormenta
    elif "VA" in metar_text: icon_cond = "🌋" # Ceniza
    elif "SQ" in metar_text: icon_cond = "💨" # Turbonada
    elif "FC" in metar_text: icon_cond = "🌪️" # Tornado/Embudo
    elif "SN" in metar_text or "SG" in metar_text: icon_cond = "❄️" # Nieve
    elif "RA" in metar_text or "DZ" in metar_text: icon_cond = "🌧️" # Lluvia
    elif "FG" in metar_text
