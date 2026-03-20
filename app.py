import streamlit as st
import requests
import re
import random
import pandas as pd
from datetime import datetime, timezone
from streamlit_autorefresh import st_autorefresh

# --- 1. CONFIGURACIÓN, TEMAS Y LAYOUT ---
st.set_page_config(page_title="Vigilancia SAVC v5.4", page_icon="✈️", layout="wide")

# Ocultar menús de código, deploy y decoraciones de Streamlit
st.markdown("""
    <style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    .stDeployButton {display:none;}
    [data-testid="stHeader"] {display: none;}
    .reportview-container .main .block-container {padding-top: 0rem;}
    </style>
""", unsafe_allow_html=True)

# Selector de Pantalla y Tema en barra lateral
st.sidebar.title("Configuración SAVC")
layout_choice = st.sidebar.radio("Disposición:", ["Ancho (Grilla)", "Centrado (Lista)"])
theme_choice = st.sidebar.radio("Modo Operativo:", ["☀️ Día", "🌙 Noche"])

# Lógica de colores según el tema
if theme_choice == "🌙 Noche":
    bg_color = "#0e1117"
    text_color = "#ffffff"
    card_bg = "#1f2937"
    st.markdown(f"""
        <style>
        .stApp {{ background-color: {bg_color}; color: {text_color}; }}
        .stCode {{ background-color: #2d3748 !important; color: #e2e8f0 !important; }}
        .stExpander {{ background-color: {card_bg} !important; border: 1px solid #374151; }}
        h1, h2, h3, h4, p, span, label {{ color: {text_color} !important; }}
        </style>
    """, unsafe_allow_html=True)
else:
    st.markdown("""<style>.stCode { background-color: #f0f2f6 !important; }</style>""", unsafe_allow_html=True)

if layout_choice == "Centrado (Lista)":
    st.markdown("""<style>.block-container {max-width: 900px;}</style>""", unsafe_allow_html=True)

if 'log_alertas' not in st.session_state:
    st.session_state.log_alertas = []

# Refresco cada 3 minutos
st_autorefresh(interval=180000, key="auto_refresh")

API_KEY = "8e7917816866402688f805f637eb54d3"
AERODROMOS = ["SAVV","SAVE","SAVT","SAWC","SAVC","SAWG","SAWE","SAWH"]

# --- 2. MOTOR DE PROCESAMIENTO ---

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
        if valido: vigente = f"{ind} {cont}" if ind != "FM" else f"FM {cont}"
    return vigente.strip()

def get_clima_icon(metar):
    if "TS" in metar: return "⛈️"
    if "RA" in metar or "DZ" in metar: return "🌧️"
    if "FG" in metar or "BR" in metar: return "🌫️"
    if "CAVOK" in metar: return "☀️"
    return "✈️"

# --- 3. AUDITORÍA (CRITERIOS SMN) ---

def auditar_v54(icao, metar, taf):
    p_vigente = obtener_bloque_vigente(taf)
    alertas = []
    vm, vp = get_token_vis(metar), get_token_vis(p_vigente)
    umbrales_v = [150, 350, 600, 800, 1500, 3000, 5000]
    ev_m = next((i for i, u in enumerate(umbrales_v) if vm < u), 8)
    ev_p = next((i for i, u in enumerate(umbrales_v) if vp < u), 8)
    if ev_m != ev_p and not (vm >= 9999 and vp >= 5000):
        alertas.append(f"VIS: Cambio umbral SMN (M: {vm}m / TAF: {vp}m)")

    def get_c(t):
        capas = re.findall(r'\b(BKN|OVC)(\d{3})\b', t)
        return min(int(c[1]) * 100 for c in capas) if capas else 9999
    nm, np = get_c(metar), get_c(p_vigente)
    for u in [100, 200, 500, 1000, 1500]:
        if (nm < u <= np) or (np < u <= nm):
            alertas.append(f"NUBES: Techo cruzó {u}ft")
            break
    return alertas, p_vigente

# --- 4. INTERFAZ ---
st.title("🖥️ Auditoría Meteorológica FIR SAVC")
st.write(f"Actualización UTC: {datetime.now(timezone.utc).strftime('%H:%M:%S')}")

cols = st.columns(2)
headers = {"X-API-Key": API_KEY}

for i, icao in enumerate(AERODROMOS):
    try:
        r_id = random.randint(1, 99999)
        m_r = requests.get(f"https://api.checkwx.com/metar/{icao}?cache={r_id}", headers=headers).json().get('data',['-'])[0]
        t_r = requests.get(f"https://api.checkwx.com/taf/{icao}?cache={r_id}", headers=headers).json().get('data',['-'])[0]
        
        if m_r != '-' and t_r != '-':
            alertas, p_vigente = auditar_v54(icao, m_r, t_r)
            icon_alert = "🟥" if alertas else "✅"
            weather_icon = get_clima_icon(m_r)
            
            with cols[i % 2]:
                with st.expander(f"{icon_alert} {weather_icon} {icao}", expanded=True):
                    st.markdown("**INFORME TAF VIGENTE:**")
                    st.code(p_vigente, language=None)
                    st.markdown("**METAR ACTUAL:**")
                    st.success(m_r)
                    for a in alertas:
                        st.error(a)
                        if not any(l['OACI']==icao and l['Alerta']==a for l in st.session_state.log_alertas[-3:]):
                            st.session_state.log_alertas.append({"Hora": datetime.now().strftime("%H:%M"), "OACI": icao, "Alerta": a})
                    st.caption(f"Ref TAF: {t_r}")
    except:
        st.error(f"Error {icao}")

# --- 5. LOG Y CRÉDITOS FINALES ---
if st.session_state.log_alertas:
    st.divider()
    with st.expander("📊 Log de Novedades del Turno"):
        st.table(pd.DataFrame(st.session_state.log_alertas).tail(10))

st.markdown(f"""
    <hr>
    <div style="text-align: center; color: #777; font-size: 0.9rem; padding-bottom: 40px; line-height: 1.6;">
        <b>SISTEMA DE VIGILANCIA AERONÁUTICA SAVC</b><br>
        Desarrollado en colaboración por <b>Gemini AI</b> & <b>Despachante de Aeronaves</b><br>
        © {datetime.now().year} - Comodoro Rivadavia, Chubut.
    </div>
""", unsafe_allow_html=True)
