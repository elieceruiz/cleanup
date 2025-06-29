import streamlit as st
import cv2
import numpy as np
import tempfile
import time
from datetime import datetime
from pymongo import MongoClient

# --- CONFIGURACIÓN ---
MONGO_URI = st.secrets["mongo_uri"]
client = MongoClient(MONGO_URI)
db = client["ordenador_visual"]
coleccion = db["registros"]

# --- FUNCIÓN DE DETECCIÓN SIMPLIFICADA ---
def detectar_bordes(imagen):
    gris = cv2.cvtColor(imagen, cv2.COLOR_BGR2GRAY)
    bordes = cv2.Canny(gris, 100, 200)
    return bordes

# --- INTERFAZ STREAMLIT ---
st.set_page_config("Ordenador Visual", layout="centered")
st.title("🧹 Ordenador Visual")

st.markdown("Sube una imagen del **ANTES** y otra del **DESPUÉS** para evaluar el cambio y registrar el esfuerzo.")

col1, col2 = st.columns(2)

with col1:
    antes_file = st.file_uploader("Foto ANTES", type=["jpg", "png", "jpeg"], key="antes")
with col2:
    despues_file = st.file_uploader("Foto DESPUÉS", type=["jpg", "png", "jpeg"], key="despues")

if antes_file and despues_file:
    # Cargar imágenes
    img_antes = cv2.imdecode(np.frombuffer(antes_file.read(), np.uint8), 1)
    img_despues = cv2.imdecode(np.frombuffer(despues_file.read(), np.uint8), 1)

    # Detectar bordes como proxy visual del desorden
    bordes_antes = detectar_bordes(img_antes)
    bordes_despues = detectar_bordes(img_despues)

    # Comparar cantidad de bordes
    conteo_antes = np.sum(bordes_antes > 0)
    conteo_despues = np.sum(bordes_despues > 0)

    st.subheader("Resultado")
    mejora = conteo_despues < conteo_antes
    st.write(f"Pixeles con bordes (ANTES): {conteo_antes:,}")
    st.write(f"Pixeles con bordes (DESPUÉS): {conteo_despues:,}")

    if mejora:
        duracion = st.number_input("¿Cuántos minutos tardaste?", min_value=1, max_value=240, step=1)
        if st.button("Guardar registro"):
            coleccion.insert_one({
                "timestamp": datetime.now(),
                "bordes_antes": int(conteo_antes),
                "bordes_despues": int(conteo_despues),
                "mejora": True,
                "minutos": duracion
            })
            st.success("✅ Registro guardado en MongoDB")
    else:
        st.warning("No se detecta mejora visual. Intenta otra vez o revisa las fotos.")

    # Mostrar imágenes
    st.image([img_antes, img_despues], caption=["ANTES", "DESPUÉS"], width=300)

# Mostrar historial
st.divider()
st.subheader("📜 Historial de acciones")
registros = list(coleccion.find().sort("timestamp", -1).limit(10))
if registros:
    for r in registros:
        st.write(f"🕒 {r['timestamp'].strftime('%Y-%m-%d %H:%M:%S')} — {r['minutos']} min — Mejora: {'✅' if r['mejora'] else '❌'}")
else:
    st.info("Aún no hay registros.")
