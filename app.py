import streamlit as st
import pymongo
from PIL import Image
import io, base64
from datetime import datetime, timezone, timedelta
import pytz
import time
from streamlit_autorefresh import st_autorefresh
import getpass
from bson import ObjectId

# === CONFIG ===
st.set_page_config(page_title="🧹 Visualizador de Limpieza", layout="centered")
MONGO_URI = st.secrets["mongo_uri"]
client = pymongo.MongoClient(MONGO_URI)
db = client.cleanup
collection = db.entries
meta = db.meta
CO = pytz.timezone("America/Bogota")

def resize_image(img, max_width=300):
    img = img.convert("RGB")
    w, h = img.size
    if w > max_width:
        ratio = max_width / w
        img = img.resize((int(w * ratio), int(h * ratio)))
    return img

def image_to_base64(img):
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=40, optimize=True)
    return base64.b64encode(buffer.getvalue()).decode()

def base64_to_image(b64_str):
    try:
        img = Image.open(io.BytesIO(base64.b64decode(b64_str)))
        return img.convert("RGB")
    except Exception:
        return Image.new("RGB", (300, 200), color="gray")

def simple_edge_score(img):
    grayscale = img.convert("L")
    pixels = list(grayscale.getdata())
    diffs = [abs(pixels[i] - pixels[i+1]) for i in range(len(pixels)-1)]
    return sum(d > 10 for d in diffs)

def format_seconds(seconds):
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02}:{m:02}:{s:02}"

if "user_login" not in st.session_state:
    st.session_state.user_login = (
        st.experimental_user.get("username") if hasattr(st, "experimental_user") else getpass.getuser()
    )

# === SYNC ===
meta_doc = meta.find_one({}) or {}
last = collection.find_one(sort=[("start_time", -1)])

tabs = st.tabs(["✨ Sesión Actual", "🗂️ Historial"])

with tabs[0]:
    st.markdown("<h1 style='text-align:center; color:#2b7a78;'>🧹 Visualizador de Limpieza</h1>", unsafe_allow_html=True)
    st.divider()

    # INICIO: NO ACTIVA
    if not last or not last.get("session_active"):
        st.info("No hay sesión activa. Sube una foto de ANTES para iniciar.")
        img_file = st.file_uploader("ANTES", type=["jpg", "jpeg", "png"], key="before_new")
        if img_file:
            img = Image.open(img_file)
            resized = resize_image(img)
            img_b64 = image_to_base64(resized)
            edges = simple_edge_score(resized)
            now_utc = datetime.now(timezone.utc)
            collection.insert_one({
                "session_active": True,
                "start_time": now_utc,
                "image_base64": img_b64,
                "edges": edges,
            })
            meta.update_one(
                {}, {"$set": {
                    "last_session_start": now_utc,
                    "ultimo_pellizco": {
                        "user": st.session_state.user_login,
                        "datetime": now_utc,
                        "mensaje": "Se subió el ANTES"
                    }
                }}, upsert=True
            )
            st.success("¡Sesión iniciada! Cuando termines, detén el cronómetro.")
            st.rerun()
        st.stop()

    # SESIÓN ACTIVA - CRONÓMETRO EN VIVO
    session_id = last["_id"]
    img_before = base64_to_image(last.get("image_base64", ""))
    before_edges = last.get("edges", 0)
    start_time = last.get("start_time").astimezone(CO)
    st.success("Sesión activa. Cuando termines, detén el cronómetro.")
    st.image(img_before, caption="ANTES", width=320)
    st.markdown(f"**Saturación visual antes:** `{before_edges:,}`")

    cronometro = st.empty()
    stop_button = st.button("⏹️ Detener cronómetro / Finalizar sesión", type="primary", use_container_width=True)

    # Loop de cronómetro "real", consulta el estado en la base cada ciclo
    while True:
        doc = collection.find_one({"_id": session_id})
        if not doc or not doc.get("session_active", False):
            st.success("¡Sesión finalizada desde otro dispositivo o ventana!")
            st.rerun()
            break
        start_time = doc["start_time"].astimezone(CO)
        elapsed = (datetime.now(CO) - start_time).total_seconds()
        cronometro.markdown(f"⏱️ <b>Tiempo activo:</b> <code>{format_seconds(int(elapsed))}</code>", unsafe_allow_html=True)
        time.sleep(1)
        if stop_button:
            end_time = datetime.now(timezone.utc)
            duration = int((end_time - doc["start_time"].replace(tzinfo=None)).total_seconds())
            result = collection.update_one(
                {"_id": doc["_id"], "session_active": True},
                {"$set": {
                    "session_active": False,
                    "end_time": end_time,
                    "duration_seconds": duration,
                    "improved": None
                }}
            )
            meta.update_one(
                {}, {"$set": {
                    "ultimo_pellizco": {
                        "user": st.session_state.user_login,
                        "datetime": end_time,
                        "mensaje": "Sesión finalizada, esperando DESPUÉS"
                    }
                }}, upsert=True
            )
            nuevo = collection.find_one({"_id": doc["_id"]})
            if result.modified_count == 1 and nuevo.get("session_active") is False:
                st.success("¡Sesión finalizada! Ahora sube la foto del después cuando quieras.")
                st.rerun()
            else:
                st.error(f"No se pudo finalizar la sesión. session_active en la base: {nuevo.get('session_active')}. session_id: {doc['_id']}")
                st.stop()
            break

    # SUBIDA DEL DESPUÉS
    last = collection.find_one(sort=[("start_time", -1)])
    if last and not last.get("session_active") and last.get("image_after", None) is None:
        st.warning("Sesión finalizada. Sube la foto del DESPUÉS para completar el registro.")
        st.image(base64_to_image(last.get("image_base64", "")), caption="ANTES (guardado)", width=320)
        img_after_file = st.file_uploader("DESPUÉS", type=["jpg", "jpeg", "png"], key="after", label_visibility="visible")
        if img_after_file is not None:
            with st.spinner("Guardando foto del después..."):
                try:
                    img_after = Image.open(img_after_file)
                    resized_after = resize_image(img_after)
                    img_b64_after = image_to_base64(resized_after)
                    edges_after = simple_edge_score(resized_after)
                    improved = False
                    edges_before = last.get("edges", 0)
                    if edges_before:
                        improved = edges_after < edges_before * 0.9
                    collection.update_one(
                        {"_id": last["_id"]},
                        {"$set": {
                            "image_after": img_b64_after,
                            "edges_after": edges_after,
                            "improved": improved
                        }}
                    )
                    meta.update_one(
                        {}, {"$set": {
                            "ultimo_pellizco": {
                                "user": st.session_state.user_login,
                                "datetime": datetime.now(timezone.utc),
                                "mensaje": "Se subió el DESPUÉS"
                            }
                        }}, upsert=True
                    )
                    st.success("¡Foto del después registrada exitosamente!")
                    st.rerun()
                except Exception as e:
                    import traceback
                    st.error(f"Error al guardar la foto del después: {e}")
                    st.text(traceback.format_exc())
        st.info("Cuando subas la foto del después, se completará la sesión en el historial.")

    elif last and not last.get("session_active") and last.get("image_after", None) is not None:
        st.success("Sesión completada. Puedes ver el resultado en el historial.")

