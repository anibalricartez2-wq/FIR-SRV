import streamlit as st

# --- CONFIGURACIÓN DE INTERFAZ ---
st.set_page_config(page_title="Monitor TAF - Criterios SMN", layout="centered")
st.title("✈️ Validador de Enmiendas TAF")
st.markdown("---")

# --- PARÁMETROS TÉCNICOS (Tabla de Enmiendas SMN) ---
# Umbrales de visibilidad en metros
VIS_THRESHOLDS = [150, 350, 600, 800, 1500, 3000, 5000]

# Umbrales de techo (BKN/OVC) y Visibilidad Vertical en pies
HEIGHT_THRESHOLDS = [100, 200, 500, 1000, 1500]

# Fenómenos significativos
SIG_PHENOMENA = ['TS', 'GR', 'RA', 'SN', 'DZ', 'FG', 'FC', 'SS', 'DS', 'SQ', 'VA']

def verificar_enmienda(taf, metar):
    alertas = []
    
    # 1. VIENTO
    # Cambio de dirección >= 60° con velocidad >= 10kt
    if abs(taf['w_dir'] - metar['w_dir']) >= 60 and (taf['w_spd'] >= 10 or metar['w_spd'] >= 10):
        alertas.append(f"VIENTO: Cambio de dirección >= 60° con intensidad >= 10kt")
        
    # Cambio de velocidad media >= 10kt
    if abs(taf['w_spd'] - metar['w_spd']) >= 10:
        alertas.append("VIENTO: Variación de velocidad media >= 10kt")

    # 2. VISIBILIDAD
    for u in VIS_THRESHOLDS:
        if (taf['vis'] < u <= metar['vis']) or (taf['vis'] >= u > metar['vis']):
            alertas.append(f"VISIBILIDAD: Cruzó umbral de {u}m")

    # 3. NUBES (BKN/OVC)
    for u in HEIGHT_THRESHOLDS:
        if (taf['ceil'] < u <= metar['ceil']) or (taf['ceil'] >= u > metar['ceil']):
            alertas.append(f"NUBES: Techo cruzó umbral de {u}ft")
            
    # Cambio de cobertura bajo 1500ft
    if (taf['ceil'] <= 1500 or metar['ceil'] <= 1500):
        if taf['is_bkn'] != metar['is_bkn']:
            alertas.append("NUBES: Cambio de cobertura (SCT/FEW <-> BKN/OVC) bajo 1500ft")

    return alertas

# --- ENTRADA DE DATOS ---
col1, col2 = st.columns(2)

with col1:
    st.subheader("Datos del TAF")
    t_dir = st.number_input("Dirección Viento", value=120)
    t_spd = st.number_input("Velocidad (kt)", value=5)
    t_vis = st.number_input("Visibilidad (m)", value=6000)
    t_ceil = st.number_input("Techo (ft)", value=2000)
    t_bkn = st.checkbox("¿Es BKN u OVC? (TAF)", value=False)

with col2:
    st.subheader("Datos del METAR")
    m_dir = st.number_input("Dirección Viento ", value=190)
    m_spd = st.number_input("Velocidad (kt) ", value=12)
    m_vis = st.number_input("Visibilidad (m) ", value=1200)
    m_ceil = st.number_input("Techo (ft) ", value=800)
    m_bkn = st.checkbox("¿Es BKN u OVC? (METAR)", value=True)

# --- RESULTADO ---
st.markdown("---")
taf_obj = {'w_dir': t_dir, 'w_spd': t_spd, 'vis': t_vis, 'ceil': t_ceil, 'is_bkn': t_bkn}
metar_obj = {'w_dir': m_dir, 'w_spd': m_spd, 'vis': m_vis, 'ceil': m_ceil, 'is_bkn': m_bkn}

motivos = verificar_enmienda(taf_obj, metar_obj)

if motivos:
    st.error("🚨 SE REQUIERE ENMIENDA")
    for m in motivos:
        st.write(f"- {m}")
else:
    st.success("✅ No se requiere enmienda.")
