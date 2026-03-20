import streamlit as st
import requests
import re
import random
import pandas as pd
from datetime import datetime, timezone
from streamlit_autorefresh import st_autorefresh

# --- 1. CONFIGURACIÓN ---
st.set_page_config(page_title="Vigilancia FIR SAVC", page_icon="✈️", layout="wide")

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

# Refresco cada 30 minutos
st_autorefresh(interval=1800000, key="datarefresh")

API_KEY = "8e7917816866402688f805f637eb54d3"
AERODROMOS = ["SAVV","SAVE","SAVT","SAWC","SAVC","SAWG","SAWE","SAWH"]

# --- 2. LÓGICA DE PARSEO Y TIEMPO ---

def obtener_periodo_vigente(taf_text):
    ahora_utc = datetime.now(timezone.utc)
    h_actual = ahora_utc.hour
    d_actual = ahora_utc.day
    
    partes = re.split(r'\b(FM|BECMG|TEMPO|PROB\d{2})\b', taf_text)
    vigente = partes[0] # Base por defecto
    
    for i in range(1, len(partes), 2):
        indicador = partes[i]
        contenido = partes[i+1]
        match = re.search(r'(\d{2})(\d{2})/(\d{2})(\d{2})', contenido)
        if match:
            d_i, h_i, d_f, h_f = map(int, match.groups())
            if d_i <= d_actual <= d_f:
                if h_i <= h_actual < h_f:
                    vigente = f"{indicador} {contenido}"
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
    codigos = ["TS", "VA", "RA", "SN", "DZ", "FG", "BR", "HZ", "FU", "SQ", "FZRA"]
    palabras = texto.split()
    return set(p for p in palabras if any(c in p.replace("+","").replace("-","") for c in codigos) and len(p) <= 5)

def auditar(icao, metar, taf_completo):
    periodo = obtener_periodo_vigente(taf_completo)
    enmiendas = []
    
    # Datos comparativos
    dr, vr, gr = parse_viento(metar)
    dt, vt, gt = parse_viento(periodo)
    vm, v_prev = parse_visibilidad(metar), parse_visibilidad(periodo)
    nm, n_prev = parse_nubes(metar), parse_nubes(periodo)
    fm, f_prev = extraer_fenos(metar), extraer_fenos(periodo)

    # Viento
    if vr is not None and vt is not None:
        if (vr >= 10 or vt >= 10) and abs(dr - dt) >= 60: enmiendas.append("VIENTO: Giro >= 60°")
        if abs(vr - vt) >= 10: enmiendas.append("VIENTO: Dif. Vel. >= 10kt")
    
    # Visibilidad (Umbrales SMN)
    for u in [150, 350, 600, 800, 1500, 3000, 5000]:
        if (vm <= u < v_prev) or (v_prev <= u < vm):
            enmiendas.append(f"VIS: Pasó umbral {u}m")
            break

    # Techos
    for u in [100, 200, 500, 1000, 1500]:
        if (nm <= u < n_prev) or (n_prev <= u < nm):
            enmiendas.append(f"NUBES: Techo pasó {u}ft")
            break

    # Fenómenos
    diff = fm.symmetric_difference(f_prev)
    if diff:
        for c in diff: enmiendas.append(f"FENÓMENO: Cambio en {c}")

    return enmiendas, periodo

# --- 3. INTERFAZ ---
st.title("🖥️ Vigilancia FIR SAVC - Comparativa Temporal")

cols = st.columns(2)
headers = {"X-API-Key": API_KEY}

for i, icao in enumerate(AERODROMOS):
    try:
        r_hash = random.randint(1, 999999)
        m_raw = requests.get(f"https://api.checkwx.com/metar/{icao}?cache={r_hash}", headers=headers).json().get('data',['-'])[0]
        t_raw = requests.get(f"https://api.checkwx.com/taf/{icao}?cache={r_hash}", headers=headers).json().get('data',['-'])[0]
        
        if m_raw != '-' and t_raw != '-':
            alertas, periodo_v = auditar(icao, m_raw, t_raw)
            estado = "⚠️ ENMIENDA" if alertas else "✅ OK"
            
            with cols[i % 2]:
                with st.expander(f"{icao} - {estado}", expanded=True):
                    # 1. TAF COMPLETO
                    st.markdown("**TAF COMPLETO:**")
                    st.caption(t_raw)
                    
                    st.divider()
                    
                    # 2. PERIODO VIGENTE (LO QUE EL BOT MIRA)
                    st.markdown(f"**PERIODO ANALIZADO (Basado en hora UTC):**")
                    st.code(periodo_v)
                    
                    # 3. METAR
                    st.markdown(f"**METAR ACTUAL:**")
                    st.success(m_raw)
                    
                    for a in alertas:
                        st.error(a)
                        if not st.session_state.historial_alertas or st.session_state.historial_alertas[-1]['Criterio'] != a:
                            st.session_state.historial_alertas.append({"Hora": datetime.now().strftime("%H:%M"), "OACI": icao, "Criterio": a})
    except:
        st.error(f"Falla de conexión en {icao}")

if st.session_state.historial_alertas:
    with st.expander("📊 Log del Turno"):
        st.table(pd.DataFrame(st.session_state.historial_alertas).tail(10))

st.markdown(f'<div class="copyright">© {datetime.now().year} - Usuario & Gemini AI. Auditoría estricta según Tabla SMN.</div>', unsafe_allow_html=True)