with tabs[1]:
    st.markdown("<h2 style='color:#2b7a78;'>🗂️ Historial de Sesiones</h2>", unsafe_allow_html=True)
    registros = list(collection.find({"session_active": False}).sort("start_time", -1).limit(10))
    for r in registros:
        ts = r["start_time"].astimezone(CO).strftime("%Y-%m-%d %H:%M:%S")
        ts_end = r.get("end_time")
        if isinstance(ts_end, datetime):
            ts_end = ts_end.astimezone(CO).strftime("%Y-%m-%d %H:%M:%S")
        else:
            ts_end = "—"
        dur = r.get("duration_seconds", 0)
        edges_before = r.get('edges', 0)
        edges_after = r.get('edges_after', 0)
        diff = edges_before - edges_after
        mejora = ""
        if diff > 0:
            mejora = f"⬇️ <span style='color:#16a34a;'>-{diff:,}</span>"
        elif diff < 0:
            mejora = f"⬆️ <span style='color:#dc2626;'>+{abs(diff):,}</span>"
        else:
            mejora = f"= 0"
        st.markdown(
            f"🗓️ <b>Inicio:</b> `{ts}` &nbsp; <b>Fin:</b> `{ts_end}` — ⏱️ `{format_seconds(dur)}` — "
            f"{'✅ Bajó la saturación visual' if r.get('improved') else '❌ Sin cambio visible'}",
            unsafe_allow_html=True
        )
        col1, col2 = st.columns(2, gap="large")
        with col1:
            st.image(base64_to_image(r.get("image_base64", "")), caption="ANTES", width=280)
            st.markdown(f"Saturación: <code>{edges_before:,}</code>", unsafe_allow_html=True)
        with col2:
            st.image(base64_to_image(r.get("image_after", "")), caption="DESPUÉS", width=280)
            st.markdown(f"Saturación: <code>{edges_after:,}</code>", unsafe_allow_html=True)
        st.markdown(f"<h4 style='text-align:center;'>Diferencia: {mejora}</h4>", unsafe_allow_html=True)
        st.markdown("---")

    with st.expander("🧨 Borrar todos los registros"):
        st.warning("¡Esta acción eliminará todo el historial! No se puede deshacer.")
        if st.button("🗑️ Borrar todo", use_container_width=True):
            now_utc = datetime.now(timezone.utc)
            collection.delete_many({})
            meta.update_one({}, {"$set": {"last_reset": now_utc}}, upsert=True)
            st.success("Registros eliminados.")
            st.rerun()
