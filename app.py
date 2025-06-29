import streamlit as st
from PIL import Image
import io, base64
import pymongo
from datetime import datetime
import pytz
from streamlit_autorefresh import st_autorefresh

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

# === INTERFAZ ===
st.set_page_config(page_title="🧹 Cleanup App", layout="centered")
tab1, tab2 = st.tabs(["🧹 Sesion Actual", "📜 Historial"])

# === TAB 1 ===
with tab1:
    st.title("🧹 Cleanup Visual Tracker")

    last = collection.find_one({"session_active": True}, sort=[("start_time", -1)])

    if last:
        st_autorefresh(interval=1000, key="refresh_crono")

        try:
            start_time = last["start_time"].replace(tzinfo=pytz.utc).astimezone(zona_col)
            image_before = base64_to_image(last["image_base64"])
            edges_before = last["edges"]
            session_id = last["_id"]

            st.subheader("🖼️ Imagen ANTES")
            st.image(image_before, width=300)
            st.markdown(f"**Edges ANTES:** `{edges_before}`")

            now = datetime.now(zona_col)
            elapsed = now - start_time
            m, s = divmod(elapsed.total_seconds(), 60)
            st.markdown(f"### ⏱️ Tiempo activo: **{int(m)} min {int(s)} sec**")

            if "image_after" in last:
                image_after = base64_to_image(last["image_after"])
                edges_after = last.get("edges_after", "?")
                duration = last.get("duration_seconds", 0)
                improved = last.get("improved", False)
                fecha = last.get("start_time").astimezone(zona_col).strftime("%Y-%m-%d %H:%M")

                st.subheader("🖼️ Imagen DESPUÉS")
                st.image(image_after, width=300)
                st.markdown(f"**Edges DESPUÉS:** `{edges_after}`")

                st.markdown("### ✅ Resultado de comparación:")
                st.markdown(f"**Duración total:** `{duration} segundos`")
                if improved:
                    st.success("✅ Hubo mejora: la segunda imagen tiene menos bordes.")
                else:
                    st.warning("❌ No hubo mejora: los bordes no disminuyeron.")

                if st.button("🔁 Iniciar nueva sesión"):
                    collection.update_one({"_id": session_id}, {"$set": {"session_active": False}})
                    st.rerun()

            else:
                st.subheader("📸 Imagen DESPUÉS")
                img_file_after = st.file_uploader("Después", type=["jpg", "jpeg", "png"], key="after")
                if img_file_after:
                    try:
                        img = Image.open(img_file_after)
                        resized = resize_image(img)
                        score = simple_edge_score(resized)
                        img_b64 = image_to_base64(resized)
                        duration = int((datetime.now(zona_col) - start_time).total_seconds())
                        improved = score < edges_before

                        collection.update_one(
                            {"_id": session_id},
                            {"$set": {
                                "session_active": False,
                                "end_time": datetime.now(zona_col),
                                "duration_seconds": duration,
                                "image_after": img_b64,
                                "edges_after": score,
                                "improved": improved
                            }}
                        )

                        st.success("✅ Imagen después guardada y sesión cerrada.")
                        st.rerun()

                    except Exception as e:
                        st.error(f"❌ Error procesando imagen después: {e}")

        except Exception as e:
            st.error(f"❌ Error cargando sesión activa: {e}")

    else:
        last_closed = collection.find_one(
            {"session_active": False, "image_after": {"$exists": True}},
            sort=[("end_time", -1)]
        )

        if last_closed:
            st.markdown("### ⚠️ No hay sesión activa. Última sesión completada:")
            try:
                image_before = base64_to_image(last_closed["image_base64"])
                image_after = base64_to_image(last_closed["image_after"])
                edges_before = last_closed.get("edges", "?")
                edges_after = last_closed.get("edges_after", "?")
                improved = last_closed.get("improved", False)
                duration = last_closed.get("duration_seconds", 0)
                fecha = last_closed.get("start_time").astimezone(zona_col).strftime("%Y-%m-%d %H:%M")

                st.markdown(f"#### 🗓️ {fecha} — ⏱️ {duration} seg — {'✅ Mejora' if improved else '❌ Sin mejora'}")
                col1, col2 = st.columns(2)
                with col1:
                    st.image(image_before, caption="ANTES", width=250)
                    st.markdown(f"**Edges:** {edges_before}")
                with col2:
                    st.image(image_after, caption="DESPUÉS", width=250)
                    st.markdown(f"**Edges:** {edges_after}")

            except Exception as e:
                st.error(f"❌ Error mostrando la última sesión cerrada: {e}")

            if st.button("🔁 Iniciar nueva sesión"):
                st.rerun()

        else:
            st.subheader("📤 Subí tu imagen inicial (ANTES)")
            img_file = st.file_uploader("Antes", type=["jpg", "jpeg", "png"])
            if img_file:
                try:
                    img = Image.open(img_file)
                    resized = resize_image(img)
                    score = simple_edge_score(resized)
                    img_b64 = image_to_base64(resized)
                    ts = datetime.now(zona_col)

                    collection.insert_one({
                        "session_active": True,
                        "start_time": ts,
                        "image_base64": img_b64,
                        "edges": score
                    })

                    st.success("✅ Imagen inicial cargada. Cronómetro iniciado.")
                    st.rerun()

                except Exception as e:
                    st.error(f"❌ Error procesando imagen inicial: {e}")

# === TAB 2: HISTORIAL ===
with tab2:
    st.title("📜 Historial de sesiones")

    records = list(collection.find({"session_active": False, "image_after": {"$exists": True}})
                   .sort("start_time", -1).limit(10))

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
                st.image(base64_to_image(r["image_after"]), caption="DESPUÉS", width=250)
                st.markdown(f"**Edges:** {edges_after}")

    # === Herramienta de desarrollo ===
    with st.expander("🧨 Herramientas de desarrollo"):
        if st.button("🗑️ Borrar todos los registros (MongoDB)"):
            collection.delete_many({})
            st.success("✅ Todos los registros han sido eliminados.")
            st.rerun()
