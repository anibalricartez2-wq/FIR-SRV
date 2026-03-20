import streamlit as st
import requests
import re
import random
import pandas as pd
from datetime import datetime, timezone
from streamlit_autorefresh import st_autorefresh

# --- 1. CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Vigilancia FIR SAVC", page_icon="✈️", layout="wide")

if 'historial_alertas' not in st.session_state:
    st.session_state.historial_alertas = []

# CSS para limpieza visual
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

# Auto-refresco cada 30 minutos
st_autorefresh(interval=1800000, key="datarefresh")

API_KEY = "8e7917816866402688f805f637eb54d3"
AERODROMOS = ["SAVV","SAVE","SAVT","SAWC","SAVC","SAWG","SAWE","SAWH"]

# --- 2. FUNCIONES DE PROCESAMIENTO ---

def obtener_periodo_vigente(taf_text):
    """Extrae la sección del TAF que aplica a la hora UTC actual"""
    ahora_utc = datetime.now(timezone.utc)
    h_actual, d_actual = ahora_utc.hour, ahora_utc.day
    # Separar por grupos de cambio
    partes = re.split(r'\b(FM|BECMG|TEMPO|PROB\d{2})\b', taf_text)
    vigente = partes[0] # Base por defecto
    
    for i in range(1, len(partes), 2):
        indicador, contenido = partes[i], partes[i+1]
        match = re.search(r'(\d{2})(\d{2})/(\d{2})(\d{2})', contenido)
        if match:
            d_i, h_i, d_f, h_f = map(int, match.groups())
            # Verificamos si la hora actual cae dentro del rango del grupo
            if d_i <= d_actual <= d_f:
                if h_i <= h_actual < h_f:
                    vigente = f"{indicador} {contenido}"
    return vigente.strip()

def parse_viento(texto):
    match = re.search(r'\b(\d{3})(\d{2,3})(G\d{2,3})?KT\b', texto)
    if match:
        d, v = int(match.group(1)), int(match.group(2))
        g = int(match.group(3)[1:]) if match.group(3) else 0
        return d, v, g
    return None, None, None

def parse_visibilidad(texto):
    if "CAVOK" in texto: return 9999
    match = re.search(r'\b(\d{4})\b', texto)
    return int(match.group(1)) if match else 9999

def parse_nubes(texto):
    # Criterio SMN: Solo bases BKN u OVC
    capas = re.findall(r'\b(BKN|OVC)(\d{3})\b', texto)
    return min(int(c[1]) * 100 for c in capas) if capas else 9999

def extraer_fenos(texto):
    """Detecta códigos de fenómenos e intensidades +/-"""
    codigos = ["TS", "VA", "RA", "SN", "DZ", "FG", "BR", "HZ", "FU", "SQ", "FC", "FZRA"]
    palabras = texto.split()
    return set(p for p in palabras if any(c in p.replace("+","").replace("-","") for c in codigos) and len(p) <= 5)

def obtener_icono_clima(metar_text):
    """Asigna icono según fenómeno principal e intensidad"""
    icon_cond = "✈️"
    icon_int = "⚠️ " if "+" in metar_text else ""
    if "TS" in metar_text: icon_cond = "⛈️"
    elif "VA" in metar_text: icon_cond = "🌋"
    elif "RA" in metar_text or "DZ" in metar_text: icon_cond = "🌧️"
    elif "SN" in metar_text: icon_cond = "❄️"
    elif "FG" in metar_text or "BR" in metar_text: icon_cond = "🌫️"
    elif "SQ" in metar_text: icon_cond = "💨"
    elif "CAVOK" in metar_text or "SKC" in metar_text: icon_cond = "☀️"
    elif "BKN" in metar_text or "OVC" in metar_text: icon_cond = "☁️"
    elif "SCT" in metar_text or "FEW" in metar_text: icon_cond = "⛅"
    return f"{icon_int}{icon_cond}"

def auditar(icao, metar, taf_completo):
    periodo = obtener_periodo_vigente(taf_completo)
    enmiendas = []
    
    dr, vr, gr = parse_viento(metar)
    dt, vt, gt = parse_viento(periodo)
    vm, vp = parse_visibilidad(metar), parse_visibilidad(periodo)
    nm, np = parse_nubes(metar), parse_nubes(periodo)
    fm, fp = extraer_fenos(metar), extraer_fenos(periodo)

    # 1. VIENTO
    if vr is not None and vt is not None:
        if (vr >= 10 or vt >= 10) and abs(dr - dt) >= 60: enmiendas.append("VIENTO: Giro >= 60°")
        if abs(vr - vt) >= 10: enmiendas.append("VIENTO: Dif. Vel. media >= 10kt")
        if (vr >= 15 or vt >= 15) and abs(gr - gt) >= 10: enmiendas.append("VIENTO: Ráfaga (Dif >= 10kt)")

    # 2. VISIBILIDAD (Umbrales SMN)
    for u in [150, 350, 600, 800, 1500, 3000, 5000]:
        if (vm <= u < vp) or (vp <= u < vm):
            enmiendas.append(f"VIS: Pasó umbral {u}m")
            break

    # 3. TECHOS
    for u in [100, 200, 500, 1000, 1500]:
        if (nm <= u < np) or (np <= u < nm):
            enmiendas.append(f"NUBES: Techo pasó {u}ft")
            break

    # 4. FENÓMENOS
    diff = fm.symmetric_difference(fp)
    if diff:
        for c in diff: enmiendas.append(f"FENÓMENO: Cambio en {c}")

    return enmiendas, periodo

# --- 3. INTERFAZ DE USUARIO ---
st.title("🖥️ Monitor de Vigilancia Meteor
