import streamlit as st
import requests
import re
import random
import pandas as pd
import io
from datetime import datetime, timezone
from streamlit_autorefresh import st_autorefresh

# --- 1. CONFIGURACIÓN Y ESTILOS GRÁFICOS RESTAURADOS ---
st.set_page_config(page_title="Vigilancia SAVC v5.2", page_icon="✈️", layout="wide")

st.sidebar.title("Configuración")
tema = st.sidebar.selectbox("Modo de Pantalla:", ["🌙 Noche", "☀️ Día"])

# CSS para restaurar la estética visual de "Tablero"
if tema == "🌙 Noche":
    main_bg = "#0e1117"
    card_bg = "#1d2129"
    text_c = "#ffffff"
    border_c = "#333"
else:
    main_bg = "#ffffff"
    card_bg = "#f0f2f6"
    text_c = "#000000"
    border_c = "#ddd"

st.markdown(f"""
    <style>
    .stApp {{ background-color: {main_bg}; color: {text_c}; }}
    .stExpander {{ 
        background-color: {card_bg} !important; 
        border: 1px solid {border_c} !important; 
        border-radius: 10px !important;
        box-shadow: 0px 4px 6px rgba(0,0,0,0.1) !important;
        margin-bottom: 10px !important;
    }}
    .stCode {{ background-color: #111 !important; color: #0f0 !important; border-radius: 5px; }}
    #MainMenu, footer, .stDeployButton, header {{ visibility: hidden; }}
    .reportview-container .main .block-container {{ padding-top: 1rem; }}
    </style>
""", unsafe_allow_html=True)

st.sidebar.divider()
if st.sidebar.button("🔄 Actualizar Ahora"):
    st.rerun()

if 'log_alertas' not in st.session_state:
    st.session_state.log_alertas = []

st_autorefresh(interval=1800000, key="auto_refresh")

API_KEY = "8e7917816866402688f805f637eb54d3"
AERODROMOS = ["SAVV","SAVE","SAVT","SAWC","SAVC","SAWG","SAWE","SAWH"]
ICAO_STRING = ",".join(AERODROMOS)

# --- 2. MOTOR DE PROCESAMIENTO ---

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
    partes = re.split(r'\b(FM|BECMG|TEMPO|PROB\d{2})\b', cuerpo)
    vigente = partes[0] 
    for i in range(1, len(partes), 2):
        ind, cont = partes[i], partes[i+1]
        m_r = re.search(r'(\d{2})(\d{2})/(\d{2})(\d{2})', cont)
        m_f = re.search(r'FM(\d{2})(\d{2})(\d{2})', cont)
        if m_r:
            di, hi, df, hf = map(int, m_r.groups())
            if (di * 10000 + hi * 100) <= ref < (df * 10000 + hf * 100): vigente = f"{ind} {cont}"
        elif m_f:
            di, hi, mi = map(int, m_f.groups())
            if ref >= (di * 10000 + hi * 100 + mi): vigente = f"FM {cont}"
    return vigente.strip()

def auditar_v52(icao, metar, taf):
    p_vigente = obtener_bloque_vigente(taf)
    alertas = []
    vm, vp = get_token_vis(metar), get_token_vis(p_vigente)
    umbrales_v = [150, 350, 600, 800, 1500, 3000, 5000]
    ev_m = next((i for i, u in enumerate(umbrales_v) if vm < u), 8)
    ev_p = next((i for i, u in enumerate(umbrales_v) if vp < u), 8)
    if ev_m != ev_p and not (vm >= 9999 and vp >= 5000):
        alertas.append(f"VIS: Cambio umbral SMN (M: {vm}m / TAF: {vp}m)")
    return alertas, p_vigente

# --- 3. INTERFAZ Y RENDERIZADO DE LOS 8 AERODROMOS ---
st.title("🖥️ Monitor de Vigilancia Meteorológica - SAVC")
st.write(f"**Actualización Automática (UTC):** {datetime.now(timezone.utc).strftime('%H:%M:%S')}")

cols = st.columns(2)
headers = {"X-API-Key": API_KEY}

try:
    r_id = random.randint(1, 99999)
    res_metar_raw = requests.get(f"https://api.checkwx.com/metar/{ICAO_STRING}?cache={r_id}", headers=headers).json().get('data', [])
    res_taf_raw = requests.get(f"https://api.checkwx.com/taf/{ICAO_STRING}?cache={r_id}", headers=headers).json().get('data', [])

    for i, icao in enumerate(AERODROMOS):
        m_r = next((m for m in res_metar_raw if icao in m), None)
        t_r = next((t for t in res_taf_raw if icao in t), None)
        
        with cols[i % 2]:
            if m_r and t_r:
                alertas, p_vigente = auditar_v52(icao, m_r, t_r)
                status_icon = "🟥" if alertas else ("🟨" if "SPECI" in m_r else "✅")
                weather_icon = get_clima_icon(m_r)
                
                with st.expander(f"{status_icon} {weather_icon} {icao}", expanded=True):
                    st.markdown("**TAF VIGENTE:**")
                    st.code(p_vigente, language=None)
                    st.markdown("**METAR ACTUAL:**")
                    st.success(m_r)
                    for a in alertas:
                        st.error(a)
                        entry = {"Hora UTC": datetime.now(timezone.utc).strftime("%H:%M"), "OACI": icao, "Detalle": a, "Reporte": m_r}
                        if not any(l['OACI']==icao and l['Detalle']==a for l in st.session_state.log_alertas[-3:]):
                            st.session_state.log_alertas.append(entry)
            else:
                with st.expander(f"⚪ ✈️ {icao}", expanded=True):
                    st.warning(f"Consultando datos de {icao}...")

except Exception as e:
    st.error(f"Error de conexión: {e}")

# --- 4. LOG Y EXCEL ---
if st.session_state.log_alertas:
    st.divider()
    c_log, c_xls = st.columns([3, 1])
    with c_log: st.subheader("📊 Registro de Alertas")
    with c_xls:
        df_log = pd.DataFrame(st.session_state.log_alertas)
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df_log.to_excel(writer, index=False, sheet_name='Log')
        st.download_button(label="📥 Descargar Excel", data=output.getvalue(), 
                           file_name=f"Log_Alertas_{datetime.now().strftime('%H%M')}.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    st.table(df_log.tail(10))

st.markdown(f"""<hr><div style="text-align: center; color: #777; font-size: 0.9rem; padding-bottom: 20px;">
    Desarrollado en colaboración por <b>Gemini AI</b> & <b>Tu Usuario</b><br>
    © {datetime.now().year} - Vigilancia Aeronáutica FIR SAVC (Comodoro Rivadavia)
</div>""", unsafe_allow_html=True)
