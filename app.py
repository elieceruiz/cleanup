import streamlit as st
from PIL import Image
import io, base64
import pymongo
from datetime import datetime
import pytz

from streamlit_autorefresh import st_autorefresh
st_autorefresh(interval=1000, key="cronometro")

# === CONFIG ===
MONGO_URI = st.secrets["mongo_uri"]
client = pymongo.MongoClient(MONGO_URI)
db = client.cleanup
collection = db.entries
zona_col = pytz.timezone("America/Bogota")

# === UTILS ===
def resize_image(img, max_width=300):
    img = img.convert("RGB")
    w, h = img.size
    if w > max_width:
        ratio = max_width / w
        img = img.resize((int(w * ratio), int(h * ratio)))
    return img

def image_to_base64(img):
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=50, optimize=True)
    return base64.b64encode(buffer.getvalue()).decode()

def base64_to_image(b64):
    return Image.open(io.BytesIO(base64.b64decode(b64)))

def simple_edge_score(img):
    gray = img.convert("L")
    px = list(gray.getdata())
    diffs = [abs(px[i] - px[i+1]) for i in range(len(px)-1)]
    return sum(d > 10 for d in diffs)

# === INIT ===
st.set_page_config(page_title="🧹 Cleanup Tracker", layout="centered")
st.title("🧹 Cleanup Visual Tracker")

for k in ["start_time", "image_before", "edges_before", "session_id", "image_after", "edges_after", "result_shown"]:
    if k not in st.session_state:
        st.session_state[k] = None

# === RECUPERAR SESIÓN ACTIVA ===
if st.session_state.start_time is None:
    last = collection.find_one({"session_active": True}, sort=[("start_time", -1)])
    if last:
        try:
            st.session_state.start_time = last["start_time"].replace(tzinfo=pytz.utc).astimezone(zona_col)
            st.session_state.image_before = base64_to_image(last["image_base64"])
            st.session_state.edges_before = last["edges"]
            st.session_state.session_id = last["_id"]
        except:
            pass

# === SI HAY IMAGEN “ANTES” CARGADA ===
if st.session_state.image_before:
    st.subheader("🖼️ Imagen ANTES")
    st.image(st.session_state.image_before, width=300)
    st.markdown(f"**Edges ANTES:** `{st.session_state.edges_before}`")

    # Cronómetro
    now = datetime.now(zona_col)
    elapsed = now - st.session_state.start_time
    m, s = divmod(elapsed.total_seconds(), 60)
    st.markdown(f"### ⏱️ Tiempo activo: **{int(m)} min {int(s)} sec**")

    # Subida imagen DESPUÉS
    st.subheader("📸 Imagen DESPUÉS")
    img_file_after = st.file_uploader("Después", type=["jpg", "jpeg", "png"], key="after")

    if img_file_after and st.session_state.image_after is None:
        try:
            img = Image.open(img_file_after)
            resized = resize_image(img)
            score = simple_edge_score(resized)
            st.session_state.image_after = resized
            st.session_state.edges_after = score
            st.success("✅ Imagen después cargada y analizada.")
            st.rerun()
        except Exception as e:
            st.error(f"❌ Error procesando imagen después: {e}")

    if st.session_state.image_after:
        st.image(st.session_state.image_after, width=300, caption="🖼️ Imagen DESPUÉS")
        st.markdown(f"**Edges DESPUÉS:** `{st.session_state.edges_after}`")

        if st.button("🟣 Finalizar y comparar"):
            try:
                duration = int((datetime.now(zona_col) - st.session_state.start_time).total_seconds())
                improved = st.session_state.edges_after < st.session_state.edges_before
                img_b64_after = image_to_base64(st.session_state.image_after)

                collection.update_one(
                    {"_id": st.session_state.session_id},
                    {"$set": {
                        "session_active": False,
                        "end_time": datetime.now(zona_col),
                        "duration_seconds": duration,
                        "image_after": img_b64_after,
                        "edges_after": st.session_state.edges_after,
                        "improved": improved
                    }}
                )

                st.markdown("### ✅ Resultado de comparación:")
                st.markdown(f"**Duración total:** `{duration} segundos`")
                if improved:
                    st.success("✅ Hubo mejora: la segunda imagen tiene menos bordes.")
                else:
                    st.warning("❌ No hubo mejora: los bordes no disminuyeron.")

                st.session_state.result_shown = True

            except Exception as e:
                st.error(f"❌ Error al guardar resultado: {e}")

    if st.session_state.result_shown:
        if st.button("🔁 Iniciar nueva sesión"):
            st.session_state.clear()
            st.rerun()

# === SI NO HAY SESIÓN, PERMITIR INICIO CON SUBIDA AUTOMÁTICA ===
else:
    st.subheader("📤 Subí tu imagen inicial (ANTES)")
    img_file = st.file_uploader("Antes", type=["jpg", "jpeg", "png"])

    if img_file and st.session_state.image_before is None:
        try:
            img = Image.open(img_file)
            resized = resize_image(img)
            score = simple_edge_score(resized)
            img_b64 = image_to_base64(resized)
            ts = datetime.now(zona_col)

            res = collection.insert_one({
                "session_active": True,
                "start_time": ts,
                "image_base64": img_b64,
                "edges": score
            })

            st.session_state.start_time = ts
            st.session_state.image_before = resized
            st.session_state.edges_before = score
            st.session_state.session_id = res.inserted_id

            st.success("✅ Imagen inicial cargada. Cronómetro iniciado.")
            st.rerun()

        except Exception as e:
            st.error(f"❌ Error procesando imagen inicial: {e}")
