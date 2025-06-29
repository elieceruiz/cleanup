import streamlit as st
import pymongo
from PIL import Image
import io, base64
from datetime import datetime, timedelta
import pytz

st.set_page_config(page_title="🧹 Visual Cleanup", layout="centered")

MONGO_URI = st.secrets["mongo_uri"]
client = pymongo.MongoClient(MONGO_URI)
db = client.cleanup
db_collection = db.entries

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
    img.save(buffer, format="JPEG", quality=50, optimize=True)
    return base64.b64encode(buffer.getvalue()).decode()

def base64_to_image(b64_str: str) -> Image.Image:
    return Image.open(io.BytesIO(base64.b64decode(b64_str)))

def simple_edge_score(img: Image.Image) -> int:
    grayscale = img.convert("L")
    pixels = list(grayscale.getdata())
    diffs = [abs(pixels[i] - pixels[i+1]) for i in range(len(pixels)-1)]
    return sum(d > 10 for d in diffs)

# === FRONT ===
st.title("🧹 Visual Cleanup")

if "start_time" not in st.session_state:
    st.session_state.start_time = None

if "img_before" not in st.session_state:
    st.session_state.img_before = None

if "before_edges" not in st.session_state:
    st.session_state.before_edges = 0

if "ready" not in st.session_state:
    st.session_state.ready = False

# === PHOTO BEFORE ===
if not st.session_state.img_before:
    st.subheader("Upload BEFORE photo")
    img_file_before = st.file_uploader("Before", type=["jpg", "jpeg", "png"], key="before")
    if img_file_before:
        st.session_state.img_before = Image.open(img_file_before)
        st.session_state.start_time = datetime.now()
        resized = resize_image(st.session_state.img_before)
        st.session_state.before_edges = simple_edge_score(resized)
        st.session_state.ready = True
        st.rerun()

# === IF BEFORE EXISTS ===
if st.session_state.ready and st.session_state.img_before:
    st.image(st.session_state.img_before, caption="BEFORE", width=300)
    st.markdown(f"**Edges:** {st.session_state.before_edges:,}")

    delta = datetime.now() - st.session_state.start_time
    minutes, seconds = divmod(delta.total_seconds(), 60)
    st.markdown(f"⏱️ Time running: **{int(minutes)} min {int(seconds)} sec**")

    st.subheader("Upload AFTER photo")
    img_file_after = st.file_uploader("After", type=["jpg", "jpeg", "png"], key="after")

    if img_file_after:
        img_after = Image.open(img_file_after)
        resized_after = resize_image(img_after)
        after_edges = simple_edge_score(resized_after)

        duration = int((datetime.now() - st.session_state.start_time).total_seconds())
        improved = after_edges < (st.session_state.before_edges * 0.9)

        img_b64_before = image_to_base64(resize_image(st.session_state.img_before))
        img_b64_after = image_to_base64(resized_after)

        if len(img_b64_before) + len(img_b64_after) > 12_000_000:
            st.warning("⚠️ Images too large to store. Try using lower resolution.")
        else:
            try:
                db_collection.insert_one({
                    "timestamp": datetime.now(tz=CO),
                    "duration_seconds": duration,
                    "improved": improved,
                    "image_before": img_b64_before,
                    "image_after": img_b64_after,
                    "edges_before": st.session_state.before_edges,
                    "edges_after": after_edges,
                })
                st.success("✅ Action recorded!")
                st.write("📝 Entry successfully saved to MongoDB.")
            except Exception as e:
                st.error(f"❌ Failed to save entry: {e}")
                st.stop()

        # Reset session state BEFORE rerun
        st.session_state.start_time = None
        st.session_state.img_before = None
        st.session_state.before_edges = 0
        st.session_state.ready = False
        st.session_state["after"] = None
        st.rerun()

# === HISTORY ===
st.subheader("📜 Action History")

week_ago = datetime.now(tz=CO) - timedelta(days=7)
this_week_count = db_collection.count_documents({"timestamp": {"$gte": week_ago}})
st.markdown(f"**✅ Sessions this week: {this_week_count}**")

records = list(db_collection.find().sort("timestamp", -1).limit(10))

if not records:
    st.info("No entries yet.")
else:
    if "page" not in st.session_state:
        st.session_state.page = 0

    start = st.session_state.page * 1
    end = start + 1

    for r in records[start:end]:
        ts = r["timestamp"].astimezone(CO).strftime("%Y-%m-%d %H:%M:%S")
        dur_m = r["duration_seconds"] // 60
        st.write(f"🕒 {ts} — {dur_m} min — Improved: {'✅' if r['improved'] else '❌'}")

        col1, col2 = st.columns(2)
        with col1:
            st.image(base64_to_image(r["image_before"]), caption="BEFORE", width=200)
            st.markdown(f"**Edges:** {r['edges_before']:,}")
        with col2:
            st.image(base64_to_image(r["image_after"]), caption="AFTER", width=200)
            st.markdown(f"**Edges:** {r['edges_after']:,}")

    col_prev, col_next = st.columns([1, 1])
    prev_clicked = col_prev.button("⬅️ Previous")
    next_clicked = col_next.button("Next ➡️")

    if prev_clicked and st.session_state.page > 0:
        st.session_state.page -= 1
        st.rerun()
    elif next_clicked and end < len(records):
        st.session_state.page += 1
        st.rerun()
