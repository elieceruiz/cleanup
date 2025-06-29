import streamlit as st
import pymongo
from PIL import Image
import io, base64
from datetime import datetime, timedelta, timezone
import pytz
from streamlit_autorefresh import st_autorefresh

# === CONFIG ===
st.set_page_config(page_title="🧹 Cleanup Visual Tracker", layout="centered")
MONGO_URI = st.secrets["mongo_uri"]
client = pymongo.MongoClient(MONGO_URI)
db = client.cleanup
collection = db.entries
meta = db.meta

# Timezones
CO = pytz.timezone("America/Bogota")

# === UTILS ===
def resize_image(img: Image.Image, max_width=300) -> Image.Image:
    img = img.convert("RGB")
    w, h = img.size
    if w > max_width:
        ratio = max_width / w
        img = img.resize((int(w * ratio), int(h * ratio)))
    return img

def image_to_base64(img: Image.Image) -> str:
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=40, optimize=True)
    return base64.b64encode(buffer.getvalue()).decode()

def base64_to_image(b64_str: str) -> Image.Image:
    try:
        img = Image.open(io.BytesIO(base64.b64decode(b64_str)))
        return img.convert("RGB")
    except Exception as e:
        st.warning(f"⚠️ Error cargando imagen: {e} (base64 size: {len(b64_str)})")
        return Image.new("RGB", (300, 200), color="gray")

def simple_edge_score(img: Image.Image) -> int:
    grayscale = img.convert("L")
    pixels = list(grayscale.getdata())
    diffs = [abs(pixels[i] - pixels[i+1]) for i in range(len(pixels)-1)]
    return sum(d > 10 for d in diffs)

# === STATE ===
if "start_time" not in st.session_state:
    st.session_state.start_time = None
if "img_before" not in st.session_state:
    st.session_state.img_before = None
if "before_edges" not in st.session_state:
    st.session_state.before_edges = 0
if "session_id" not in st.session_state:
    st.session_state.session_id = None
if "ready" not in st.session_state:
    st.session_state.ready = False
if "last_check" not in st.session_state:
    st.session_state.last_check = datetime(2000, 1, 1, tzinfo=timezone.utc)

# === SYNC META ===
meta_doc = meta.find_one({}) or {}
last_reset = meta_doc.get("last_reset", datetime(2000, 1, 1)).replace(tzinfo=timezone.utc)
last_session_start = meta_doc.get("last_session_start", datetime(2000, 1, 1)).replace(tzinfo=timezone.utc)
last = collection.find_one(sort=[("start_time", -1)])
historial = collection.count_documents({"session_active": False})

if (not last or not last.get("session_active")) and (
    last_reset > st.session_state.last_check or last_session_start > st.session_state.last_check
):
    st.session_state.last_check = datetime.now(timezone.utc)
    st.rerun()

# === AUTORREFRESH SI HAY SESIÓN ACTIVA ===
if last and last.get("session_active"):
    st_autorefresh(interval=1000, key="refresh")

# === FRONT ===
tabs = st.tabs(["🧽 Sesión Actual", "📜 Historial"])

