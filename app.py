import streamlit as st
from PIL import Image, ImageFilter
import numpy as np
from datetime import datetime, timedelta
from pymongo import MongoClient
from pytz import timezone
import time
import base64
import io
from streamlit_autorefresh import st_autorefresh

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

# --- RESIZE IMAGE ---
def resize_image(img: Image.Image, max_width=400) -> Image.Image:
    w, h = img.size
    if w > max_width:
        ratio = max_width / w
        return img.resize((int(w * ratio), int(h * ratio)))
    return img

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
if "img_after" not in st.session_state:
    st.session_state.img_after = None
if "history_offset" not in st.session_state:
    st.session_state.history_offset = 0

# --- AUTOREFRESH TIMER IF RUNNING AND NO AFTER PHOTO YET ---
if st.session_state.start_time and st.session_state.img_after is None:
    st_autorefresh(interval=1000, key="refresh")

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

    if st.session_state.img_after is None:
        after_file = st.file_uploader("Now upload your AFTER photo", type=["jpg", "png", "jpeg"], key="after")
        if after_file:
            st.session_state.img_after = Image.open(after_file)
            st.rerun()

    elif st.session_state.img_after is not None:
        after_edges = count_edges(st.session_state.img_after)

        st.subheader("🔍 Analysis Result")
        st.write(f"Edge pixels BEFORE: {st.session_state.before_edges:,}")
        st.write(f"Edge pixels AFTER: {after_edges:,}")

        improved = after_edges < (st.session_state.before_edges * 0.9)

        if improved:
            st.success("🎉 Well done! You were proactive and reduced visual clutter.")
        else:
            st.warning("No significant visual improvement detected. Try again.")

        # Resize images before saving
        resized_before = resize_image(st.session_state.img_before)
        resized_after = resize_image(st.session_state.img_after)

        # Save to MongoDB
        collection.insert_one({
            "timestamp": datetime.now(CO),
            "edges_before": st.session_state.before_edges,
            "edges_after": after_edges,
            "improved": improved,
            "duration_seconds": elapsed,
            "image_before": image_to_base64(resized_before),
            "image_after": image_to_base64(resized_after)
        })

        st.balloons()
        st.success("✅ Your cleanup session was saved.")

        # Clear session state
        st.session_state.start_time = None
        st.session_state.before_edges = None
        st.session_state.img_before = None
        st.session_state.img_after = None
        st.rerun()

# --- HISTORY ---
st.divider()
st.subheader("📜 Action History")

# Count sessions this week
start_of_week = datetime.now(CO) - timedelta(days=datetime.now(CO).weekday())
weekly_count = collection.count_documents({"timestamp": {"$gte": start_of_week}})
st.info(f"🧮 You have completed {weekly_count} cleanup sessions this week.")

# Paginate history
limit = 5
skip = st.session_state.history_offset
records = list(collection.find().sort("timestamp", -1).skip(skip).limit(limit))

if records:
    for r in records:
        duration_m = r["duration_seconds"] // 60
        st.write(f"🕒 {r['timestamp'].astimezone(CO).strftime('%Y-%m-%d %H:%M:%S')} — {duration_m} min — Improved: {'✅' if r['improved'] else '❌'}")
        col1, col2 = st.columns(2)
        with col1:
            st.image(base64_to_image(r["image_before"]), caption=f"BEFORE\n{r['edges_before']:,} edges", width=200)
        with col2:
            st.image(base64_to_image(r["image_after"]), caption=f"AFTER\n{r['edges_after']:,} edges", width=200)

    col_prev, col_next = st.columns(2)
    with col_prev:
        if st.session_state.history_offset >= limit:
            if st.button("⬅️ Previous"):
                st.session_state.history_offset -= limit
                st.rerun()
    with col_next:
        if collection.count_documents({}) > skip + limit:
            if st.button("Next ➡️"):
                st.session_state.history_offset += limit
                st.rerun()
else:
    st.info("No records yet.")
