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

# REFRESH CADA 30 MINUTOS
st_autorefresh(interval=1800000, key="datarefresh")

API_KEY = "8e7917816866402688f805f637eb54d3"
AERODROMOS = ["SAVV","SAVE","SAVT","SAWC","SAVC","SAWG","SAWE","SAWH"]

# --- 2. FUNCIONES DE EXTRACCIÓN PRECISAS ---

def parse_viento(texto):
    if not texto or "Sin datos" in texto: return None, None, None
    # Busca grupo de viento (ej: 27015G25KT)
    match = re.search(r'\b(\d{3})(\d{2,3})(G\d{2,3})?KT\b', texto)
    if match:
        d = int(match.group(1))
        v = int(match.group(2))
        g = int(match.group(3)[1:]) if match.group(3) else 0
        return d, v, g
    return None, None, None

def parse_visibilidad(texto):
    # Busca 4 números aislados (visibilidad en metros)
    match = re.search(r'\b(\d{4})\b', texto)
    if match:
        return int(match.group(1))
    if "CAVOK" in texto: return 9999
    return 9999

def parse_nubes(texto):
    # Criterio SMN: Solo importa la base de BKN u OVC por debajo de 1500ft
    capas = re.findall(r'\b(BKN|OVC)(\d{3})\b', texto)
    if capas:
        return min(int(c[1]) * 100 for c in capas)
    return 9999

def extraer_fenomenos(texto):
    """Extrae códigos de fenómenos como +RA, -DZ, FG, TS, etc., evitando nubes o indicadores de tiempo"""
    codigos = ["VC", "MI", "BC", "PR", "DR", "BL", "SH", "TS", "FZ", "DZ", "RA", "SN", "SG", "IC", "PL", "GR", "GS", "BR", "FG", "FU", "VA", "DU", "SA", "HZ", "PO", "SQ", "FC", "SS", "DS"]
    encontrados = []
    palabras = texto.split()
    for p in palabras:
        # Limpia intensidades para buscar el código base
        base = p.replace("+", "").replace("-", "")
        # Si la palabra contiene algún código de fenómeno y es corta (evita confundir con nubes)
        if any(c in base for c in codigos) and len(base) <= 4:
            encontrados.append(p)
    return set(encontrados)

def obtener_icono_clima(metar_text):
    icon = "✈️"
    prefijo = "⚠️ " if "+" in metar_text else ""
    if "TS" in metar_text: icon = "⛈️"
    elif "VA" in metar_text: icon = "🌋"
    elif "SN" in metar_text: icon = "❄️"
    elif "RA" in metar_text or "DZ" in metar_text: icon = "🌧️"
    elif "FG" in metar_text or "BR" in metar_text: icon = "🌫️"
    elif "SKC" in metar_text or "CLR" in metar_text or "NSC" in metar_text or "CAVOK" in metar_text: icon = "☀️"
    return f"{prefijo}{icon}"

def auditar(icao, metar, taf):
    enmiendas = []
    
    # 1. VIENTO
    dr, vr, gr = parse_viento(metar)
    dt, vt, gt = parse_viento(taf)
    if vr is not None and vt is not None:
        if (vr >= 10 or vt >= 10) and abs(dr - dt) >= 60:
            enmiendas.append(f"VIENTO: Giro >= 60° ({dr}° vs {dt}°)")
        if abs(vr - vt) >= 10:
            enmiendas.append(f"VIENTO: Dif. Vel. media >= 10kt")
        if (gr >= 15 or vr + 10 >= 15) and abs(gr - gt) >= 10:
            enmiendas.append(f"VIENTO: Ráfaga (Dif >= 10kt)")

    # 2. VISIBILIDAD (Umbrales SMN)
    v_metar = parse_visibilidad(metar)
    v_taf = parse_visibilidad(taf)
    umbrales_v = [150, 350, 600, 800, 1500, 3000, 5000]
    for u in umbrales_v:
        if (v_metar <= u < v_taf) or (v_taf <= u < v_metar):
            enmiendas.append(f"VIS: Cruzó umbral {u}m ({v_metar}m)")
            break

    # 3. TECHOS (BKN/OVC)
    n_metar = parse_nubes(metar)
    n_taf = parse_nubes(taf)
    umbrales_n = [100, 200, 500, 1000, 1500]
    for u in umbrales_n:
        if (n_metar <= u < n_taf) or (n_taf <= u < n_metar):
            enmiendas.append(f"NUBES: Techo cruzó {u}ft ({n_metar}ft)")
            break

    # 4. FENÓMENOS E INTENSIDADES (VERIFICACIÓN PRECISA)
    f_metar = extraer_fenomenos(metar)
    f_taf = extraer_fenomenos(taf)
    
    # Si hay algo en el METAR que no está en el TAF (incluyendo cambios de + o -)
    cambios = f_metar.symmetric_difference(f_taf)
    if cambios:
        for c in cambios:
            if c in f_metar:
                enmiendas.append(f"FENÓMENO: Nuevo o Intenso ({c})")
            else:
                enmiendas.append(f"FENÓMENO: Cesó ({c})")
            
    return enmiendas

# --- 3. INTERFAZ ---
st.title("🖥️ Vigilancia FIR SAVC (Criterios SMN Verificados)")

if st.session_state.historial_alertas:
    with st.expander("📊 Registro de Enmiendas Requeridas"):
        df_log = pd.DataFrame(st.session_state.historial_alertas)
        st.table(df_log.tail(10))
        if st.button("Limpiar historial"):
            st.session_state.historial_alertas = []
            st.rerun()

st.divider()
st.write(f"Sincronizado: **{datetime.now().strftime('%H:%M:%S')}**")

cols = st.columns(2)
headers = {"X-API-Key": API_KEY}

for i, icao in enumerate(AERODROMOS):
    try:
        r_hash = random.randint(1, 999999)
        m_data = requests.get(f"https://api.checkwx.com/metar/{icao}?cache={r_hash}", headers=headers).json()
        t_data = requests.get(f"https://api.checkwx.com/taf/{icao}?cache={r_hash}", headers=headers).json()
        
        metar = m_data.get('data', ['Sin datos'])[0]
        taf = t_data.get('data', ['Sin datos'])[0]
        
        alertas = auditar(icao, metar, taf) if "Sin datos" not in [metar, taf] else []
        icono = obtener_icono_clima(metar)

        with cols[i % 2]:
            estado = "⚠️ ENMIENDA" if alertas else "✅ OK"
            with st.expander(f"{icono} {icao} - {estado}", expanded=True):
                st.info(f"**TAF:** {taf}")
                st.success(f"**METAR:** {metar}")
                for a in alertas:
                    st.error(a)
                    # Evitar duplicados idénticos seguidos en el log
                    if not st.session_state.historial_alertas or st.session_state.historial_alertas[-1]['Criterio'] != a:
                        st.session_state.historial_alertas.append({
                            "Hora": datetime.now().strftime("%H:%M"),
                            "OACI": icao,
                            "Criterio": a
                        })
    except Exception:
        st.error(f"Error de comunicación en {icao}")

st.markdown(
    f"""<div class="copyright">
    © {datetime.now().year} - Vigilancia Meteorológica <br>
    Desarrollado por <b>Usuario</b> & <b>Gemini AI</b>. Auditoría estricta según Tabla SMN.
    </div>""", unsafe_allow_html=True
)
