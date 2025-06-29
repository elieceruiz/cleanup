import streamlit as st
import pymongo
from PIL import Image
import io, base64
from datetime import datetime, timezone
import pytz
from streamlit_autorefresh import st_autorefresh
import getpass

# === CONFIG ===
st.set_page_config(page_title="🧹 Visualizador de Limpieza", layout="centered")
MONGO_URI = st.secrets["mongo_uri"]
client = pymongo.MongoClient(MONGO_URI)
db = client.cleanup
collection = db.entries
meta = db.meta

CO = pytz.timezone("America/Bogota")

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
if "user_login" not in st.session_state:
    st.session_state.user_login = st.experimental_user.get("username") if hasattr(st, "experimental_user") else getpass.getuser()

# === SYNC META ===
meta_doc = meta.find_one({}) or {}
last_reset = meta_doc.get("last_reset", datetime(2000, 1, 1)).replace(tzinfo=timezone.utc)
last_session_start = meta_doc.get("last_session_start", datetime(2000, 1, 1)).replace(tzinfo=timezone.utc)
last = collection.find_one(sort=[("start_time", -1)])
historial = collection.count_documents({"session_active": False})

# Si se reseteó o arrancó otra sesión desde otro dispositivo, sincroniza
if (not last or not last.get("session_active")) and (
    last_reset > st.session_state.last_check or last_session_start > st.session_state.last_check
):
    st.session_state.last_check = datetime.now(timezone.utc)
    st.rerun()

tabs = st.tabs(["✨ Sesión Actual", "🗂️ Historial"])

# === AUTORREFRESH: sincronización solo si hay sesión activa ===
if last and last.get("session_active"):
    st_autorefresh(interval=1000, key="sincronizador_global")

with tabs[0]:
    st.markdown("""
        <h1 style='text-align:center; color:#2b7a78;'>🧹 Visualizador de Limpieza</h1>
        <p style='text-align:center; color:#3a506b; font-size:1.2em;'>
            Lleva el control visual de tus limpiezas. ¡Sube fotos de antes y después y observa cómo cambia la saturación visual!<br>
            <span style="font-size:0.95em; color:#5f6f8c;">(La app se sincroniza en todos los dispositivos en tiempo real)</span>
        </p>
    """, unsafe_allow_html=True)

    st.divider()

    # --- Si NO hay sesión activa, muestra solo el uploader de "ANTES" ---
    if not last or not last.get("session_active"):
        st.info("No hay sesión activa. Sube una foto de ANTES para iniciar.")
        img_file = st.file_uploader("ANTES", type=["jpg", "jpeg", "png"], key="before_new")
        st.caption("Esta imagen servirá para comparar el resultado final. ¡Elige la mejor toma!")
        if img_file:
            img = Image.open(img_file)
            resized = resize_image(img)
            img_b64 = image_to_base64(resized)
            edges = simple_edge_score(resized)
            result = collection.insert_one({
                "session_active": True,
                "start_time": datetime.now(timezone.utc),
                "image_base64": img_b64,
                "edges": edges,
            })
            # Registrar el "pellizco" en meta
            meta.update_one(
                {},
                {"$set": {
                    "last_session_start": datetime.now(timezone.utc),
                    "ultimo_pellizco": {
                        "user": st.session_state.user_login,
                        "datetime": datetime.now(timezone.utc),
                        "mensaje": "Se subió el ANTES"
                    }
                }},
                upsert=True
            )
            st.success("¡Sesión iniciada! Ahora sube la foto del después cuando termines.")
            st.rerun()
        st.stop()

    # --- Si SÍ hay sesión activa, muestra el flujo activo ---
    mongo_session_id = str(last["_id"])
    local_session_id = str(st.session_state.session_id) if st.session_state.session_id else None
    if mongo_session_id != local_session_id:
        st.session_state.img_before = base64_to_image(last.get("image_base64", ""))
        st.session_state.before_edges = last.get("edges", 0)
        st.session_state.start_time = last.get("start_time").astimezone(CO)
        st.session_state.ready = True
        st.session_state.session_id = last["_id"]
        st.session_state.img_after_uploaded = None

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
        img_after_b64 = last.get("image_after")
        if not img_after_b64:
            # Mostrar mensaje de sincronización si en otro dispositivo subieron el antes
            if last and last.get("session_active") and last.get("image_base64") and last.get("image_after") is None:
                st.info("Sesión activa. Si subiste la foto del ANTES desde otro dispositivo, puedes continuar aquí subiendo el DESPUÉS.")

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
                        # Registrar en meta que se subió el DESPUÉS
                        meta.update_one(
                            {},
                            {"$set": {
                                "ultimo_pellizco": {
                                    "user": st.session_state.user_login,
                                    "datetime": datetime.now(timezone.utc),
                                    "mensaje": "Se subió el DESPUÉS"
                                }
                            }},
                            upsert=True
                        )
                        st.balloons()
                        st.success("¡Sesión registrada exitosamente! 🎊")
                        st.session_state.img_before = None
                        st.session_state.ready = False
                        st.session_state.start_time = None
                        st.session_state.before_edges = 0
                        st.rerun()
                    else:
                        st.error("No se encontró la sesión activa en Mongo para actualizar. Verifica el session_id y que la sesión está iniciada correctamente.")
                except Exception as e:
                    import traceback
                    st.error(f"Error al procesar o guardar la imagen: {e}")
                    print(traceback.format_exc())
        else:
            try:
                st.image(base64_to_image(img_after_b64), caption="DESPUÉS (guardada)", width=320)
            except Exception as e:
                st.warning(f"Error mostrando la imagen del después: {e}")
            edges_after_val = last.get("edges_after")
            if edges_after_val is not None:
                st.markdown(f"**Saturación visual después:** `{edges_after_val:,}`")
        if not img_after_b64:
            st.info("Sube una imagen del después para poder finalizar tu sesión.")

with tabs[1]:
    st.markdown("""
        <h2 style='color:#2b7a78;'>🗂️ Historial de Sesiones</h2>
        <p style='color:#3a506b;'>Aquí puedes ver tus transformaciones anteriores, con el antes y el después lado a lado y la diferencia de saturación visual.</p>
    """, unsafe_allow_html=True)

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
        st.markdown(
            f"<h4 style='text-align:center;'>"
            f"Diferencia: {mejora}</h4>",
            unsafe_allow_html=True
        )
        st.markdown("---")

    with st.expander("🧨 Borrar todos los registros"):
        st.warning("¡Esta acción eliminará todo el historial! No se puede deshacer.")
        if st.button("🗑️ Borrar todo", use_container_width=True):
            collection.delete_many({})
            meta.update_one({}, {"$set": {"last_reset": datetime.now(timezone.utc)}}, upsert=True)
            st.success("Registros eliminados.")
            st.rerun()

    with st.expander("Meta de sincronización (debug)", expanded=False):
        meta_doc = meta.find_one({})
        st.write(meta_doc)
        if meta_doc and "ultimo_pellizco" in meta_doc:
            info_user = meta_doc["ultimo_pellizco"].get("user", "¿desconocido?")
            info_dt = meta_doc["ultimo_pellizco"].get("datetime")
            info_msg = meta_doc["ultimo_pellizco"].get("mensaje", "")
            st.info(
                f"Última acción meta: **{info_msg}** por **{info_user}** el `{info_dt}`"
            )
