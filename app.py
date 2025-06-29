import streamlit as st
import pymongo
from PIL import Image
import io, base64
from datetime import datetime, timedelta, timezone
import pytz
from streamlit_autorefresh import st_autorefresh

# === CONFIG ===
st.set_page_config(page_title="🧹 Visualizador de Limpieza", layout="centered")
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

def format_seconds(seconds: int) -> str:
    """Convierte segundos en HH:MM:SS amigable."""
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02}:{m:02}:{s:02}"

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
if "img_after_uploaded" not in st.session_state:
    st.session_state.img_after_uploaded = None

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

# === AUTORREFRESH ALTO: sincronía en todos los dispositivos ===
if last and last.get("session_active"):
    st_autorefresh(interval=1000, key="sincronizador_global")

# === FRONT ===
tabs = st.tabs(["✨ Sesión Actual", "🗂️ Historial"])

with tabs[0]:
    st.markdown("""
        <h1 style='text-align:center; color:#2b7a78;'>🧹 Visualizador de Limpieza</h1>
        <p style='text-align:center; color:#3a506b; font-size:1.2em;'>
            Lleva el control visual y motivador de tus limpiezas. ¡Sube fotos de antes y después y observa cómo cambia la saturación visual del espacio!
        </p>
    """, unsafe_allow_html=True)

    st.divider()

    if not last or not last.get("session_active"):
        st.info("No hay sesión activa. ¡Inicia una nueva sesión para comenzar!")
        latest = collection.find_one({"session_active": False}, sort=[("end_time", -1)])
        if latest:
            ts = latest["start_time"].astimezone(CO).strftime("%Y-%m-%d %H:%M")
            dur = latest.get("duration_seconds", 0)
            st.markdown(f"**⏳ Última sesión:** `{ts}` &nbsp; | &nbsp; **Duración:** `{format_seconds(dur)}` &nbsp; | &nbsp; {'✅ Bajó la saturación visual' if latest.get('improved') else '❌ Sin cambio visible'}")
            col1, col2 = st.columns(2)
            with col1:
                st.image(base64_to_image(latest.get("image_base64", "")), caption="ANTES", width=250)
                st.markdown(f"Saturación visual: `{latest.get('edges', 0):,}`")
            with col2:
                st.image(base64_to_image(latest.get("image_after", "")), caption="DESPUÉS", width=250)
                st.markdown(f"Saturación visual: `{latest.get('edges_after', 0):,}`")
        st.divider()
        if st.button("🚀 Iniciar nueva sesión", use_container_width=True):
            st.session_state.clear()
            collection.update_many({"session_active": True}, {"$set": {"session_active": False}})
            meta.update_one(
                {},
                {"$set": {"last_session_start": datetime.now(timezone.utc)}},
                upsert=True
            )
            st.rerun()

    # === SESIÓN ACTIVA ===
    if last and last.get("session_active"):
        # Sincronizar estado local
        mongo_session_id = str(last["_id"])
        local_session_id = str(st.session_state.session_id) if st.session_state.session_id else None
        if mongo_session_id != local_session_id:
            st.session_state.img_before = base64_to_image(last.get("image_base64", ""))
            st.session_state.before_edges = last.get("edges", 0)
            st.session_state.start_time = last.get("start_time").astimezone(CO)
            st.session_state.ready = True
            st.session_state.session_id = last["_id"]
            st.session_state.img_after_uploaded = None

        if not st.session_state.img_before:
            st.subheader("📷 Sube tu imagen del ANTES")
            img_file = st.file_uploader("ANTES", type=["jpg", "jpeg", "png"], key="before")
            st.caption("Esta imagen servirá para comparar el resultado final. ¡Elige la mejor toma!")
            if img_file and st.button("🟢 Iniciar sesión", use_container_width=True):
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
            st.success("¡Sesión activa! Cuando termines, sube la foto del después para ver el cambio en la saturación visual 🎉")
            st.image(st.session_state.img_before, caption="ANTES", width=320)
            st.markdown(f"**Saturación visual antes:** `{st.session_state.before_edges:,}`")
            now = datetime.now(CO)
            if st.session_state.start_time:
                elapsed = now - st.session_state.start_time
                st.markdown(f"⏱️ <b>Tiempo activo:</b> <code>{format_seconds(int(elapsed.total_seconds()))}</code>", unsafe_allow_html=True)

            st.divider()

            st.subheader("📸 Sube la imagen del DESPUÉS")
            img_after_file = st.file_uploader("DESPUÉS", type=["jpg", "jpeg", "png"], key="after", label_visibility="visible")
            st.caption("¡Muestra el resultado alcanzado!")

            if img_after_file is not None:
                try:
                    if not st.session_state.session_id:
                        st.error("No hay sesión activa. No se puede guardar la imagen del después porque falta el session_id.")
                        st.stop()
                    img_after = Image.open(img_after_file)
                    resized_after = resize_image(img_after)
                    img_b64_after = image_to_base64(resized_after)
                    edges_after = simple_edge_score(resized_after)
                    result = collection.update_one(
                        {"_id": st.session_state.session_id},
                        {"$set": {
                            "image_after": img_b64_after,
                            "edges_after": edges_after
                        }}
                    )
                    if result.modified_count == 1:
                        st.success(f"Imagen y saturación visual guardadas correctamente ({edges_after:,}).")
                    else:
                        st.error("No se encontró la sesión activa en Mongo para actualizar. Verifica el session_id y que la sesión está iniciada correctamente.")
                except Exception as e:
                    import traceback
                    st.error(f"Error al procesar o guardar la imagen: {e}")
                    print(traceback.format_exc())

            img_after_b64 = last.get("image_after")
            edges_after_val = last.get("edges_after")
            if img_after_b64:
                try:
                    st.image(base64_to_image(img_after_b64), caption="DESPUÉS (guardada)", width=320)
                except Exception as e:
                    st.warning(f"Error mostrando la imagen del después: {e}")
                if edges_after_val is not None:
                    st.markdown(f"**Saturación visual después:** `{edges_after_val:,}`")
                if st.button("✅ Finalizar y comparar", use_container_width=True):
                    img_after = base64_to_image(img_after_b64)
                    resized_after = resize_image(img_after)
                    edges_after = last.get("edges_after", simple_edge_score(resized_after))
                    improved = edges_after < st.session_state.before_edges * 0.9
                    end_time = datetime.now(timezone.utc)
                    duration = int((end_time - st.session_state.start_time.replace(tzinfo=None)).total_seconds())

                    collection.update_one(
                        {"_id": st.session_state.session_id},
                        {"$set": {
                            "session_active": False,
                            "end_time": end_time,
                            "improved": improved,
                            "duration_seconds": duration,
                        }}
                    )
                    st.balloons()
                    st.success("¡Sesión registrada exitosamente! 🎊")
                    st.session_state.img_before = None
                    st.session_state.ready = False
                    st.session_state.start_time = None
                    st.session_state.before_edges = 0
                    st.rerun()
            else:
                st.info("Sube una imagen del después para poder finalizar tu sesión.")

