import streamlit as st
import requests
import re
import pandas as pd
from datetime import datetime, timezone
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

# --- 2. LOGICA DE TIEMPO Y PARSEO ---

def get_viento_vigente_taf(taf_raw):
    """Extrae el grupo de viento del TAF que corresponde a la hora actual UTC"""
    ahora_utc = datetime.now(timezone.utc)
    hora_actual_int = ahora_utc.hour
    dia_actual_int = ahora_utc.day

    # Dividir TAF por grupos de tiempo (FM, BECMG, TEMPO)
    partes = re.split(r'\s(?=FM|BECMG|TEMPO)', taf_raw)
    
    # El primer grupo es siempre el viento base
    viento_elegido = partes[0]
    
    # Buscamos si hay un grupo FM (From) que ya haya empezado
    for p in partes:
        if "FM" in p:
            match_time = re.search(r'FM(\d{2})(\d{2})(\d{2})', p)
            if match_time:
                dia_fm, hora_fm, min_fm = map(int, match_time.groups())
                # Si ya pasamos esa hora, este es nuestro nuevo viento base
                if dia_actual_int >= dia_fm and hora_actual_int >= hora_fm:
                    viento_elegido = p

    return viento_elegido

def get_weather_icon(metar):
    if "TS" in metar: return "⛈️"
    if "RA" in metar or "DZ" in metar: return "🌧️"
    if "FG" in metar or "BR" in metar: return "🌫️"
    if "SN" in metar: return "❄️"
    if "VCTS" in metar: return "🌩️"
    if "CAVOK" in metar or "SKC" in metar: return "☀️"
    return "☁️"

def diff_angular(d1, d2):
    diff = abs(d1 - d2)
    return diff if diff <= 180 else 360 - diff

def parse_viento(texto):
    if not texto or "Sin datos" in texto: return None, None, None
    match = re.search(r'(\d{3})(\d{2,3})(G\d{2,3})?KT', texto)
    if match:
        d = int(match.group(1))
        v = int(match.group(2))
        g = int(match.group(3)[1:]) if match.group(3) else 0
        return d, v, g
    return None, None, None

# --- 3. INTERFAZ ---
st.title("✈️ Vigilancia Operativa FIR SAVC")
st.write(f"Hora Actual (UTC): **{datetime.now(timezone.utc).strftime('%H:%M')}Z**")

# Panel de Log
with st.expander("📝 REGISTRO DE ENMIENDAS SUGERIDAS", expanded=False):
    if st.session_state.historial_alertas:
        st.table(pd.DataFrame(st.session_state.historial_alertas).iloc[::-1])
        if st.button("Limpiar Log"):
            st.session_state.historial_alertas = []
            st.rerun()
    else:
        st.info("No hay alertas de enmienda activas.")

st.divider()

# --- 4. PROCESAMIENTO ---
headers = {"X-API-Key": API_KEY}
cols = st.columns(2) # Volvemos a 2 para que el texto sea legible

for i, icao in enumerate(AERODROMOS):
    with cols[i % 2]:
        try:
            res_m = requests.get(f"https://api.checkwx.com/metar/{icao}", headers=headers).json()
            res_t = requests.get(f"https://api.checkwx.com/taf/{icao}", headers=headers).json()
            
            metar = res_m.get('data', ['Sin datos'])[0]
            taf_full = res_t.get('data', ['Sin datos'])[0]
            
            # Analizar periodo del TAF
            taf_vigente = get_viento_vigente_taf(taf_full)
            
            # Datos de viento
            dr, vr, rr = parse_viento(metar)
            dt, vt, rt = parse_viento(taf_vigente)
            
            alertas = []
            if vr is not None and vt is not None:
                # Criterio A: Giro de 60° o más con vto > 10kt
                if vr >= 10 or vt >= 10:
                    d_ang = diff_angular(dr, dt)
                    if d_ang >= 60:
                        alertas.append(f"🔴 ENMIENDA: Giro {d_ang}° respecto al TAF")
                
                # Criterio B: Intensidad dif > 10kt
                if abs(vr - vt) >= 10:
                    alertas.append(f"🟠 ENMIENDA: Dif. Velocidad {abs(vr-vt)}kt")

            # UI
            icon = get_weather_icon(metar)
            with st.container(border=True):
                st.subheader(f"{icon} {icao}")
                
                col_m, col_t = st.columns(2)
                col_m.markdown(f"**METAR ACTUAL**\n`{metar}`")
                col_t.markdown(f"**TAF VIGENTE**\n`{taf_vigente}`")
                
                if alertas:
                    for a in alertas:
                        st.warning(a)
                        # Registrar en historial si es nuevo
                        id_h = f"{icao}_{a[:15]}"
                        if st.session_state.last_alert_id.get(id_h) != a:
                            st.session_state.historial_alertas.append({
                                "Hora": datetime.now().strftime("%H:%M"),
                                "OACI": icao,
                                "Motivo": a
                            })
                            st.session_state.last_alert_id[id_h] = a
                else:
                    st.success("✅ TAF Representativo")
                
                with st.expander("Ver TAF Completo"):
                    st.text(taf_full)

        except Exception as e:
            st.error(f"Error en {icao}")

st.caption("Nota: El análisis de TAF prioriza el grupo base o cambios tipo 'FM' según la hora UTC actual.")
