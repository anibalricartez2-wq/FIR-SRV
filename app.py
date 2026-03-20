import streamlit as st
import requests
import re
import random
import pandas as pd
from datetime import datetime, timezone
from streamlit_autorefresh import st_autorefresh

# --- 1. CONFIGURACIÓN Y CRÉDITOS ---
st.set_page_config(page_title="Vigilancia SAVC v5.0", page_icon="✈️", layout="wide")

# Selector de Pantalla (Ancho o Centrado)
layout_choice = st.sidebar.radio("Tipo de Pantalla:", ["Wide (Ancho)", "Centered (Centrado)"])
if layout_choice == "Centered (Centrado)":
    st.markdown("""<style>.block-container {max-width: 800px;}</style>""", unsafe_allow_html=True)

if 'log_alertas' not in st.session_state:
    st.session_state.log_alertas = []

# Ocultar basura de Streamlit (Panel de código y footer original)
hide_style = """
    <style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    .stDeployButton {display:none;}
    </style>
"""
st.markdown(hide_style, unsafe_allow_html=True)

st_autorefresh(interval=1800000, key="auto_refresh")

API_KEY = "8e7917816866402688f805f637eb54d3"
AERODROMOS = ["SAVV","SAVE","SAVT","SAWC","SAVC","SAWG","SAWE","SAWH"]

# --- 2. MOTOR DE PARSEO Y TIEMPOS ---

def get_token_vis(texto):
    """Filtra tokens para hallar visibilidad real (ignora grupos / o Z)"""
    if any(x in texto for x in ["CAVOK", "SKC", "NSC"]): return 9999
    tokens = texto.split()
    for t in tokens:
        if "/" in t or "Z" in t or t.startswith("FM"): continue
        if re.fullmatch(r'\d{4}', t): return int(t)
    return 9999

def obtener_bloque_vigente(taf_raw):
    ahora = datetime.now(timezone.utc)
    ref = ahora.day * 10000 + ahora.hour * 100 + ahora.minute
    cuerpo = re.sub(r'^(TAF\s+)?([A-Z]{4})\s+\d{6}Z\s+', '', taf_raw)
    partes = re.split(r'\b(FM|BECMG|TEMPO|PROB\d{2})\b', cuerpo)
    vigente = partes[0]
    for i in range(1, len(partes), 2):
        ind, cont = partes[i], partes[i+1]
        m_r = re.search(r'(\d{2})(\d{2})/(\d{2})(\d{2})', cont)
        m_f = re.search(r'FM(\d{2})(\d{2})(\d{2})', cont)
        valido = False
        if m_r:
            di, hi, df, hf = map(int, m_r.groups())
            if (di * 10000 + hi * 100) <= ref < (df * 10000 + hf * 100): valido = True
        elif m_f:
            di, hi, mi = map(int, m_f.groups())
            if ref >= (di * 10000 + hi * 100 + mi): valido = True
        if valido: vigente = cont
    return vigente.strip()

def get_clima_icon(metar):
    if "TS" in metar: return "⛈️"
    if "VA" in metar: return "🌋"
    if "SN" in metar: return "❄️"
    if "RA" in metar or "DZ" in metar: return "🌧️"
    if "FG" in metar or "BR" in metar: return "🌫️"
    if "HZ" in metar or "FU" in metar: return "🌫️"
    if "CAVOK" in metar: return "☀️"
    if "BKN" in metar or "OVC" in metar: return "☁️"
    return "✈️"

# --- 3. AUDITORÍA SEGÚN UMBRALES PDF ---

def auditar_v5(icao, metar, taf):
    p_vigente = obtener_bloque_vigente(taf)
    alertas = []
    
    # Visibilidad (Escalones SMN)
    vm, vp = get_token_vis(metar), get_token_vis(p_vigente)
    umbrales_v = [150, 350, 600, 800, 1500, 3000, 5000]
    ev_m = next((i for i, u in enumerate(umbrales_v) if vm < u), 8)
    ev_p = next((i for i, u in enumerate(umbrales_v) if vp < u), 8)
    
    if ev_m != ev_p and not (vm >= 9999 and vp >= 5000):
        alertas.append(f"VIS: Cambio umbral SMN (M: {vm}m / T: {vp}m)")

    # Techos (BKN/OVC)
    def get_c(t):
        capas = re.findall(r'\b(BKN|OVC)(\d{3})\b', t)
        return min(int(c[1]) * 100 for c in capas) if capas else 9999
    nm, np = get_c(metar), get_c(p_vigente)
    for u in [100, 200, 500, 1000, 1500]:
        if (nm < u <= np) or (np < u <= nm):
            alertas.append(f"NUBES: Techo cruzó {u}ft")
            break
            
    return alertas, p_vigente

# --- 4. INTERFAZ Y LOG ---
st.title("🖥️ Monitor de Vigilancia Meteorológica - SAVC")
st.subheader("Auditoría en Tiempo Real de Enmiendas (Criterios SMN)")

cols = st.columns(2)
headers = {"X-API-Key": API_KEY}

for i, icao in enumerate(AERODROMOS):
    try:
        r_id = random.randint(1, 999)
        m_r = requests.get(f"https://api.checkwx.com/metar/{icao}?cache={r_id}", headers=headers).json().get('data',['-'])[0]
        t_r = requests.get(f"https://api.checkwx.com/taf/{icao}?cache={r_id}", headers=headers).json().get('data',['-'])[0]
        
        if m_r != '-' and t_r != '-':
            alertas, p_vigente = auditar_v5(icao, m_r, t_r)
            status_icon = "🟥" if alertas else "✅"
            weather_icon = get_clima_icon(m_r)
            
            with cols[i % 2]:
                with st.expander(f"{status_icon} {weather_icon} {icao} - Ver Detalles", expanded=True):
                    st.write(f"**VIGENTE:** `{p_vigente}`")
                    st.success(f"**METAR:** `{m_r}`")
                    for a in alertas:
                        st.error(a)
                        # Registrar en Log si es nueva
                        if not any(l['OACI']==icao and l['Alerta']==a for l in st.session_state.log_alertas[-5:]):
                            st.session_state.log_alertas.append({"Hora": datetime.now().strftime("%H:%M"), "OACI": icao, "Alerta": a})
    except:
        st.error(f"Falla de datos: {icao}")

# --- 5. LOG Y CRÉDITOS ---
st.divider()
if st.session_state.log_alertas:
    with st.expander("📊 Log de Novedades del Turno", expanded=False):
        st.table(pd.DataFrame(st.session_state.log_alertas).tail(10))

st.markdown(f"""
    <div style="text-align: center; color: #888; padding: 20px;">
        <p>Desarrollado por <b>Gemini AI</b> & <b>Tu Usuario</b></p>
        <p>© {datetime.now().year} - Vigilancia Aeronáutica FIR SAVC (Comodoro Rivadavia)</p>
    </div>
""", unsafe_allow_html=True)
