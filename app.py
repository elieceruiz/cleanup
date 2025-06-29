import streamlit as st
from PIL import Image, ImageFilter
import numpy as np
from datetime import datetime
from pymongo import MongoClient
from pytz import timezone
import time
import base64
import io

# --- CONFIGURATION ---
MONGO_URI = st.secrets["mongo_uri"]
client = MongoClient(MONGO_URI)
db = client["visual_cleanup"]
collection = db["records"]
CO = timezone("America/Bogota")

# --- EDGE DETECTION ---
def count_edges(img: Image.Image) -> int:
    gray = img.convert("L")
    edges = gray.filter(ImageFilter.FIND_EDGES)
    edge_array = np.array(edges)
    return int(np.sum(edge_array > 50))

# --- IMAGE TO BASE64 ---
def image_to_base64(img: Image.Image) -> str:
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode()

# --- BASE64 TO IMAGE ---
def base64_to_image(b64_str: str) -> Image.Image:
    return Image.open(io.BytesIO(base64.b64decode(b64_str)))

# --- UI CONFIG ---
st.set_page_config("Visual Cleanup", layout="centered")
st.title("🧹 Visual Cleanup")

# --- SESSION INITIALIZATION ---
if "start_time" not in st.session_state:
    st.session_state.start_time = None
if "before_edges" not in st.session_state:
    st.session_state.before_edges = None
if "img_before" not in st.session_state:
    st.session_state.img_before = None

# --- STEP 1: Upload BEFORE photo ---
if st.session_state.start_time is None:
    before_file = st.file_uploader("Upload your BEFORE photo", type=["jpg", "png", "jpeg"])
    if before_file:
        img_before = Image.open(before_file)
        st.session_state.img_before = img_before
        st.session_state.before_edges = count_edges(img_before)
        st.session_state.start_time = datetime.now(CO)
        st.success("📸 BEFORE photo uploaded. Timer started. Now tidy up!")
        st.image(img_before, caption="BEFORE", width=300)
        st.rerun()

# --- STEP 2: While timer is running ---
elapsed = None
if st.session_state.start_time:
    elapsed = (datetime.now(CO) - st.session_state.start_time).seconds
    minutes = elapsed // 60
    seconds = elapsed % 60
    st.info(f"⏱️ Time running: {minutes} min {seconds} sec")
    st.image(st.session_state.img_before, caption="BEFORE", width=300)
    after_file = st.file_uploader("Now upload your AFTER photo", type=["jpg", "png", "jpeg"], key="after")

    if after_file:
        img_after = Image.open(after_file)
        after_edges = count_edges(img_after)

        st.subheader("🔍 Analysis Result")
        st.write(f"Edge pixels BEFORE: {st.session_state.before_edges:,}")
        st.write(f"Edge pixels AFTER: {after_edges:,}")

        improved = after_edges < st.session_state.before_edges

        if improved:
            st.success("🎉 Well done! You were proactive and reduced visual clutter.")
        else:
            st.warning("No significant visual improvement detected. Try again.")

        # Save to MongoDB
        collection.insert_one({
            "timestamp": datetime.now(CO),
            "edges_before": st.session_state.before_edges,
            "edges_after": after_edges,
            "improved": improved,
            "duration_seconds": elapsed,
            "image_before": image_to_base64(st.session_state.img_before),
            "image_after": image_to_base64(img_after)
        })

        st.balloons()
        st.success("✅ Your cleanup session was saved.")

        st.session_state.start_time = None
        st.session_state.before_edges = None
        st.session_state.img_before = None
        st.rerun()

# --- HISTORY ---
st.divider()
st.subheader("📜 Action History")
records = list(collection.find().sort("timestamp", -1).limit(10))
if records:
    for r in records:
        duration_m = r["duration_seconds"] // 60
        st.write(f"🕒 {r['timestamp'].astimezone(CO).strftime('%Y-%m-%d %H:%M:%S')} — {duration_m} min — Improved: {'✅' if r['improved'] else '❌'}")
        col1, col2 = st.columns(2)
        with col1:
            st.image(base64_to_image(r["image_before"]), caption="BEFORE", width=200)
        with col2:
            st.image(base64_to_image(r["image_after"]), caption="AFTER", width=200)
else:
    st.info("No records yet.")
