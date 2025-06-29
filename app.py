import streamlit as st
from PIL import Image, ImageFilter
import numpy as np
from datetime import datetime
from pymongo import MongoClient
import io

# --- CONFIGURACIÓN ---
MONGO_URI = st.secrets["mongo_uri"]
client = MongoClient(MONGO_URI)
db = client["ordenador_visual"]
coleccion = db["registros"]

# --- DETECCIÓN DE BORDES SIN OPENCV ---
def contar_bordes(img: Image.Image) -> int:
    gris = img.convert("L")  # Escala de grises
    bordes = gris.filter(ImageFilter.FIND_EDGES)
    np_bordes = np.array(bordes)
    cantidad = np.sum(np_bordes > 50)  # Umbral básico
    return cantidad

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
    img_antes = Image.open(antes_file)
    img_despues = Image.open(despues_file)

    conteo_antes = contar_bordes(img_antes)
    conteo_despues = contar_bordes(img_despues)

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
