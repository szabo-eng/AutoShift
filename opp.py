import streamlit as st
import pandas as pd
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime

# --- הגדרות דף ---
st.set_page_config(page_title="ניהול שיבוץ - תצוגה דחוסה", layout="wide")

# --- CSS לצמצום רווחים מקסימלי ---
st.markdown("""
    <style>
    /* יישור לימין וצמצום מרווחי גוף העמוד */
    [data-testid="stAppViewContainer"], [data-testid="stSidebar"], .main {
        direction: rtl;
        text-align: right;
    }
    
    /* צמצום רווחים בין אלמנטים של Streamlit */
    [data-testid="stVerticalBlock"] {
        gap: 0.1rem !important;
    }
    div.element-container {
        margin-bottom: -10px !important;
    }

    /* כותרת דביקה דקה */
    .sticky-header {
        position: -webkit-sticky;
        position: sticky;
        top: 2.85rem;
        background-color: #ffffff;
        z-index: 1000;
        padding: 4px 8px;
        border-bottom: 2px solid #1f77b4;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
        margin-bottom: 5px;
    }
    .sticky-header h5 { margin: 0; font-size: 0.85rem !important; font-weight: bold; color: #1f77b4; text-align: center;}
    .sticky-header p { margin: 0; font-size: 0.7rem !important; color: #666; text-align: center;}

    /* כרטיסי משמרות צפופים */
    .shift-card { 
        padding: 4px 8px; 
        border-radius: 4px; 
        border-right: 6px solid #ccc; 
        margin-bottom: 2px;
    }
    .type-atan { border-right-color: #FFA500; background-color: #FFF8EE; }
    .type-standard { border-right-color: #ADD8E6; background-color: #F0F8FF; }
    
    .shift-title { font-size: 0.8rem; font-weight: bold; line-height: 1.1; }
    .shift-station { font-size: 0.7rem; color: #444; }

    /* הקטנת כפתורים */
    .stButton > button {
        padding: 2px 10px !important;
        height: auto !important;
        font-size: 0.75rem !important;
        margin-top: 2px !important;
    }

    div[role="dialog"] { direction: rtl; text-align: right; }
    </style>
    """, unsafe_allow_html=True)

# --- חיבור Firebase ---
if not firebase_admin._apps:
    try:
        firebase_info = dict(st.secrets["firebase"])
        cred = credentials.Certificate(firebase_info)
        firebase_admin.initialize_app(cred)
    except:
        st.error("שגיאה בחיבור ל-Firebase.")
db = firestore.client()

# --- פונקציות עזר ---
DAYS_HEBREW = {'Sunday': 'ראשון', 'Monday': 'שני', 'Tuesday': 'שלישי', 'Wednesday': 'רביעי', 'Thursday': 'חמישי', 'Friday': 'שישי', 'Saturday': 'שבת'}
def get_day_name(date_str):
    try: return DAYS_HEBREW[datetime.strptime(date_str, '%d/%m/%Y').strftime('%A')]
    except: return ""

def get_shift_style(v_type):
    v_type = str(v_type)
    if "אט" in v_type: return "type-atan"
    if "תקן" in v_type: return "type-standard"
    return ""

def get_balance_from_db():
    scores = {}
    try:
        docs = db.collection('employee_history').stream()
        for doc in docs: scores[doc.id] = doc.to_dict().get('total_shifts', 0)
    except: pass
    return scores

def update_db_balance(schedule_dict):
    batch = db.batch()
    assigned = [n for n in schedule_dict.values() if n and "⚠️" not in str(n)]
    if not assigned: return 0
    for name in set(assigned):
        count = assigned.count(name)
        doc_ref = db.collection('employee_history').document(name)
        batch.set(doc_ref, {'total_shifts': firestore.Increment(count)}, merge=True)
    batch.commit()
    return len(assigned)

