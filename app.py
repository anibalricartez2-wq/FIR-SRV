import streamlit as st
import requests
import re
import random
import pandas as pd
from datetime import datetime, timezone
from streamlit_autorefresh import st_autorefresh

# --- 1. CONFIGURACIÓN DE PÁGINA ---
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

# Auto-refresco cada 30 minutos
st_autorefresh(interval=1800000, key="datarefresh")

API_KEY = "8e7917816866402688f805f637eb54d3"
AERODROMOS = ["SAVV","SAVE","SAVT","SAWC","SAVC","SAWG","SAWE","SAWH"]

# --- 2. MOTOR DE PROCESAMIENTO TAF (Lógica Secuencial Avanzada) ---

def extraer_bloques_taf(taf_text):
    """Divide el TAF en bloques cronológicos: BASE, FM, BECMG, TEMPO"""
    taf_clean = re.sub(r'^(TAF\s+)?([A-Z]{4})\s+\d{6}Z\s+', '', taf_text)
    tags = [m for m in re.finditer(r'\b(FM|BECMG|TEMPO|PROB\d{2})\b', taf_clean)]
    
    if not tags:
        return [{"tipo": "BASE", "contenido": taf_clean}]
    
    bloques = [{"tipo": "BASE", "contenido": taf_clean[:tags[0].start()].strip()}]
    for i in range(len(tags)):
        start = tags[i].start()
        end = tags[i+1].start() if i+1 < len(tags) else len(taf_clean)
        bloques.append({"tipo": tags[i].group(), "contenido": taf_clean[start:end].strip()})
    return bloques

def obtener_periodo_dominante(taf_text):
    """Determina qué sección del TAF es válida ahora mismo (UTC)"""
    ahora = datetime.now(timezone.utc)
    ref = ahora.day * 10000 + ahora.hour * 100 + ahora.minute
    bloques = extraer_bloques_taf(taf_text)
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
            # FM y BECMG establecen una nueva condición base
            if any(x in b["tipo"] for x in ["FM", "BECMG"]): dominante = b["contenido"]
            # TEMPO se superpone (lo tomamos como vigente para auditar contra el METAR)
            elif "TEMPO" in b["tipo"]: dominante = b["contenido"]
            
    return dominante

# --- 3. AUDITORÍA DE CRITERIOS SMN ---

def auditar_smn(icao, metar, taf_completo):
    periodo = obtener_periodo_dominante(taf_completo)
    enmiendas = []
    
    # Visibilidad
    def get_v(t):
        if "CAVOK" in t: return 9999
        m = re.search(r'\b(\d{4})\b', t)
        return int(m.group(1)) if m else 9999
    
    vm, vp = get_v(metar), get_v(periodo)
    for u in [150, 350, 600, 800, 1500, 3000, 5000]:
        if (vm < u <= vp) or (vp < u <= vm):
            enmiendas.append(f"VIS: Cruzó umbral {u}m")
            break

    # Techos (BKN/OVC)
    capas_m = re.findall(r'\b(BKN|OVC)(\d{3})\b', metar)
    capas_p = re.findall(r'\b(BKN|OVC)(\d{3})\b', periodo)
    nm = min(int(c[1]) * 100 for c in capas_m) if capas_m else 9999
    np = min(int(c[1]) * 100 for c in capas_p) if capas_p else 9999
    for u in [100, 200, 500, 1000, 1500]:
        if (nm < u <= np) or (np < u <= nm):
            enmiendas.append(f"NUBES: Techo cruzó {u}ft")
            break

    # Viento
    m_v = re.search(r'\b(\d{3})(\d{2,3})(G\d{2,3})?KT\b', metar)
    p_v = re.search(r'\b(\d{3})(\d{2,3})(G\d{2,3})?KT\b', periodo)
    if m_v and p_v:
        dr, vr = int(m_v.group(1)), int(m_v.group(2))
        dt, vt = int(p_v.group(1)), int(p_v.group(2))
        if (vr >= 10 or vt >= 10) and abs(dr - dt) >= 60: enmiendas.append("VIENTO: Giro >= 60°")
        if abs(vr - vt) >= 10: enmiendas.append("VIENTO: Dif. Vel. >= 10kt")

    return enmiendas, periodo

# --- 4. INTERFAZ ---
st.title("✈️ Auditor de Enmiendas FIR SAVC")

cols = st.columns(2)
headers = {"X-API-Key": API_KEY}

for i, icao in enumerate(AERODROMOS):
    try:
        r_hash = random.randint(1, 999999)
        m_raw = requests.get(f"https://api.checkwx.com/metar/{icao}?cache={r_hash}", headers=headers).json().get('data',['-'])[0]
        t_raw = requests.get(f"https://api.checkwx.com/taf/{icao}?cache={r_hash}", headers=headers).json().get('data',['-'])[0]
        
        if m_raw != '-' and t_raw != '-':
            alertas, periodo_v = auditar_smn(icao, m_raw, t_raw)
            icon = "🟥" if alertas else "✅"
            
            with cols[i % 2]:
                with st.expander(f"{icon} {icao}", expanded=True):
                    st.caption(f"TAF: {t_raw}")
                    st.divider()
                    st.markdown(f"**VIGENTE:** `{periodo_v}`")
                    st.success(f"**METAR:** `{m_raw}`")
                    for a in alertas:
                        st.error(a)
                        if not any(d['Criterio'] == a and d['OACI'] == icao for d in st.session_state.historial_alertas[-5:]):
                            st.session_state.historial_alertas.append({"Hora": datetime.now().strftime("%H:%M"), "OACI": icao, "Criterio": a})
    except:
        st.error(f"Error de conexión en {icao}")

if st.session_state.historial_alertas:
    st.divider()
    with st.expander("📊 Log de Novedades"):
        st.table
