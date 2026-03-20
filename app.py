import streamlit as st
import requests
import re
import random
import pandas as pd
from datetime import datetime, timezone
from streamlit_autorefresh import st_autorefresh

# --- 1. CONFIGURACIÓN ---
st.set_page_config(page_title="Vigilancia SAVC - Tiempo Real", page_icon="✈️", layout="wide")

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

st_autorefresh(interval=1800000, key="datarefresh") # 30 min

API_KEY = "8e7917816866402688f805f637eb54d3"
AERODROMOS = ["SAVV","SAVE","SAVT","SAWC","SAVC","SAWG","SAWE","SAWH"]

# --- 2. MOTOR DE LÓGICA TEMPORAL ---

def obtener_pronostico_vigente(taf_text):
    """
    Divide el TAF y devuelve la parte que corresponde a la hora actual UTC.
    """
    ahora_utc = datetime.now(timezone.utc)
    dia_actual = ahora_utc.day
    hora_actual = ahora_utc.hour
    
    # Separamos por grupos de cambio
    partes = re.split(r'\b(FM|BECMG|TEMPO|PROB\d{2})\b', taf_text)
    base = partes[0]
    
    vigente = base
    
    # Recorremos los grupos para ver cuál aplica por horario
    for i in range(1, len(partes), 2):
        indicador = partes[i]
        contenido = partes[i+1]
        
        # Buscamos el grupo horario (ej: 2018/2021 o 201500)
        match_periodo = re.search(r'(\d{2})(\d{2})/(\d{2})(\d{2})', contenido)
        if match_periodo:
            dia_ini, hora_ini, dia_fin, hora_fin = map(int, match_periodo.groups())
            
            # Lógica simplificada: si estamos dentro del rango de días y horas
            if dia_ini <= dia_actual <= dia_fin:
                if hora_ini <= hora_actual < hora_fin:
                    vigente = contenido
                    # Si es TEMPO o PROB, a veces se prefiere mantener la base o sumar criterios
                    # Aquí tomamos el grupo como el nuevo estándar a comparar
    
    return vigente

def parse_viento(texto):
    match = re.search(r'\b(\d{3})(\d{2,3})(G\d{2,3})?KT\b', texto)
    if match:
        d, v = int(match.group(1)), int(match.group(2))
        g = int(match.group(3)[1:]) if match.group(3) else 0
        return d, v, g
    return None, None, None

def parse_visibilidad(texto):
    if "CAVOK" in texto: return 9999
    match = re.search(r'\b(\d{4})\b', texto)
    return int(match.group(1)) if match else 9999

def parse_nubes(texto):
    capas = re.findall(r'\b(BKN|OVC)(\d{3})\b', texto)
    if capas:
        return min(int(c[1]) * 100 for c in capas)
    return 9999

def extraer_fenomenos(texto):
    codigos = ["TS", "VA", "RA", "SN", "DZ", "FG", "BR", "HZ", "FU", "SQ", "FZRA"]
    palabras = texto.split()
    encontrados = []
    for p in palabras:
        base = p.replace("+", "").replace("-", "")
        if any(base.startswith(c) for c in codigos) and len(base) <= 4:
            encontrados.append(p)
    return set(encontrados)

def auditar(icao, metar, taf_completo):
    # 1. Obtener qué parte del TAF aplica AHORA
    taf_vigente = obtener_pronostico_vigente(taf_completo)
    enmiendas = []
    
    # 2. Comparación de Viento
    dr, vr, gr = parse_viento(metar)
    dt, vt, gt = parse_viento(taf_vigente)
    if vr is not None and vt is not None:
        if (vr >= 10 or vt >= 10) and abs(dr - dt) >= 60:
            enmiendas.append(f"VIENTO: Giro >= 60° (Previsto: {dt}°, Real: {dr}°)")
        if abs(vr - vt) >= 10:
            enmiendas.append(f"VIENTO: Dif. Vel. >= 10kt (Previsto: {vt}kt, Real: {vr}kt)")
    
    # 3. Visibilidad (Umbrales SMN)
    v_m, v_t = parse_visibilidad(metar), parse_visibilidad(taf_vigente)
    umbrales_v = [150, 350, 600, 800, 1500, 3000, 5000]
    for u in umbrales_v:
        if (v_m <= u < v_t) or (v_t <= u < v_m):
            enmiendas.append(f"VIS: Cruzó umbral {u}m (Actual: {v_m}m)")
            break

    # 4. Nubes
    n_m, n_t = parse_nubes(metar), parse_nubes(taf_vigente)
    umbrales_n = [100, 200, 500, 1000, 1500]
    for u in umbrales_n:
        if (n_m <= u < n_t) or (n_t <= u < n_m):
            enmiendas.append(f"NUBES: Techo cruzó {u}ft (Actual: {n_m}ft)")
            break

    # 5. Fenómenos e Intensidad
    f_m, f_t = extraer_fenomenos(metar), extraer_fenomenos(taf_vigente)
    cambios = f_m.symmetric_difference(f_t)
    if cambios:
        for c in cambios:
            tipo = "Inicia/Intensifica" if c in f_m else "Finaliza"
            enmiendas.append(f"FENÓMENO: {tipo} ({c})")
            
    return enmiendas, taf_vigente

# --- 3. INTERFAZ ---
st.title("🖥️ Vigilancia FIR SAVC - Auditoría por Periodo TAF")

cols = st.columns(2)
headers = {"X-API-Key": API_KEY}

for i, icao in enumerate(AERODROMOS):
    try:
        r_hash = random.randint(1, 999999)
        m_res = requests.get(f"https://api.checkwx.com/metar/{icao}?cache={r_hash}", headers=headers).json()
        t_res = requests.get(f"https://api.checkwx.com/taf/{icao}?cache={r_hash}", headers=headers).json()
        
        metar = m_res.get('data', ['-'])[0]
        taf_c = t_res.get('data', ['-'])[0]
        
        if metar != '-' and taf_c != '-':
            alertas, periodo_aplicado = auditar(icao, metar, taf_c)
            
            with cols[i % 2]:
                estado = "⚠️ ENMIENDA" if alertas else "✅ OK"
                with st.expander(f"{icao} - {estado}", expanded=True):
                    st.success(f"**METAR:** `{metar}`")
                    st.info(f"**PRONÓSTICO VIGENTE (Periodo actual):** `{periodo_aplicado}`")
                    if alertas:
                        for a in alertas:
                            st.error(a)
        else:
            st.warning(f"Sin datos suficientes para {icao}")
    except:
        st.error(f"Error en {icao}")

st.markdown(f'<div class="copyright">© {datetime.now().year} - Desarrollado por Usuario & Gemini AI. Lógica de comparación temporal activa.</div>', unsafe_allow_html=True)
