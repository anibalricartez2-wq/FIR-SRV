import streamlit as st
import requests
import re
import random
import pandas as pd
from datetime import datetime, timezone
from streamlit_autorefresh import st_autorefresh

# --- 1. CONFIGURACIÓN Y ESTILOS ---
st.set_page_config(page_title="Vigilancia SAVC v5.2", page_icon="✈️", layout="wide")

st.sidebar.title("Configuración")
tema = st.sidebar.selectbox("Modo de Pantalla:", ["🌙 Noche", "☀️ Día"])

# Inyección de CSS para temas y ocultar menús (Limpio como pediste)
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

if 'log_alertas' not in st.session_state:
    st.session_state.log_alertas = []

# Refresco cada 30 minutos para cuidar el plan de la API
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

# --- 3. INTERFAZ DE USUARIO ---
st.title("🖥️ Monitor de Vigilancia Meteorológica - SAVC")
st.write(f"**Actualización Automática (UTC):** {datetime.now(timezone.utc).strftime('%H:%M:%S')}")

# Aseguramos la grilla de 2 columnas
cols = st.columns(2)
headers = {"X-API-Key": API_KEY}

try:
    r_id = random.randint(1, 99999)
    # Una sola llamada para traer todo el FIR
    res_metar_raw = requests.get(f"https://api.checkwx.com/metar/{ICAO_STRING}?cache={r_id}", headers=headers).json().get('data', [])
    res_taf_raw = requests.get(f"https://api.checkwx.com/taf/{ICAO_STRING}?cache={r_id}", headers=headers).json().get('data', [])

    # EL BUCLE AHORA RECORRE LOS 8 AERODROMOS OBLIGATORIAMENTE
    for i, icao in enumerate(AERODROMOS):
        # Buscamos el reporte que coincida con el OACI en la lista recibida
        m_r = next((m for m in res_metar_raw if icao in m), None)
        t_r = next((t for t in res_taf_raw if icao in t), None)
        
        with cols[i % 2]:
            # El expander se crea SIEMPRE, manteniendo la visualización de los 8
            if m_r and t_r:
                alertas, p_vigente = auditar_v52(icao, m_r, t_r)
                status_icon = "🟥" if alertas else ("🟨" if "SPECI" in m_r else "✅")
                weather_icon = get_clima_icon(m_r)
                
                with st.expander(f"{status_icon} {weather_icon} {icao}", expanded=True):
                    st.markdown("**INFORME TAF VIGENTE:**")
                    st.code(p_vigente, language=None)
                    st.markdown("**METAR ACTUAL:**")
                    st.success(m_r)
                    for a in alertas:
                        st.error(a)
                        log_entry = {"Hora": datetime.now().strftime("%H:%M"), "OACI": icao, "Alerta": a}
                        if not any(l['OACI']==icao and l['Alerta']==a for l in st.session_state.log_alertas[-3:]):
                            st.session_state.log_alertas.append(log_entry)
                    st.caption(f"Referencia TAF Completo: {t_r}")
            else:
                # Si falta la data de uno, el cuadro aparece igual pero con aviso
                with st.expander(f"⚪ ✈️ {icao}", expanded=True):
                    st.warning(f"Aguardando datos de {icao}...")

except Exception as e:
    st.error(f"Falla de conexión: {e}")

# --- 4. LOG Y CRÉDITOS ---
if st.session_state.log_alertas:
    st.divider()
    with st.expander("📊 Log de Novedades del Turno"):
        st.table(pd.DataFrame(st.session_state.log_alertas).tail(10))

st.markdown(f"""<hr><div style="text-align: center; color: #777; font-size: 0.9rem; padding-bottom: 20px;">
    Desarrollado en colaboración por <b>Gemini AI</b> & <b>Tu Usuario</b><br>
    © {datetime.now().year} - Vigilancia Aeronáutica FIR SAVC (Comodoro Rivadavia)
</div>""", unsafe_allow_html=True)
