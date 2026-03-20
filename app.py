import streamlit as st
import requests
import re
import pandas as pd
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

# --- 1. CONFIGURACIÓN ---
st.set_page_config(page_title="Vigilancia FIR SAVC", page_icon="✈️", layout="wide")

if 'historial_alertas' not in st.session_state:
    st.session_state.historial_alertas = []
if 'last_alert_id' not in st.session_state:
    st.session_state.last_alert_id = {}

st_autorefresh(interval=120000, key="datarefresh")

API_KEY = "8e7917816866402688f805f637eb54d3"
AERODROMOS = ["SAVV","SAVE","SAVT","SAWC","SAVC","SAWG","SAWE","SAWH"]

# --- 2. FUNCIONES LÓGICAS ---

def get_weather_icon(metar):
    """Asigna un icono según fenómenos significativos en el METAR"""
    if "TS" in metar: return "⛈️" # Tormenta
    if "RA" in metar or "DZ" in metar: return "🌧️" # Lluvia / Llovizna
    if "SN" in metar or "SG" in metar: return "❄️" # Nieve
    if "FG" in metar or "BR" in metar: return "🌫️" # Niebla / Neblina
    if "HZ" in metar or "FU" in metar: return "🌫️" # Bruma / Humo
    if "VCTS" in metar: return "🌩️" # Tormenta en las cercanías
    if "SKC" in metar or "CLR" in metar or "CAVOK" in metar: return "☀️" # Despejado
    if "BKN" in metar or "OVC" in metar: return "☁️" # Nublado
    if "SCT" in metar or "FEW" in metar: return "🌤️" # Parcialmente nublado
    return "🔹" # Por defecto

def diff_angular(d1, d2):
    diff = abs(d1 - d2)
    return diff if diff <= 180 else 360 - diff

def parse_viento(texto):
    if not texto or "Sin datos" in texto: return None, None, None
    match = re.search(r'(\d{3})(\d{2,3})(G\d{2,3})?KT', texto)
    if match:
        return int(match.group(1)), int(match.group(2)), (int(match.group(3)[1:]) if match.group(3) else 0)
    return None, None, None

def registrar_alerta(icao, tipo, valor):
    id_alerta = f"{icao}_{tipo}"
    ahora = datetime.now().strftime("%H:%M")
    if st.session_state.last_alert_id.get(id_alerta) != valor:
        st.session_state.historial_alertas.append({
            "H_Local": ahora, "OACI": icao, "Alerta": tipo, "Detalle": valor
        })
        st.session_state.last_alert_id[id_alerta] = valor

# --- 3. INTERFAZ ---
st.title("🖥️ Vigilancia FIR SAVC")

with st.expander("📊 LOG DE DESVÍOS (TURNO ACTUAL)", expanded=False):
    if st.session_state.historial_alertas:
        df_log = pd.DataFrame(st.session_state.historial_alertas)
        st.table(df_log.iloc[::-1]) # Lo más nuevo arriba
        if st.button("🗑️ Limpiar Historial"):
            st.session_state.historial_alertas = []
            st.session_state.last_alert_id = {}
            st.rerun()
    else:
        st.info("No hay desvíos registrados.")

st.divider()

# --- 4. GRILLA DE AERÓDROMOS ---
headers = {"X-API-Key": API_KEY}
cols = st.columns(4)

for i, icao in enumerate(AERODROMOS):
    with cols[i % 4]:
        try:
            res_m = requests.get(f"https://api.checkwx.com/metar/{icao}", headers=headers).json()
            res_t = requests.get(f"https://api.checkwx.com/taf/{icao}", headers=headers).json()
            
            metar = res_m.get('data', ['Sin datos'])[0]
            taf = res_t.get('data', ['Sin datos'])[0]
            
            # Obtener icono y procesar alertas
            icon = get_weather_icon(metar)
            alertas_locales = []
            
            dr, vr, rr = parse_viento(metar)
            dt, vt, rt = parse_viento(taf)
            
            if vr is not None and vt is not None:
                if (vr >= 10 or vt >= 10) and diff_angular(dr, dt) >= 60:
                    alertas_locales.append(f"GIRO: {diff_angular(dr, dt)}°")
                    registrar_alerta(icao, "GIRO", f"{diff_angular(dr, dt)}°")
                if abs(vr - vt) >= 10:
                    alertas_locales.append(f"INTENSIDAD: {abs(vr-vt)}kt")
                    registrar_alerta(icao, "INTENSIDAD", f"{abs(vr-vt)}kt")

            # UI de la Tarjeta
            color = "red" if alertas_locales else "blue"
            # Título con Icono de clima
            st.markdown(f"### {icon} :{color}[{icao}]")
            
            if alertas_locales:
                for a in alertas_locales:
                    st.error(a)
            else:
                st.success("✅ Estabilidad")
                
            st.caption(f"**METAR:** `{metar}`")
            with st.expander("Ver TAF"):
                st.code(taf, language="markdown")
                
        except Exception:
            st.error(f"Error {icao}")

st.divider()
st.write(f"Sincronizado: **{datetime.now().strftime('%H:%M:%S')}**")
