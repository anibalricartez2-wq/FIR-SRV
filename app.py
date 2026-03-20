import streamlit as st
import requests
import re
import random
import pandas as pd
from datetime import datetime, timezone
from streamlit_autorefresh import st_autorefresh

# --- 1. CONFIGURACIÓN ---
st.set_page_config(page_title="Vigilancia FIR SAVC v3.5", page_icon="✈️", layout="wide")

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

st_autorefresh(interval=1800000, key="datarefresh")

API_KEY = "8e7917816866402688f805f637eb54d3"
AERODROMOS = ["SAVV","SAVE","SAVT","SAWC","SAVC","SAWG","SAWE","SAWH"]

# --- 2. MOTOR DE PARSEO BLINDADO (Lógica para todos los OACI) ---

def limpiar_metar_taf(texto):
    """Elimina ruidos de fecha/hora para no confundirlos con visibilidad/techos"""
    # Borra rangos tipo 2016/2022
    t = re.sub(r'\d{4}/\d{4}', '', texto)
    # Borra grupos Z tipo 201600Z
    t = re.sub(r'\d{6}Z', '', t)
    # Borra indicadores FM tipo FM201600
    t = re.sub(r'FM\d{6}', '', t)
    return t

def parse_vis_pro(texto):
    """Extrae visibilidad real ignorando números de tiempo"""
    if any(x in texto for x in ["CAVOK", "SKC", "NSC"]): return 9999
    t_limpio = limpiar_metar_taf(texto)
    # Busca el primer número de 4 dígitos aislado
    match = re.search(r'\b(\d{4})\b', t_limpio)
    return int(match.group(1)) if match else 9999

def obtener_periodo_dominante(taf_text):
    """Lógica cronológica para determinar qué parte del TAF manda ahora"""
    ahora = datetime.now(timezone.utc)
    ref = ahora.day * 10000 + ahora.hour * 100 + ahora.minute
    
    # Limpieza inicial del TAF (quita cabecera)
    taf_clean = re.sub(r'^(TAF\s+)?([A-Z]{4})\s+\d{6}Z\s+', '', taf_text)
    tags = [m for m in re.finditer(r'\b(FM|BECMG|TEMPO|PROB\d{2})\b', taf_clean)]
    
    if not tags: return taf_clean
    
    bloques = [{"tipo": "BASE", "contenido": taf_clean[:tags[0].start()].strip()}]
    for i in range(len(tags)):
        start = tags[i].start()
        end = tags[i+1].start() if i+1 < len(tags) else len(taf_clean)
        bloques.append({"tipo": tags[i].group(), "contenido": taf_clean[start:end].strip()})
    
    dominante = bloques[0]["contenido"]
    for b in bloques[1:]:
        match_r = re.search(r'(\d{2})(\d{2})/(\d{2})(\d{2})', b["contenido"])
        match_f = re.search(r'FM(\d{2})(\d{2})(\d{2})', b["contenido"])
        valido = False
        if match_r:
            di, hi, df, hf = map(int, match_r.groups())
            if (di * 10000 + hi * 100) <= ref < (df * 10000 + hf * 100): valido = True
        elif match_f:
            di, hi, mi = map(int, match_f.groups())
            if ref >= (di * 10000 + hi * 100 + mi): valido = True
            
        if valido:
            # Prioridad de cambio: FM y BECMG son base, TEMPO es condicional
            dominante = b["contenido"]
    return dominante

def determinar_escalon_vis(valor):
    umbrales = [150, 350, 600, 800, 1500, 3000, 5000]
    for i, u in enumerate(umbrales):
        if valor < u: return i
    return 8 # +5000m / CAVOK

# --- 3. AUDITORÍA FINAL ---

def auditar_v35(icao, metar, taf_completo):
    periodo = obtener_periodo_dominante(taf_completo)
    enmiendas = []
    
    vm = parse_vis_pro(metar)
    vp = parse_vis_pro(periodo)
    
    # Solo alerta si los escalones operativos son distintos
    if determinar_escalon_vis(vm) != determinar_escalon_vis(vp):
        # Filtro de seguridad: No alertar si el METAR es CAVOK y el TAF decía +5000m
        if not (vm >= 9999 and vp >= 5000):
            enmiendas.append(f"VIS: Cambio de escalón (M: {vm}m / T: {vp}m)")

    # Techos
    def get_c(t):
        capas = re.findall(r'\b(BKN|OVC)(\d{3})\b', t)
        return min(int(c[1]) * 100 for c in capas) if capas else 9999
    
    nm, np = get_c(metar), get_c(periodo)
    umbrales_n = [100, 200, 500, 1000, 1500]
    for u in umbrales_n:
        if (nm < u <= np) or (np < u <= nm):
            enmiendas.append(f"NUBES: Techo cruzó {u}ft")
            break

    return enmiendas, periodo

# --- 4. INTERFAZ ---
st.title("🖥️ Auditoría de Vigilancia SAVC - v3.5 (Blindada)")

cols = st.columns(2)
headers = {"X-API-Key": API_KEY}

for i, icao in enumerate(AERODROMOS):
    try:
        r_hash = random.randint(1, 9999)
        m_r = requests.get(f"https://api.checkwx.com/metar/{icao}?cache={r_hash}", headers=headers).json().get('data',['-'])[0]
        t_r = requests.get(f"https://api.checkwx.com/taf/{icao}?cache={r_hash}", headers=headers).json().get('data',['-'])[0]
        
        if m_r != '-' and t_r != '-':
            alertas, periodo_v = auditar_v35(icao, m_r, t_r)
            icon = "🟥" if alertas else "✅"
            with cols[i % 2]:
                with st.expander(f"{icon} {icao}", expanded=True):
                    st.caption(f"Periodo TAF Analizado: {periodo_v}")
                    st.success(f"METAR ACTUAL: {m_r}")
                    for a in alertas: st.error(a)
    except:
        st.error(f"Error conexión {icao}")

st.markdown(f'<div class="copyright">© {datetime.now().year} - Vigilancia Aeronáutica SAVC. Lógica de escalones SMN corregida.</div>', unsafe_allow_html=True)