with tabs[1]:
    st.markdown("""
        <h2 style='color:#2b7a78;'>🗂️ Historial de Sesiones</h2>
        <p style='color:#3a506b;'>Aquí puedes ver las sesiones anteriores y tu progreso acumulado.</p>
    """, unsafe_allow_html=True)
    registros = list(collection.find({"session_active": False}).sort("start_time", -1).limit(10))
    for r in registros:
        ts = r["start_time"].astimezone(CO).strftime("%Y-%m-%d %H:%M:%S")
        dur = r.get("duration_seconds", 0)
        st.markdown(f"🗓️ `{ts}` — ⏱️ `{format_seconds(dur)}` — {'✅ Bajó la saturación visual' if r.get('improved') else '❌ Sin cambio visible'}")
        col1, col2 = st.columns(2)
        with col1:
            st.image(base64_to_image(r.get("image_base64", "")), caption="ANTES", width=200)
            st.markdown(f"Saturación visual: `{r.get('edges', 0):,}`")
        with col2:
            st.image(base64_to_image(r.get("image_after", "")), caption="DESPUÉS", width=200)
            st.markdown(f"Saturación visual: `{r.get('edges_after', 0):,}`")
        st.divider()

    with st.expander("🧨 Borrar todos los registros"):
        st.warning("¡Esta acción eliminará todo el historial! No se puede deshacer.")
        if st.button("🗑️ Borrar todo", use_container_width=True):
            collection.delete_many({})
            meta.update_one({}, {"$set": {"last_reset": datetime.now(timezone.utc)}}, upsert=True)
            st.success("Registros eliminados.")
            st.rerun()
