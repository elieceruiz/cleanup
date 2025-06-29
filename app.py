import streamlit as st
from PIL import Image
import io, base64
import pymongo
from datetime import datetime
import pytz

from streamlit_autorefresh import st_autorefresh
st_autorefresh(interval=1000, key="cronometro")

# ==== CONFIGURACIÓN ====
MONGO_URI = st.secrets["mongo_uri"]
client = pymongo.MongoClient(MONGO_URI)
db = client.cleanup
collection = db.entries

zona_col = pytz.timezone("America/Bogota")

# ==== FUNCIONES ====
def resize_image(img: Image.Image, max_width=300) -> Image.Image:
    img = img.convert("RGB")
    w, h = img.size
    if w > max_width:
        ratio = max_width / w
        img = img.resize((int(w * ratio), int(h * ratio)))
    return img

def image_to_base64(img: Image.Image) -> str:
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=50, optimize=True)
    return base64.b64encode(buffer.getvalue()).decode()

def simple_edge_score(img: Image.Image) -> int:
    grayscale = img.convert("L")
    pixels = list(grayscale.getdata())
    diffs = [abs(pixels[i] - pixels[i+1]) for i in range(len(pixels)-1)]
    return sum(d > 10 for d in diffs)

# ==== INTERFAZ ====
st.set_page_config(page_title="🧪 Test Mongo + Crono", layout="centered")
st.title("🧪 Test de Subida + Edges + Cronómetro")

if "start_time" not in st.session_state:
    st.session_state.start_time = None
if "image" not in st.session_state:
    st.session_state.image = None
if "edges" not in st.session_state:
    st.session_state.edges = None
if "session_id" not in st.session_state:
    st.session_state.session_id = None

if not st.session_state.image:
    img_file = st.file_uploader("Sube una imagen", type=["jpg", "jpeg", "png"])

    if img_file and st.button("🟢 Iniciar sesión"):
        try:
            image_raw = Image.open(img_file)
            resized = resize_image(image_raw)
            score = simple_edge_score(resized)
            img_b64 = image_to_base64(resized)
            timestamp = datetime.now(zona_col)

            result = collection.insert_one({
                "test": True,
                "session_active": True,
                "start_time": timestamp,
                "image_base64": img_b64,
                "edges": score
            })

            st.session_state.start_time = timestamp
            st.session_state.image = resized
            st.session_state.edges = score
            st.session_state.session_id = result.inserted_id

            st.success("✅ Imagen subida y sesión iniciada.")
        except Exception as e:
            st.error(f"❌ Error al subir: {e}")
else:
    st.image(st.session_state.image, caption="Imagen subida", width=300)
    st.markdown(f"**Edges:** `{st.session_state.edges}`")

    now = datetime.now(zona_col)
    elapsed = now - st.session_state.start_time
    minutes, seconds = divmod(elapsed.total_seconds(), 60)
    st.markdown(f"### ⏱️ Tiempo activo: **{int(minutes)} min {int(seconds)} sec**")

    if st.button("🛑 Finalizar sesión"):
        try:
            end_time = datetime.now(zona_col)
            duration = int((end_time - st.session_state.start_time).total_seconds())

            collection.update_one(
                {"_id": st.session_state.session_id},
                {"$set": {
                    "session_active": False,
                    "end_time": end_time,
                    "duration_seconds": duration
                }}
            )

            st.success(f"✅ Sesión finalizada ({duration} segundos).")

            # Limpiar estado
            st.session_state.start_time = None
            st.session_state.image = None
            st.session_state.edges = None
            st.session_state.session_id = None
        except Exception as e:
            st.error(f"❌ Error al finalizar sesión: {e}")
