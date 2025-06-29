import streamlit as st
import pymongo
from datetime import datetime, timezone

# --- Configuración MongoDB ---
MONGO_URI = st.secrets["mongo_uri"]
client = pymongo.MongoClient(MONGO_URI)
db = client.cleanup
meta = db.meta

# --- Bloque de sincronización global (¡esto va al inicio!) ---
if "ultimo_pellizco_global" not in st.session_state:
    st.session_state.ultimo_pellizco_global = None

meta_doc = meta.find_one({}) or {}
nuevo_pellizco = meta_doc.get("ultimo_pellizco_global", {})

# Mostrar los valores actuales para debug
st.info(f"🧭 Meta global en memoria: {st.session_state.ultimo_pellizco_global}")
st.info(f"🧭 Meta global en base: {nuevo_pellizco}")

# Si detecta cambio, forzar recarga
if nuevo_pellizco != st.session_state.ultimo_pellizco_global:
    st.session_state.ultimo_pellizco_global = nuevo_pellizco
    st.rerun()

# --- Interfaz para actualizar el meta global ---
st.header("Sincronización Global - Demo")
user = st.text_input("Usuario", value=st.session_state.get("user_login", "elieceruiz"))
mensaje = st.text_input("Mensaje para meta global", value="Prueba de sincronía")

if st.button("Actualizar meta global"):
    meta.update_one(
        {},
        {"$set": {
            "ultimo_pellizco_global": {
                "user": user,
                "datetime": datetime.now(timezone.utc),
                "mensaje": mensaje
            }
        }},
        upsert=True
    )
    st.success("¡Meta global actualizada!")

# Mostrar el último valor guardado
if nuevo_pellizco:
    st.write("Último pellizco global:", nuevo_pellizco)
