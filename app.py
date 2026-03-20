from flask import Flask, render_template

app = Flask(__name__)

# --- LA FUNCIÓN DE LÓGICA (Basada en el PDF del SMN) ---
def check_amendment_criteria(taf, metar):
    alerts = []
    # Viento: Cambio >= 60° con velocidad >= 10kt
    if abs(taf['w_dir'] - metar['w_dir']) >= 60 and (taf['w_spd'] >= 10 or metar['w_spd'] >= 10):
        alerts.append("VIENTO: Cambio de dirección >= 60° con > 10kt")
    
    # Visibilidad: Cruce de umbrales operativos
    umbrales_vis = [150, 350, 600, 800, 1500, 3000, 5000]
    for u in umbrales_vis:
        if (taf['vis'] < u <= metar['vis']) or (taf['vis'] >= u > metar['vis']):
            alerts.append(f"VISIBILIDAD: Cruzó umbral de {u}m")
            
    # Techo de nubes (BKN/OVC): Cruce de umbrales
    umbrales_nubes = [100, 200, 500, 1000, 1500]
    for u in umbrales_nubes:
        if (taf['ceil'] < u <= metar['ceil']) or (taf['ceil'] >= u > metar['ceil']):
            alerts.append(f"NUBES: Techo cruzó umbral de {u}ft")

    return alerts

@app.route('/')
def index():
    # DATOS DE PRUEBA (Aquí iría lo que extraés de tu base de datos o API)
    taf_data = {'w_dir': 100, 'w_spd': 5, 'vis': 5000, 'ceil': 2000}
    metar_data = {'w_dir': 180, 'w_spd': 15, 'vis': 800, 'ceil': 400}

    # Ejecutamos la lógica
    lista_alertas = check_amendment_criteria(taf_data, metar_data)

    # ¡ESTO ES LO IMPORTANTE! Pasamos 'lista_alertas' al HTML
    return render_template('index.html', alertas=lista_alertas)

if __name__ == '__main__':
    app.run(debug=True)
