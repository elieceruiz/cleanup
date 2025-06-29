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

def base64_to_image(b64_str: str) -> Image.Image:
    return Image.open(io.BytesIO(base64.b64decode(b64_str)))

def simple_edge_score(img: Image.Image) -> int:
    grayscale = img.convert("L")
    pixels = list(grayscale.getdata())
    diffs = [abs(pixels[i] - pixels[i+1]) for i in range(len(pixels)-1)]
    return sum(d > 10 for d in diffs)

# ==== INICIALIZACIÓN DE ESTADO ====
st.set_page_config(page_title="🧹 Visual Cleanup", layout="centered")
st.title("🧹 Cleanup Test con Edge Score")

for k in ["start_time", "image", "edges", "session_id"]:
    if k not in st.session_state:
        st.session_state[k] = None

# ==== RECUPERAR SESIÓN ACTIVA DESDE MONGO SI EXISTE ====
if st.session_state.start_time is None or st.session_state.image is None:
    last_active = collection.find_one({"session_active": True}, sort=[("start_time", -1)])
    if last_active:
        try:
            st.session_state.start_time = last_active["start_time"].replace(tzinfo=pytz.utc).astimezone(zona_col)
            st.session_state.image = base64_to_image(last_active["image_base64"])
            st.session_state.edges = last_active["edges"]
            st.session_state.session_id = last_active["_id"]
        except Exception as e:
            st.warning(f"No se pudo restaurar la sesión: {e}")

# ==== SI HAY SESIÓN ACTIVA ====
if st.session_state.image:
    st.image(st.session_state.image, caption="🖼️ Imagen ANTES", width=300)
    st.markdown(f"**Edges ANTES:** `{st.session_state.edges}`")

    now = datetime.now(zona_col)
    elapsed = now - st.session_state.start_time
    minutes, seconds = divmod(elapsed.total_seconds(), 60)
    st.markdown(f"### ⏱️ Tiempo activo: **{int(minutes)} min {int(seconds)} sec**")

    # ==== SUBIDA Y COMPARACIÓN DE IMAGEN DESPUÉS ====
    st.subheader("📸 Sube la imagen DESPUÉS")
    img_file_after = st.file_uploader("Después", type=["jpg", "jpeg", "png"], key="after")

    if img_file_after:
        try:
            img_after = Image.open(img_file_after)
            resized_after = resize_image(img_after)
            score_after = simple_edge_score(resized_after)
            st.image(resized_after, caption="🖼️ Imagen DESPUÉS", width=300)
            st.markdown(f"**Edges DESPUÉS:** `{score_after}`")

            if st.button("🟣 Finalizar y comparar"):
                duration = int((datetime.now(zona_col) - st.session_state.start_time).total_seconds())
                improved = score_after < st.session_state.edges
                img_b64_after = image_to_base64(resized_after)

                collection.update_one(
                    {"_id": st.session_state.session_id},
                    {"$set": {
                        "session_active": False,
                        "end_time": datetime.now(zona_col),
                        "duration_seconds": duration,
                        "image_after": img_b64_after,
                        "edges_after": score_after,
                        "improved": improved
                    }}
                )

                if improved:
                    st.success("✅ Hubo mejora: la segunda imagen tiene menos bordes.")
                else:
                    st.warning("❌ No hubo mejora: los bordes no disminuyeron.")

                st.markdown("---")
                st.info("🔄 Reiniciando para una nueva sesión...")
                st.session_state.clear()
                st.rerun()

        except Exception as e:
            st.error(f"❌ Error procesando la imagen después: {e}")

# ==== SI NO HAY SESIÓN ACTIVA, SUBIR IMAGEN ANTES ====
else:
    st.subheader("📤 Sube una imagen inicial")
    img_file = st.file_uploader("Antes", type=["jpg", "jpeg", "png"])
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

            st.success("✅ Imagen inicial guardada. Cronómetro iniciado.")
        except Exception as e:
            st.error(f"❌ No se pudo subir la imagen inicial: {e}")
