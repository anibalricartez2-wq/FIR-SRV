import streamlit as st
import requests
import re
import random
import pandas as pd
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

# --- 1. CONFIGURACIÓN ---
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

st_autorefresh(interval=1800000, key="datarefresh")

API_KEY = "8e7917816866402688f805f637eb54d3"
AERODROMOS = ["SAVV","SAVE","SAVT","SAWC","SAVC","SAWG","SAWE","SAWH"]

# --- 2. FUNCIONES TÉCNICAS REVISADAS ---

def parse_viento(texto):
    if not texto or "Sin datos" in texto: return None, None, None
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
    # Criterio SMN: Base de la capa BKN u OVC
    capas = re.findall(r'\b(BKN|OVC)(\d{3})\b', texto)
    if capas:
        return min(int(c[1]) * 100 for c in capas)
    return 9999

def extraer_fenomenos(texto):
    """Detecta fenómenos e intensidades (+/-) de forma estricta"""
    codigos = ["TS", "VA", "RA", "SN", "DZ", "FG", "BR", "HZ", "FU", "SQ", "PO", "FC", "DS", "SS", "FZRA"]
    palabras = texto.split()
    encontrados = []
    for p in palabras:
        base = p.replace("+", "").replace("-", "")
        if any(base.startswith(c) or base.endswith(c) for c in codigos) and len(base) <= 4:
            encontrados.append(p)
    return set(encontrados)

def obtener_icono_clima(metar_text):
    icon = "✈️"
    prefijo = "⚠️ " if "+" in metar_text else ""
    if "TS" in metar_text: icon = "⛈️"
    elif "VA" in metar_text: icon = "🌋"
    elif "RA" in metar_text or "DZ" in metar_text: icon = "🌧️"
    elif "FG" in metar_text or "BR" in metar_text: icon = "🌫️"
    elif "CAVOK" in metar_text or "SKC" in metar_text: icon = "☀️"
    return f"{prefijo}{icon}"

def auditar(icao, metar, taf):
    enmiendas = []
    
    # --- CRITERIO VIENTO ---
    dr, vr, gr = parse_viento(metar)
    dt, vt, gt = parse_viento(taf)
    if vr is not None and vt is not None:
        if (vr >= 10 or vt >= 10) and abs(dr - dt) >= 60:
            enmiendas.append(f"VIENTO: Giro >= 60°")
        if abs(vr - vt) >= 10:
            enmiendas.append(f"VIENTO: Dif. Vel. media >= 10kt")
        if (vr >= 15 or vt >= 15) and abs(gr - gt) >= 10:
            enmiendas.append(f"VIENTO: Ráfaga (Dif >= 10kt)")

    # --- CRITERIO VISIBILIDAD (CORREGIDO SEGÚN PDF) ---
    v_m = parse_visibilidad(metar)
    v_t = parse_visibilidad(taf)
    # Umbrales exactos: 150, 350, 600, 800, 1500, 3000, 5000
    umbrales_v = [150, 350, 600, 800, 1500, 3000, 5000]
    for u in umbrales_v:
        # Verifica si el cambio "atraviesa" el umbral en cualquier dirección
        if (v_m <= u < v_t) or (v_t <= u < v_m):
            enmiendas.append(f"VIS: Pasó umbral {u}m (Actual: {v_m}m)")
            break

    # --- CRITERIO NUBES (CORREGIDO SEGÚN PDF) ---
    n_m = parse_nubes(metar)
    n_t = parse_nubes(taf)
    # Umbrales: 100, 200, 500, 1000, 1500 ft
    umbrales_n = [100, 200, 500, 1000, 1500]
    for u in umbrales_n:
        if (n_m <= u < n_t) or (n_t <= u < n_m):
            enmiendas.append(f"NUBES: Techo pasó {u}ft (Actual: {n_m}ft)")
            break

    # --- CRITERIO FENÓMENOS ---
    f_m = extraer_fenomenos(metar)
    f_t = extraer_fenomenos(taf)
    cambios = f_m.symmetric_difference(f_t)
    if cambios:
        for c in cambios:
            tipo = "Inicia/Intensifica" if c in f_m else "Finaliza"
            enmiendas.append(f"FENÓMENO: {tipo} ({c})")
            
    return enmiendas

# --- 3. INTERFAZ ---
st.title("🖥️ Vigilancia FIR SAVC (Auditoría SMN)")

if st.session_state.historial_alertas:
    with st.expander("📊 Log de Enmiendas Requeridas"):
        st.table(pd.DataFrame(st.session_state.historial_alertas).tail(10))
        if st.button("Limpiar Registro"):
            st.session_state.historial_alertas = []
            st.rerun()

st.divider()

cols = st.columns(2)
headers = {"X-API-Key": API_KEY}

for i, icao in enumerate(AERODROMOS):
    try:
        r_hash = random.randint(1, 999999)
        m_res = requests.get(f"https://api.checkwx.com/metar/{icao}?cache={r_hash}", headers=headers).json()
        t_res = requests.get(f"https://api.checkwx.com/taf/{icao}?cache={r_hash}", headers=headers).json()
        
        metar, taf = m_res.get('data', ['-'])[0], t_res.get('data', ['-'])[0]
        alertas = auditar(icao, metar, taf) if metar != '-' and taf != '-' else []
        
        with cols[i % 2]:
            header_text = f"{obtener_icono_clima(metar)} {icao}"
            if alertas:
                with st.expander(f"{header_text} ⚠️ ENMIENDA", expanded=True):
                    st.error(f"**METAR:** {metar}")
                    st.caption(f"TAF: {taf}")
                    for a in alertas:
                        st.warning(a)
                        if not any(d['Criterio'] == a and d['OACI'] == icao for d in st.session_state.historial_alertas[-3:]):
                            st.session_state.historial_alertas.append({"Hora": datetime.now().strftime("%H:%M"), "OACI": icao, "Criterio": a})
            else:
                with st.expander(f"{header_text} ✅ OK", expanded=False):
                    st.success(f"**METAR:** {metar}")
                    st.caption(f"TAF: {taf}")
    except:
        st.error(f"Error en {icao}")

st.markdown(f'<div class="copyright">© {datetime.now().year} - Desarrollado por Usuario & Gemini AI. Basado en Criterios SMN Argentina.</div>', unsafe_allow_html=True)
