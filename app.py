import streamlit as st
import requests
import re
import random
import pandas as pd
from datetime import datetime, timezone
from streamlit_autorefresh import st_autorefresh

# --- CONFIGURACIÓN ---
st.set_page_config(page_title="Monitor SAVC Pro", page_icon="✈️", layout="wide")

if 'historial_alertas' not in st.session_state:
    st.session_state.historial_alertas = []

st_autorefresh(interval=1800000, key="datarefresh")

API_KEY = "8e7917816866402688f805f637eb54d3"
AERODROMOS = ["SAVV","SAVE","SAVT","SAWC","SAVC","SAWG","SAWE","SAWH"]

# --- LÓGICA DE PARSEO ---

def obtener_periodo_vigente(taf_text):
    ahora_utc = datetime.now(timezone.utc)
    h_actual, d_actual = ahora_utc.hour, ahora_utc.day
    partes = re.split(r'\b(FM|BECMG|TEMPO|PROB\d{2})\b', taf_text)
    vigente = partes[0]
    for i in range(1, len(partes), 2):
        indicador, contenido = partes[i], partes[i+1]
        match = re.search(r'(\d{2})(\d{2})/(\d{2})(\d{2})', contenido)
        if match:
            d_i, h_i, d_f, h_f = map(int, match.groups())
            if d_i <= d_actual <= d_f:
                if h_i <= h_actual < h_f:
                    vigente = f"{indicador} {contenido}"
    return vigente.strip()

def parse_visibilidad(texto):
    if any(x in texto for x in ["CAVOK", "SKC", "CLR", "NSC"]): return 9999
    match = re.search(r'\b(\d{4})\b', texto)
    return int(match.group(1)) if match else 9999

def parse_viento(texto):
    match = re.search(r'\b(\d{3})(\d{2,3})(G\d{2,3})?KT\b', texto)
    return (int(match.group(1)), int(match.group(2)), int(match.group(3)[1:]) if match.group(3) else 0) if match else (None, None, None)

def parse_nubes(texto):
    capas = re.findall(r'\b(BKN|OVC)(\d{3})\b', texto)
    return min(int(c[1]) * 100 for c in capas) if capas else 9999

def extraer_fenos(texto):
    codigos = ["TS", "VA", "RA", "SN", "DZ", "FG", "BR", "HZ", "FU", "SQ", "FC", "FZRA"]
    palabras = texto.split()
    return set(p.replace("+","").replace("-","") for p in palabras if any(c in p for c in codigos) and len(p) <= 5)

def auditar(icao, metar, taf_completo):
    periodo = obtener_periodo_vigente(taf_completo)
    enmiendas = []
    
    # Datos
    vm = parse_visibilidad(metar)
    vp = parse_visibilidad(periodo)
    
    # --- CORRECCIÓN CRÍTICA DE VISIBILIDAD ---
    # Solo alerta si uno está por encima del umbral y el otro por debajo.
    # Si AMBOS son 3000, no alerta.
    umbrales_v = [150, 350, 600, 800, 1500, 3000, 5000]
    for u in umbrales_v:
        # Lógica: ¿Están en lados distintos del umbral?
        if (vm < u <= vp) or (vp < u <= vm):
            enmiendas.append(f"VIS: Cruzó umbral {u}m (METAR: {vm}m / TAF: {vp}m)")
            break

    # Resto de criterios (Viento, Nubes, Fenos)
    nm, np = parse_nubes(metar), parse_nubes(periodo)
    for u in [100, 200, 500, 1000, 1500]:
        if (nm < u <= np) or (np < u <= nm):
            enmiendas.append(f"NUBES: Techo cruzó {u}ft")
            break

    dr, vr, gr = parse_viento(metar)
    dt, vt, gt = parse_viento(periodo)
    if vr is not None and vt is not None:
        if (vr >= 10 or vt >= 10) and abs(dr - dt) >= 60: enmiendas.append("VIENTO: Giro >= 60°")
        if abs(vr - vt) >= 10: enmiendas.append("VIENTO: Dif. Vel. media >= 10kt")

    fm, fp = extraer_fenos(metar), extraer_fenos(periodo)
    if fm != fp:
        diff = fm.symmetric_difference(fp)
        if diff: enmiendas.append(f"FENÓMENO: Cambio en {list(diff)}")

    return enmiendas, periodo

# --- INTERFAZ ---
st.title("🖥️ Auditoría Meteorológica FIR SAVC")

cols = st.columns(2)
headers = {"X-API-Key": API_KEY}

for i, icao in enumerate(AERODROMOS):
    try:
        r_hash = random.randint(1, 999999)
        m_raw = requests.get(f"https://api.checkwx.com/metar/{icao}?cache={r_hash}", headers=headers).json().get('data',['-'])[0]
        t_raw = requests.get(f"https://api.checkwx.com/taf/{icao}?cache={r_hash}", headers=headers).json().get('data',['-'])[0]
        
        if m_raw != '-' and t_raw != '-':
            alertas, periodo_v = auditar(icao, m_raw, t_raw)
            icon_enm = "🟥 " if alertas else "✅ "
            
            with cols[i % 2]:
                with st.expander(f"{icon_enm}{icao}", expanded=True):
                    st.caption(f"TAF: {t_raw}")
                    st.divider()
                    st.info(f"Vigente: {periodo_v}")
                    st.success(f"METAR: {m_raw}")
                    for a in alertas:
                        st.error(a)
    except:
        st.error(f"Error en {icao}")

st.markdown("© 2026 - Auditoría Estricta SMN")
