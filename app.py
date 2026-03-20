import streamlit as st
import requests
import re
import random
import pandas as pd
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

# --- 1. CONFIGURACIÓN ---
st.set_page_config(page_title="Vigilancia FIR SAVC", page_icon="✈️", layout="wide")

# Refresco cada 30 minutos (1800000 ms)
st_autorefresh(interval=1800000, key="datarefresh")

# --- 2. FUNCIONES DE EXTRACCIÓN (PARSERS) ---
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
    # Busca la capa más baja de BKN u OVC
    capas = re.findall(r'(BKN|OVC)(\d{3})', texto)
    if capas:
        return min(int(c[1]) * 100 for c in capas)
    return 9999

# --- 3. LÓGICA DE AUDITORÍA (SEGÚN TABLA SMN) ---
def auditar(icao, metar, taf):
    enmiendas = []
    
    # Datos METAR
    dr, vr, gr = parse_viento(metar)
    vis_r = parse_visibilidad(metar)
    techo_r = parse_nubes(metar)
    
    # Datos TAF
    dt, vt, gt = parse_viento(taf)
    vis_t = parse_visibilidad(taf)
    techo_t = parse_nubes(taf)

    # A) VIENTO 
    if vr is not None and vt is not None:
        # Cambio de dirección >= 60° con viento >= 10kt
        if (vr >= 10 or vt >= 10) and abs(dr - dt) >= 60:
            enmiendas.append(f"VIENTO: Giro >= 60° ({dr}° vs {dt}°)")
        
        # Cambio velocidad media >= 10kt
        if abs(vr - vt) >= 10:
            enmiendas.append(f"VIENTO: Dif. Vel. >= 10kt ({vr} vs {vt}kt)")
            
        # Ráfagas (Gusts): Variación >= 10kt siendo media >= 15kt
        if (gr > 0) and (vr >= 15 or vt >= 15) and (gr - vr >= 10):
            enmiendas.append(f"VIENTO: Ráfagas detectadas (+{gr-vr}kt)")

    # B) VISIBILIDAD (Umbrales SMN: 150, 350, 600, 800, 1500, 3000, 5000) 
    umbrales_vis = [150, 350, 600, 800, 1500, 3000, 5000]
    for u in umbrales_vis:
        if (vis_r <= u < vis_t) or (vis_t <= u < vis_r):
            enmiendas.append(f"VIS: Cruzó umbral de {u}m")
            break

    # C) NUBES (Umbrales BKN/OVC: 100, 200, 500, 1000, 1500 ft) 
    umbrales_nubes = [100, 200, 500, 1000, 1500]
    for u in umbrales_nubes:
        if (techo_r <= u < techo_t) or (techo_t <= u < techo_r):
            enmiendas.append(f"NUBES: Techo cruzó {u}ft")
            break

    # D) FENÓMENOS (Inicio/Fin de fenómenos críticos) 
    criticos = ["TS", "VA", "SQ", "FC", "FG", "FZRA", "DZ", "RA", "SN"]
    for f in criticos:
        if (f in metar and f not in taf) or (f in taf and f not in metar):
            enmiendas.append(f"FENÓMENO: Cambio en {f}")

    return enmiendas

# --- 4. INTERFAZ Y RENDERIZADO ---
# (Aquí va el resto de tu código de UI, columnas y el footer de copyright)
