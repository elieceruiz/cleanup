import streamlit as st
from PIL import Image
import io, base64
import pymongo
from datetime import datetime
import pytz

from streamlit_autorefresh import st_autorefresh
st_autorefresh(interval=1000, key="refresh")

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

# === INIT SESSION STATE ===
st.set_page_config(page_title="🧹 Cleanup App", layout="centered")

for k in ["start_time", "image_before", "edges_before", "session_id", "image_after", "edges_after", "result_shown"]:
    if k not in st.session_state:
        st.session_state[k] = None

# === TABS ===
tab1, tab2 = st.tabs(["🧹 Sesión Actual", "📜 Historial"])

# === TAB 1: SESIÓN ACTUAL ===
with tab1:
    st.title("🧹 Cleanup Visual Tracker")

    # Recuperar sesión activa si hay
    if st.session_state.start_time is None:
        last = collection.find_one({"session_active": True}, sort=[("start_time", -1)])
        if last:
            try:
                st.session_state.start_time = last["start_time"].replace(tzinfo=pytz.utc).astimezone(zona_col)
                st.session_state.image_before = base64_to_image(last["image_base64"])
                st.session_state.edges_before = last["edges"]
                st.session_state.session_id = last["_id"]
            except:
                st.warning("⚠️ No se pudo restaurar la sesión anterior.")

    # Si ya cargó la imagen ANTES
    if st.session_state.image_before:
        st.subheader("🖼️ Imagen ANTES")
        st.image(st.session_state.image_before, width=300)
        st.markdown(f"**Edges ANTES:** `{st.session_state.edges_before}`")

        now = datetime.now(zona_col)
        elapsed = now - st.session_state.start_time
        m, s = divmod(elapsed.total_seconds(), 60)
        st.markdown(f"### ⏱️ Tiempo activo: **{int(m)} min {int(s)} sec**")

        # Subir y procesar imagen después
        st.subheader("📸 Imagen DESPUÉS")
        img_file_after = st.file_uploader("Después", type=["jpg", "jpeg", "png"], key="after")

        if img_file_after and st.session_state.image_after is None:
            try:
                img = Image.open(img_file_after)
                resized = resize_image(img)
                score = simple_edge_score(resized)
                img_b64 = image_to_base64(resized)
                duration = int((datetime.now(zona_col) - st.session_state.start_time).total_seconds())
                improved = score < st.session_state.edges_before

                collection.update_one(
                    {"_id": st.session_state.session_id},
                    {"$set": {
                        "session_active": False,
                        "end_time": datetime.now(zona_col),
                        "duration_seconds": duration,
                        "image_after": img_b64,
                        "edges_after": score,
                        "improved": improved
                    }}
                )

                st.session_state.image_after = resized
                st.session_state.edges_after = score
                st.session_state.result_shown = True
                st.success("✅ Imagen procesada y sesión cerrada.")

            except Exception as e:
                st.error(f"❌ Error al guardar sesión: {e}")

        if st.session_state.result_shown and st.session_state.image_after:
            st.image(st.session_state.image_after, width=300, caption="🖼️ Imagen DESPUÉS")
            st.markdown(f"**Edges DESPUÉS:** `{st.session_state.edges_after}`")

            duration = int((datetime.now(zona_col) - st.session_state.start_time).total_seconds())
            improved = st.session_state.edges_after < st.session_state.edges_before

            st.markdown("### ✅ Resultado de comparación:")
            st.markdown(f"**Duración total:** `{duration} segundos`")
            if improved:
                st.success("✅ Hubo mejora: la segunda imagen tiene menos bordes.")
            else:
                st.warning("❌ No hubo mejora: los bordes no disminuyeron.")

            if st.button("🔁 Iniciar nueva sesión"):
                st.session_state.clear()
                st.rerun()

    # Si aún no hay sesión activa, subir imagen inicial
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

# === TAB 2: HISTORIAL ===
with tab2:
    st.title("📜 Historial de sesiones")

    records = list(
        collection.find({"session_active": False}).sort("start_time", -1).limit(10)
    )

    if not records:
        st.info("Aún no hay sesiones finalizadas registradas.")
    else:
        for r in records:
            fecha = r.get("start_time", datetime.now()).astimezone(zona_col).strftime("%Y-%m-%d %H:%M")
            dur = r.get("duration_seconds", 0)
            edges_before = r.get("edges", "?")
            edges_after = r.get("edges_after", "?")
            improved = r.get("improved", False)

            st.markdown(f"#### 🗓️ {fecha} — ⏱️ {dur} seg — {'✅ Mejora' if improved else '❌ Sin mejora'}")
            col1, col2 = st.columns(2)
            with col1:
                st.image(base64_to_image(r["image_base64"]), caption="ANTES", width=250)
                st.markdown(f"**Edges:** {edges_before}")
            with col2:
                if "image_after" in r:
                    st.image(base64_to_image(r["image_after"]), caption="DESPUÉS", width=250)
                    st.markdown(f"**Edges:** {edges_after}")
                else:
                    st.warning("⚠️ No se cargó imagen después.")
