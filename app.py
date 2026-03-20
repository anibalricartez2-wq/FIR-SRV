import streamlit as st
import requests
import re
import random
import pandas as pd
from datetime import datetime, timezone
from streamlit_autorefresh import st_autorefresh

# --- 1. CONFIGURACIÓN ---
st.set_page_config(page_title="Auditor FIR SAVC v3.2", page_icon="✈️", layout="wide")

if 'historial_alertas' not in st.session_state:
    st.session_state.historial_alertas = []

st_autorefresh(interval=1800000, key="datarefresh")

API_KEY = "8e7917816866402688f805f637eb54d3"
AERODROMOS = ["SAVV","SAVE","SAVT","SAWC","SAVC","SAWG","SAWE","SAWH"]

# --- 2. MOTOR DE LOGICA (TIEMPOS) ---

def obtener_periodo_dominante(taf_text):
    ahora = datetime.now(timezone.utc)
    ref = ahora.day * 10000 + ahora.hour * 100 + ahora.minute
    
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
            if any(x in b["tipo"] for x in ["FM", "BECMG", "TEMPO"]): dominante = b["contenido"]
    return dominante

# --- 3. AUDITORÍA DE ESCALONES (EVITA FALSOS POSITIVOS) ---

def determinar_escalon_vis(valor):
    """Asigna un número de escalón basado en los umbrales del SMN"""
    umbrales = [150, 350, 600, 800, 1500, 3000, 5000]
    for i, u in enumerate(umbrales):
        if valor < u:
            return i # Retorna el índice del umbral que NO alcanzó
    return len(umbrales) # Está por encima de 5000m

def determinar_escalon_techo(valor):
    """Asigna un número de escalón basado en los umbrales de techo"""
    umbrales = [100, 200, 500, 1000, 1500]
    for i, u in enumerate(umbrales):
        if valor < u:
            return i
    return len(umbrales)

def auditar_smn_v32(icao, metar, taf_completo):
    periodo = obtener_periodo_dominante(taf_completo)
    enmiendas = []
    
    # --- VISIBILIDAD ---
    def get_v(t):
        if "CAVOK" in t: return 9999
        m = re.search(r'\b(\d{4})\b', t)
        return int(m.group(1)) if m else 9999
    
    vm, vp = get_v(metar), get_v(periodo)
    if determinar_escalon_vis(vm) != determinar_escalon_vis(vp):
        enmiendas.append(f"VIS: Cambio de escalón operativo (M: {vm}m / T: {vp}m)")

    # --- TECHOS ---
    def get_c(t):
        capas = re.findall(r'\b(BKN|OVC)(\d{3})\b', t)
        return min(int(c[1]) * 100 for c in capas) if capas else 9999
    
    nm, np = get_c(metar), get_c(periodo)
    if determinar_escalon_techo(nm) != determinar_escalon_techo(np):
        enmiendas.append(f"NUBES: Cambio de escalón de techo (M: {nm}ft / T: {np}ft)")

    # --- VIENTO ---
    def get_w(t):
        m = re.search(r'\b(\d{3})(\d{2,3})(G\d{2,3})?KT\b', t)
        return (int(m.group(1)), int(m.group(2))) if m else (None, None)
    
    dm, vm_kt = get_w(metar)
    dp, vp_kt = get_w(periodo)
    if vm_kt is not None and vp_kt is not None:
        if (vm_kt >= 10 or vp_kt >= 10) and abs(dm - dp) >= 60: enmiendas.append("VIENTO: Giro >= 60°")
        if abs(vm_kt - vp_kt) >= 10: enmiendas.append("VIENTO: Dif. Vel. >= 10kt")

    return enmiendas, periodo

# --- 4. INTERFAZ ---
st.title("🖥️ Auditor de Vigilancia FIR SAVC")

cols = st.columns(2)
headers = {"X-API-Key": API_KEY}

for i, icao in enumerate(AERODROMOS):
    try:
        r_hash = random.randint(1, 9999)
        m_r = requests.get(f"https://api.checkwx.com/metar/{icao}?cache={r_hash}", headers=headers).json().get('data',['-'])[0]
        t_r = requests.get(f"https://api.checkwx.com/taf/{icao}?cache={r_hash}", headers=headers).json().get('data',['-'])[0]
        
        if m_r != '-' and t_r != '-':
            alertas, periodo_v = auditar_smn_v32(icao, m_r, t_r)
            icon = "🟥" if alertas else "✅"
            with cols[i % 2]:
                with st.expander(f"{icon} {icao}", expanded=True):
                    st.caption(f"Vigente: {periodo_v}")
                    st.success(f"METAR: {m_r}")
                    for a in alertas: st.error(a)
    except:
        st.error(f"Error {icao}")

st.markdown("---")
st.caption("© 2026 - Auditoría por escalones operativos (SMN)")
