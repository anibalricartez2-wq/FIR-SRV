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

# ESTILO CSS PARA INTERFAZ LIMPIA
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

# REFRESH CADA 30 MINUTOS (1.800.000 ms)
st_autorefresh(interval=1800000, key="datarefresh")

API_KEY = "8e7917816866402688f805f637eb54d3"
AERODROMOS = ["SAVV","SAVE","SAVT","SAWC","SAVC","SAWG","SAWE","SAWH"]

# --- 2. FUNCIONES TÉCNICAS (PARSERS Y AUDITORÍA) ---

def parse_viento(texto):
    if not texto or "Sin datos" in texto: return None, None, None
    match = re.search(r'(\d{3})(\d{2,3})(G\d{2,3})?KT', texto)
    if match:
        d = int(match.group(1))
        v = int(match.group(2))
        g = int(match.group(3)[1:]) if match.group(3) else 0
        return d, v, g
    return None, None, None

def parse_visibilidad(texto):
    match = re.search(r'\s(\d{4})\s', texto)
    return int(match.group(1)) if match else 9999

def parse_nubes(texto):
    # Detecta la capa más baja de BKN u OVC según criterios SMN
    capas = re.findall(r'(BKN|OVC)(\d{3})', texto)
    if capas:
        return min(int(c[1]) * 100 for c in capas)
    return 9999

def obtener_icono_clima(metar_text):
    """Mapeo dinámico con detección de intensidad (+/-)"""
    icon = "✈️"
    prefijo = "⚠️ " if "+" in metar_text else ""
    
    if "TS" in metar_text: icon = "⛈️"
    elif "VA" in metar_text: icon = "🌋"
    elif "SN" in metar_text: icon = "❄️"
    elif "RA" in metar_text or "DZ" in metar_text: icon = "🌧️"
    elif "FG" in metar_text or "BR" in metar_text: icon = "🌫️"
    elif "SKC" in metar_text or "CLR" in metar_text or "NSC" in metar_text: icon = "☀️"
    elif "BKN" in metar_text or "OVC" in metar_text: icon = "☁️"
    
    return f"{prefijo}{icon}"

def auditar(icao, metar, taf):
    enmiendas = []
    # Extracción de datos
    dr, vr, gr = parse_viento(metar)
    vis_r = parse_visibilidad(metar)
    techo_r = parse_nubes(metar)
    dt, vt, gt = parse_viento(taf)
    vis_t = parse_visibilidad(taf)
    techo_t = parse_nubes(taf)

    # 1. CRITERIO VIENTO (Giro >= 60° o Vel >= 10kt)
    if vr is not None and vt is not None:
        if (vr >= 10 or vt >= 10) and abs(dr - dt) >= 60:
            enmiendas.append(f"VIENTO: Giro >= 60° ({dr}° vs {dt}°)")
        if abs(vr - vt) >= 10:
            enmiendas.append(f"VIENTO: Dif. Vel. >= 10kt")
        if (gr > 0) and (vr >= 15 or vt >= 15) and (gr - vr >= 10):
            enmiendas.append(f"VIENTO: Ráfaga no prevista (+{gr-vr}kt)")

    # 2. CRITERIO VISIBILIDAD (Cruces de umbrales SMN)
    umbrales_vis = [150, 350, 600, 800, 1500, 3000, 5000]
    for u in umbrales_vis:
        if (vis_r <= u < vis_t) or (vis_t <= u < vis_r):
            enmiendas.append(f"VIS: Cruzó umbral de {u}m")
            break

    # 3. CRITERIO TECHOS (BKN/OVC < 1500ft)
    umbrales_nubes = [100, 200, 500, 1000, 1500]
    for u in umbrales_nubes:
        if (techo_r <= u < techo_t) or (techo_t <= u < techo_r):
            enmiendas.append(f"NUBES: Techo cruzó {u}ft")
            break

    # 4. FENÓMENOS E INTENSIDADES (+ / -)
    fenomenos_criticos = ["TS", "VA", "SN", "FG", "FZRA", "SQ", "DZ", "RA"]
    for f in fenomenos_criticos:
        # Detectar aparición/desaparición o cambio de intensidad
        en_metar = [s for s in metar.split() if f in s]
        en_taf = [s for s in taf.split() if f in s]
        
        if en_metar != en_taf:
            desc = en_metar[0] if en_metar else f"Fin de {f}"
            enmiendas.append(f"FENÓMENO: Cambio a {desc}")
            
    return enmiendas

# --- 3. INTERFAZ DE USUARIO ---
st.title("🖥️ Vigilancia FIR SAVC (Criterios SMN)")

with st.sidebar:
    st.header("Configuración")
    st.info("Actualización automática: 30 min")
    if st.button("🔄 Forzar Sincronización"):
        st.rerun()

if st.session_state.historial_alertas:
    with st.expander("📊 Historial de Enmiendas Requeridas (Turno Actual)"):
        df_log = pd.DataFrame(st.session_state.historial_alertas)
        st.table(df_log.tail(10))
        if st.button("🗑️ Limpiar historial"):
            st.session_state.historial_alertas = []
            st.rerun()

st.divider()
st.write(f"Última actualización: **{datetime.now().strftime('%H:%M:%S')}**")

cols = st.columns(2)
headers = {"X-API-Key": API_KEY}

for i, icao in enumerate(AERODROMOS):
    try:
        r_hash = random.randint(1, 999999)
        # Consultas a API
        res_m = requests.get(f"https://api.checkwx.com/metar/{icao}?cache={r_hash}", headers=headers).json()
        metar = res_m.get('data', ['Sin datos'])[0]
        
        res_t = requests.get(f"https://api.checkwx.com/taf/{icao}?cache={r_hash}", headers=headers).json()
        taf = res_t.get('data', ['Sin datos'])[0]
        
        alertas = auditar(icao, metar, taf) if "Sin datos" not in [metar, taf] else []
        icono = obtener_icono_clima(metar)

        with cols[i % 2]:
            estado = "⚠️ ENMIENDA" if alertas else "✅ OK"
            color_border = "red" if alertas else "green"
            
            with st.expander(f"{icono} {icao} - {estado}", expanded=True):
                st.info(f"**TAF:** {taf}")
                st.success(f"**METAR:** {metar}")
                for a in alertas:
                    st.error(a)
                    # Registro en historial si no está ya presente en este ciclo
                    st.session_state.historial_alertas.append({
                        "Hora": datetime.now().strftime("%H:%M"),
                        "OACI": icao,
                        "Criterio": a
                    })
    except Exception:
        st.error(f"Error de conexión con {icao}")

# --- 4. DERECHOS DE AUTOR ---
st.markdown(
    f"""<div class="copyright">
    © {datetime.now().year} - Sistema de Vigilancia Meteorológica Aeronáutica <br>
    Desarrollado por <b>RICARTEZ ANIBAL</b> & <b>Gemini AI</b>. Basado en Criterios de Enmienda TAF - SMN Argentina.
    </div>""", unsafe_allow_html=True
)
