import streamlit as st
from PIL import Image, ImageFilter
import numpy as np
from datetime import datetime
from pymongo import MongoClient

# --- CONFIGURATION ---
MONGO_URI = st.secrets["mongo_uri"]
client = MongoClient(MONGO_URI)
db = client["visual_cleanup"]
collection = db["records"]

# --- EDGE DETECTION WITHOUT OPENCV ---
def count_edges(img: Image.Image) -> int:
    gray = img.convert("L")  # Grayscale
    edges = gray.filter(ImageFilter.FIND_EDGES)
    edge_array = np.array(edges)
    count = np.sum(edge_array > 50)  # Basic threshold
    return count

# --- STREAMLIT UI ---
st.set_page_config("Visual Cleanup", layout="centered")
st.title("🧹 Visual Cleanup")

st.markdown("Upload a **BEFORE** and **AFTER** image to evaluate changes and log your effort.")

col1, col2 = st.columns(2)

with col1:
    before_file = st.file_uploader("BEFORE Photo", type=["jpg", "png", "jpeg"], key="before")
with col2:
    after_file = st.file_uploader("AFTER Photo", type=["jpg", "png", "jpeg"], key="after")

if before_file and after_file:
    img_before = Image.open(before_file)
    img_after = Image.open(after_file)

    edges_before = count_edges(img_before)
    edges_after = count_edges(img_after)

    st.subheader("Result")
    improved = edges_after < edges_before
    st.write(f"Edge pixels (BEFORE): {edges_before:,}")
    st.write(f"Edge pixels (AFTER): {edges_after:,}")

    if improved:
        duration = st.number_input("How many minutes did it take?", min_value=1, max_value=240, step=1)
        if st.button("Save record"):
            collection.insert_one({
                "timestamp": datetime.now(),
                "edges_before": int(edges_before),
                "edges_after": int(edges_after),
                "improved": True,
                "minutes": duration
            })
            st.success("✅ Record saved to MongoDB")
    else:
        st.warning("No visual improvement detected. Try again or check your photos.")

    st.image([img_before, img_after], caption=["BEFORE", "AFTER"], width=300)

# History display
st.divider()
st.subheader("📜 Action History")
records = list(collection.find().sort("timestamp", -1).limit(10))
if records:
    for r in records:
        st.write(f"🕒 {r['timestamp'].strftime('%Y-%m-%d %H:%M:%S')} — {r['minutes']} min — Improved: {'✅' if r['improved'] else '❌'}")
else:
    st.info("No records yet.")
