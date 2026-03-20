import streamlit as st
import requests
import re
import random
import pandas as pd
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

# --- 1. CONFIGURACIÓN ---
st.set_page_config(page_title="Vigilancia FIR SAVC", page_icon="✈️", layout="wide")

# Inicializar el historial en la memoria de la sesión
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

# 1. REFRESH ACTUALIZADO A 30 MINUTOS (30 * 60 * 1000 ms)
st_autorefresh(interval=1800000, key="datarefresh")

API_KEY = "8e7917816866402688f805f637eb54d3"
AERODROMOS = ["SAVV","SAVE","SAVT","SAWC","SAVC","SAWG","SAWE","SAWH"]

# --- 2. FUNCIONES TÉCNICAS ---

def obtener_icono_clima(metar_text):
    """Mapeo de fenómenos meteorológicos a iconos visuales"""
    if "TS" in metar_text: return "⛈️" 
    if "VA" in metar_text: return "🌋" # Ceniza volcánica
    if "RA" in metar_text or "DZ" in metar_text: return "🌧️"
    if "SN" in metar_text: return "❄️"
    if "FG" in metar_text or "BR" in metar_text: return "🌫️"
    if "HZ" in metar_text or "FU" in metar_text: return "🌫️"
    if "VCTS" in metar_text: return "⚡" # Tormentas en las cercanías
    if "SKC" in metar_text or "CLR" in metar_text or "NSC" in metar_text: return "☀️"
    if "BKN" in metar_text or "OVC" in metar_text: return "☁️"
    if "SCT" in metar_text or "FEW" in metar_text: return "⛅"
    return "✈️"

def diff_angular(d1, d2):
    diff = abs(d1 - d2)
    return diff if diff <= 180 else 360 - diff

def parse_viento(texto):
    if not texto or "Sin datos" in texto: return None, None, None
    match = re.search(r'(\d{3})(\d{2,3})(G\d{2,3})?KT', texto)
    if match:
        return int(match.group(1)), int(match.group(2)), (int(match.group(3)[1:]) if match.group(3) else 0)
    return None, None, None

def auditar(icao, reporte, taf):
    alertas = []
    dr, vr, rr = parse_viento(reporte)
    dt, vt, rt = parse_viento(taf)
    if vr is not None and vt is not None:
        if vr >= 10 or vt >= 10:
            d_ang = diff_angular(dr, dt)
            if d_ang >= 60:
                msg = f"CRIT A: Giro {d_ang}°"
                alertas.append(msg)
                st.session_state.historial_alertas.append({
                    "H_Local": datetime.now().strftime("%H:%M:%S"), 
                    "OACI": icao, 
                    "Alerta": "GIRO VTO", 
                    "Valor": f"{d_ang}°"
                })
        
        if abs(vr - vt) >= 10:
            msg = f"CRIT B: Dif Int {abs(vr-vt)}kt"
            alertas.append(msg)
            st.session_state.historial_alertas.append({
                "H_Local": datetime.now().strftime("%H:%M:%S"), 
                "OACI": icao, 
                "Alerta": "INTENSIDAD", 
                "Valor": f"{abs(vr-vt)}kt"
            })
    return alertas

# --- 3. INTERFAZ ---
st.title("🖥️ Vigilancia FIR SAVC")

with st.container():
    if st.session_state.historial_alertas:
        st.subheader("📊 Registro de Desvíos del Turno")
        df_log = pd.DataFrame(st.session_state.historial_alertas)
        st.table(df_log.tail(5))
        
        col_btn1, col_btn2 = st.columns([1, 4])
        with col_btn1:
            csv = df_log.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 DESCARGAR LOG CSV",
                data=csv,
                file_name=f"vigilancia_SAVC_{datetime.now().strftime('%Y%m%d')}.csv",
                mime='text/csv',
            )
        with col_btn2:
            if st.button("🗑️ Limpiar historial"):
                st.session_state.historial_alertas = []
                st.rerun()
    else:
        st.info("🔎 No se han detectado desvíos. Actualización automática cada 30 min.")

st.divider()
st.write(f"Última Sincronización: **{datetime.now().strftime('%H:%M:%S')}**")

# Grilla de Aeródromos
cols = st.columns(2)
headers = {"X-API-Key": API_KEY}

for i, icao in enumerate(AERODROMOS):
    try:
        r_hash = random.randint(1, 999999)
        res_m = requests.get(f"https://api.checkwx.com/metar/{icao}?cache={r_hash}", headers=headers).json()
        metar = res_m.get('data', ['Sin datos'])[0]
        
        res_t = requests.get(f"https://api.checkwx.com/taf/{icao}?cache={r_hash}", headers=headers).json()
        taf = res_t.get('data', ['Sin datos'])[0]
        
        alertas = auditar(icao, metar, taf) if "Sin datos" not in [metar, taf] else []
        icono = obtener_icono_clima(metar)

        with cols[i % 2]:
            estado = "⚠️ ALERTA" if alertas else "✅ OK"
            with st.expander(f"{icono} {icao} - {estado}", expanded=True):
                st.caption("TAF VIGENTE:")
                st.code(taf)
                st.markdown(f"**METAR ACTUAL:** `{metar}`")
                for a in alertas:
                    st.error(a)
    except Exception:
        st.error(f"Falla de conexión en {icao}")

# DERECHOS DE AUTOR
st.markdown(
    f"""
    <div class="copyright">
        © {datetime.now().year} - Sistema de Vigilancia Meteorológica <br>
        Desarrollado por <b>ANIBAL RICARTEZ</b> & <b>Gemini AI</b>. Todos los derechos reservados.
    </div>
    """, 
    unsafe_allow_html=True
)