with tabs[0]:
    st.title("🧹 Cleanup Visual Tracker")

    if not last or not last.get("session_active"):
        st.warning("⚠️ No hay sesión activa. Última sesión completada:")
        latest = collection.find_one({"session_active": False}, sort=[("end_time", -1)])
        if latest:
            ts = latest["start_time"].astimezone(CO).strftime("%Y-%m-%d %H:%M")
            dur = latest.get("duration_seconds", 0)
            st.markdown(f"📅 {ts} — ⏱️ {dur} seg — {'✅ Mejora' if latest.get('improved') else '❌ Sin mejora'}")
            col1, col2 = st.columns(2)
            with col1:
                st.image(base64_to_image(latest.get("image_base64", "")), caption="ANTES", width=250)
                st.markdown(f"Edges: {latest.get('edges', 0):,}")
            with col2:
                st.image(base64_to_image(latest.get("image_after", "")), caption="DESPUÉS", width=250)
                st.markdown(f"Edges: {latest.get('edges_after', 0):,}")
        if st.button("🔁 Iniciar nueva sesión"):
            # Limpiar estado local
            st.session_state.clear()

            # Marcar sesiones anteriores como inactivas (por si alguna quedó viva)
            collection.update_many({"session_active": True}, {"$set": {"session_active": False}})

            # Actualizar 'meta' para forzar sincronización
            meta.update_one(
                {},
                {"$set": {"last_session_start": datetime.now(timezone.utc)}},
                upsert=True
            )

            # Recargar la App para reflejar el reinicio
            st.rerun()

    # === SESIÓN ACTIVA ===
    if last and last.get("session_active"):
        # Hidratar estado local siempre que cambie la sesión activa (comparando session_id)
        mongo_session_id = str(last["_id"])
        local_session_id = str(st.session_state.session_id) if st.session_state.session_id else None
        if mongo_session_id != local_session_id:
            st.session_state.img_before = base64_to_image(last.get("image_base64", ""))
            st.session_state.before_edges = last.get("edges", 0)
            st.session_state.start_time = last.get("start_time").astimezone(CO)
            st.session_state.ready = True
            st.session_state.session_id = last["_id"]

        if not st.session_state.img_before:
            st.subheader("Subí la imagen del ANTES")
            img_file = st.file_uploader("Antes", type=["jpg", "jpeg", "png"], key="before")
            if img_file and st.button("🟢 Iniciar sesión"):
                img = Image.open(img_file)
                resized = resize_image(img)
                img_b64 = image_to_base64(resized)
                edges = simple_edge_score(resized)

                st.session_state.img_before = resized
                st.session_state.before_edges = edges
                st.session_state.start_time = datetime.now(CO)
                st.session_state.ready = True

                result = collection.insert_one({
                    "session_active": True,
                    "start_time": datetime.now(timezone.utc),
                    "image_base64": img_b64,
                    "edges": edges,
                })
                st.session_state.session_id = result.inserted_id
                meta.update_one({}, {"$set": {"last_session_start": datetime.now(timezone.utc)}}, upsert=True)
                st.rerun()

        if st.session_state.img_before:
            st.image(st.session_state.img_before, caption="ANTES", width=300)
            st.markdown(f"Edges: {st.session_state.before_edges:,}")
            now = datetime.now(CO)
            elapsed = now - st.session_state.start_time
            st.markdown(f"⏱️ Tiempo activo: {int(elapsed.total_seconds())} seg")

            st.subheader("Subí la imagen del DESPUÉS")
            img_after_file = st.file_uploader("Después", type=["jpg", "jpeg", "png"], key="after")

            if img_after_file and st.button("✅ Finalizar y comparar"):
                img_after = Image.open(img_after_file)
                resized_after = resize_image(img_after)
                img_b64_after = image_to_base64(resized_after)
                edges_after = simple_edge_score(resized_after)
                improved = edges_after < st.session_state.before_edges * 0.9
                end_time = datetime.now(timezone.utc)
                duration = int((end_time - st.session_state.start_time.replace(tzinfo=None)).total_seconds())

                collection.update_one(
                    {"_id": st.session_state.session_id},
                    {"$set": {
                        "session_active": False,
                        "end_time": end_time,
                        "image_after": img_b64_after,
                        "edges_after": edges_after,
                        "improved": improved,
                        "duration_seconds": duration,
                    }}
                )
                st.success("🧹 Sesión registrada exitosamente.")
                st.session_state.img_before = None
                st.session_state.ready = False
                st.session_state.start_time = None
                st.session_state.before_edges = 0
                st.rerun()

with tabs[1]:
    st.title("📜 Historial")
    registros = list(collection.find({"session_active": False}).sort("start_time", -1).limit(10))
    for r in registros:
        ts = r["start_time"].astimezone(CO).strftime("%Y-%m-%d %H:%M:%S")
        dur = r.get("duration_seconds", 0)
        st.markdown(f"📅 {ts} — ⏱️ {dur} seg — {'✅ Mejora' if r.get('improved') else '❌ Sin mejora'}")
        col1, col2 = st.columns(2)
        with col1:
            st.image(base64_to_image(r.get("image_base64", "")), caption="ANTES", width=200)
            st.markdown(f"Edges: {r.get('edges', 0):,}")
        with col2:
            st.image(base64_to_image(r.get("image_after", "")), caption="DESPUÉS", width=200)
            st.markdown(f"Edges: {r.get('edges_after', 0):,}")
        st.divider()

    with st.expander("🧨 Borrar todos los registros"):
        if st.button("🗑️ Borrar todo"):
            collection.delete_many({})
            meta.update_one({}, {"$set": {"last_reset": datetime.now(timezone.utc)}}, upsert=True)
            st.success("Registros eliminados.")
            st.rerun()
