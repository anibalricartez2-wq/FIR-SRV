import streamlit as st

# --- PARÁMETROS SMN (Criterios de Enmienda) ---
VIS_THRESHOLDS = [150, 350, 600, 800, 1500, 3000, 5000]
HEIGHT_THRESHOLDS = [100, 200, 500, 1000, 1500]

def check_amendment_criteria(taf, metar):
    alerts = []
    # Viento: Cambio >= 60° con velocidad >= 10kt
    if abs(taf['w_dir'] - metar['w_dir']) >= 60 and (taf['w_spd'] >= 10 or metar['w_spd'] >= 10):
        alerts.append("VIENTO: Cambio de dirección >= 60° con > 10kt")
    
    # Visibilidad: Cruce de umbrales
    for u in VIS_THRESHOLDS:
        if (taf['vis'] < u <= metar['vis']) or (taf['vis'] >= u > metar['vis']):
            alerts.append(f"VISIBILIDAD: Cruzó umbral de {u}m")
            
    # Techo de nubes: Cruce de umbrales
    for u in HEIGHT_THRESHOLDS:
        if (taf['ceil'] < u <= metar['ceil']) or (taf['ceil'] >= u > metar['ceil']):
            alerts.append(f"NUBES: Techo cruzó umbral de {u}ft")
    return alerts

# --- INTERFAZ DE STREAMLIT ---
st.set_page_config(page_title="Monitor TAF - SMN", page_icon="✈️")
st.title("✈️ Monitor de Enmiendas TAF")
st.write("Basado en criterios técnicos del SMN Argentina.")

# Datos de prueba (Aquí podés conectar tu lógica de meteorología)
taf_data = {'w_dir': 100, 'w_spd': 5, 'vis': 5000, 'ceil': 2000}
metar_data = {'w_dir': 180, 'w_spd': 15, 'vis': 800, 'ceil': 400}

st.subheader("Estado Actual")
alertas = check_amendment_criteria(taf_data, metar_data)

if alertas:
    for alerta in alertas:
        st.error(f"⚠️ {alerta}")
else:
    st.success("✅ No se requiere enmienda.")