# --- חלונית בחירה ---
@st.dialog("בחירה מהירה", width="large")
def show_selection_dialog(shift_key, date_str, station, shift_name, v_type, req_df, history_scores, atan_col, hours_col):
    st.write(f"**{station} | {shift_name}**")
    already = st.session_state.assigned_today.get(date_str, set())
    avail_df = req_df[(req_df['תאריך מבוקש'] == date_str) & (~req_df['שם'].isin(already))].copy()
    if "אט\"ן" in str(v_type): avail_df = avail_df[avail_df[atan_col] == 'כן']
    
    if avail_df.empty: st.warning("אין פנויים")
    else:
        avail_df['balance'] = avail_df['שם'].map(lambda x: history_scores.get(x, 0))
        avail_df = avail_df.sort_values('balance')
        options = {f"{r['שם']} | מאזן: {int(r['balance'])} | {r['תחנה']} | {r[hours_col]}": r['שם'] for _, r in avail_df.iterrows()}
        choice = st.radio("בחר עובד:", list(options.keys()), index=None)
        if st.button("אשר", use_container_width=True):
            if choice:
                sel_name = options[choice]
                st.session_state.final_schedule[shift_key] = sel_name
                st.session_state.assigned_today.setdefault(date_str, set()).add(sel_name)
                st.rerun()

# --- Session State ---
if 'final_schedule' not in st.session_state: st.session_state.final_schedule = {}
if 'assigned_today' not in st.session_state: st.session_state.assigned_today = {}

# --- Sidebar ---
with st.sidebar:
    st.subheader("⚙️ נתונים")
    req_file = st.file_uploader("REQ.csv", type=['csv'])
    shifts_file = st.file_uploader("SHIFTS.csv", type=['csv'])
    if st.button("🧹 איפוס לוח"):
        st.session_state.final_schedule = {}; st.session_state.assigned_today = {}; st.rerun()

# --- Main App ---
if req_file and shifts_file:
    req_df = pd.read_csv(req_file, encoding='utf-8-sig')
    shifts_template = pd.read_csv(shifts_file, encoding='utf-8-sig')
    req_df.columns = req_df.columns.str.strip()
    shifts_template.columns = shifts_template.columns.str.strip()
    
    atan_col = [c for c in req_df.columns if "אט" in c and "מורשה" in c][0]
    hours_col = 'שעות'
    dates = sorted(req_df['תאריך מבוקש'].unique())
    history_scores = get_balance_from_db()

    # גריד דחוס
    cols = st.columns(len(dates), gap="small")
    for i, date_str in enumerate(dates):
        with cols[i]:
            st.markdown(f'<div class="sticky-header"><h5>יום {get_day_name(date_str)}</h5><p>{date_str}</p></div>', unsafe_allow_html=True)
            for idx, s_row in shifts_template.iterrows():
                shift_key = f"{date_str}_{s_row['תחנה']}_{idx}"
                current = st.session_state.final_schedule.get(shift_key)
                with st.container(border=True):
                    st.markdown(f'<div class="shift-card {get_shift_style(s_row["סוג תקן"])}"><div class="shift-title">{s_row["משמרת"]}</div><div class="shift-station">{s_row["תחנה"]}</div></div>', unsafe_allow_html=True)
                    if current:
                        st.caption(f"✅ {current}")
                        if st.button("✖️", key=f"rem_{shift_key}"):
                            st.session_state.assigned_today[date_str].discard(current); st.session_state.final_schedule[shift_key] = None; st.rerun()
                    else:
                        if st.button("➕", key=f"btn_{shift_key}", use_container_width=True):
                            show_selection_dialog(shift_key, date_str, s_row['תחנה'], s_row['משמרת'], s_row['סוג תקן'], req_df, history_scores, atan_col, hours_col)

    # טבלה תחתונה קטנה
    if st.session_state.final_schedule:
        st.markdown("---")
        if st.button("💾 שמירה", type="primary", use_container_width=True):
            update_db_balance(st.session_state.final_schedule)
            st.success("נשמר!"); st.session_state.final_schedule = {}
else:
    st.info("העלה קבצים...")
