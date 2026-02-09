import streamlit as st
import pandas as pd
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime
import io

# --- 1. הגדרות דף ועיצוב (תיקון Sticky Header) ---
st.set_page_config(page_title="מערכת שיבוץ מבצעית 2026", layout="wide", page_icon="📅")

st.markdown("""
    <style>
    /* הגדרות RTL */
    [data-testid="stAppViewContainer"], [data-testid="stSidebar"], .main { 
        direction: rtl !important; 
        text-align: right !important; 
    }
    
    /* מכולת הטבלה הראשית */
    [data-testid="stHorizontalBlock"] {
        direction: rtl !important;
        display: flex !important;
        flex-direction: row !important;
        overflow-x: auto !important;
        gap: 0 !important;
        max-height: 85vh; /* גובה מקסימלי לגלילה */
        overflow-y: auto !important;
        position: relative;
    }

    /* עיצוב עמודה */
    [data-testid="column"] {
        min-width: 260px !important;
        max-width: 260px !important;
        flex: 0 0 260px !important;
        border-right: 1px solid #ccc !important;
        background-color: #fdfdfd;
        padding: 0 !important;
        margin: 0 !important;
    }

    /* תיקון ה-Sticky Header */
    .table-header {
        background-color: #1f77b4;
        color: white;
        padding: 15px 5px;
        text-align: center;
        border-bottom: 2px solid #444;
        
        /* הקסם שמשאיר את הכותרת למעלה */
        position: -webkit-sticky; /* תמיכה בדפדפנים ישנים */
        position: sticky;
        top: 0;
        z-index: 999; /* ערך גבוה כדי שיישאר מעל הכרטיסיות */
        width: 100%;
    }
    
    .day-name { font-weight: bold; font-size: 1.1rem; display: block; }
    .date-val { font-size: 0.85rem; opacity: 0.9; }

    .shift-container {
        border-bottom: 1px solid #eee;
        padding: 10px;
        min-height: 160px;
        display: flex;
        flex-direction: column;
    }

    .shift-card { 
        padding: 8px; 
        border-radius: 4px; 
        margin-bottom: 5px; 
        border-right: 6px solid #ccc;
        background-color: #fff;
        border: 1px solid #ddd;
        text-align: right;
    }
    
    .type-atan { border-right-color: #FFA500; background-color: #FFF9F0; }
    .type-standard { border-right-color: #2E86C1; background-color: #F0F7FC; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. אתחול Firebase ---
@st.cache_resource
def get_db():
    if not firebase_admin._apps:
        try:
            if "firebase" in st.secrets:
                cred = credentials.Certificate(dict(st.secrets["firebase"]))
                firebase_admin.initialize_app(cred)
            else: return None
        except: return None
    return firestore.client()

db = get_db()

# --- 3. פונקציות עזר ---
DAYS_HEB = {'Sunday': 'ראשון', 'Monday': 'שני', 'Tuesday': 'שלישי', 'Wednesday': 'רביעי', 'Thursday': 'חמישי', 'Friday': 'שישי', 'Saturday': 'שבת'}

def get_day_name(date_str):
    try: return DAYS_HEB[datetime.strptime(date_str, '%d/%m/%Y').strftime('%A')]
    except: return ""

@st.cache_data(ttl=600)
def get_balance_map():
    scores = {}
    if not db: return scores
    try:
        docs = db.collection('employee_history').stream()
        for doc in docs: scores[doc.id] = doc.to_dict().get('total_shifts', 0)
    except: pass
    return scores

def update_firebase_db(final_schedule):
    if not db: return False
    batch = db.batch()
    updates = {}
    for name in final_schedule.values(): updates[name] = updates.get(name, 0) + 1
    for name, count in updates.items():
        doc_ref = db.collection('employee_history').document(name)
        batch.set(doc_ref, {'total_shifts': firestore.Increment(count)}, merge=True)
    try:
        batch.commit()
        get_balance_map.clear()
        return True
    except: return False

# --- 4. דיאלוג שיבוץ ---
@st.dialog("שיבוץ עובד ידני")
def show_manual_picker(shift_key, date_str, s_row, req_df, balance):
    st.write(f"**תחנה:** {s_row['תחנה']} | **משמרת:** {s_row['משמרת']}")
    avail = req_df[req_df['תאריך מבוקש'] == date_str].copy()
    already_working = st.session_state.assigned_today.get(date_str, set())
    avail = avail[~avail['שם'].isin(already_working)]
    
    if "אט" in str(s_row['סוג תקן']):
        atan_cols = [c for c in req_df.columns if "אט" in c and "מורשה" in c]
        if atan_cols: avail = avail[avail[atan_cols[0]] == 'כן']
    
    if avail.empty: st.warning("אין עובדים פנויים.")
    else:
        avail['bal'] = avail['שם'].map(lambda x: balance.get(x, 0))
        options = {f"{r['שם']} (מאזן: {int(r['bal'])})": r['שם'] for _, r in avail.sort_values('bal').iterrows()}
        choice_label = st.radio("בחר עובד:", list(options.keys()))
        if st.button("בצע שיבוץ", type="primary", use_container_width=True):
            name = options[choice_label]
            st.session_state.final_schedule[shift_key] = name
            st.session_state.assigned_today.setdefault(date_str, set()).add(name)
            st.rerun()

# --- 5. State ---
if 'init' not in st.session_state:
    st.session_state.final_schedule = {}
    st.session_state.assigned_today = {}
    st.session_state.cancelled_shifts = set()
    st.session_state.init = True

# --- 6. Sidebar ---
with st.sidebar:
    st.title("⚙️ ניהול")
    req_f = st.file_uploader("בקשות (CSV)", type=['csv'])
    shi_f = st.file_uploader("תבנית (CSV)", type=['csv'])
    
    if st.button("🧹 נקה הכל", use_container_width=True):
        st.session_state.final_schedule = {}
        st.session_state.assigned_today = {}
        st.session_state.cancelled_shifts = set()
        st.rerun()

    if st.session_state.final_schedule:
        st.divider()
        if st.button("💾 עדכן נתונים ב-DB", type="primary", use_container_width=True):
            if update_firebase_db(st.session_state.final_schedule):
                st.toast("עודכן בהצלחה!", icon="✅")

# --- 7. Main ---
st.title("📅 לוח שיבוץ 2026")

if req_f and shi_f:
    req_df = pd.read_csv(req_f, encoding='utf-8-sig')
    shi_df = pd.read_csv(shi_f, encoding='utf-8-sig')
    dates = sorted(req_df['תאריך מבוקש'].unique(), key=lambda x: datetime.strptime(x, '%d/%m/%Y'))
    global_balance = get_balance_map()

    # גריד המשמרות
    cols = st.columns(len(dates))
    
    for i, d_str in enumerate(dates):
        with cols[i]:
            # הכותרת שצריכה להישאר נעולה
            st.markdown(f'''
                <div class="table-header">
                    <span class="day-name">{get_day_name(d_str)}</span>
                    <span class="date-val">{d_str}</span>
                </div>
            ''', unsafe_allow_html=True)
            
            for idx, s in shi_df.iterrows():
                s_key = f"{d_str}_{s['תחנה']}_{s['משמרת']}_{idx}"
                assigned = st.session_state.final_schedule.get(s_key)
                cancelled = s_key in st.session_state.cancelled_shifts
                
                style = "type-atan" if "אט" in str(s['סוג תקן']) else "type-standard"
                
                st.markdown(f'<div class="shift-container"><div class="shift-card {style}"><div class="shift-info">{s["משמרת"]}<br>{s["תחנה"]}</div></div>', unsafe_allow_html=True)
                
                if cancelled:
                    if st.button("שחזר", key=f"res_{s_key}"): 
                        st.session_state.cancelled_shifts.remove(s_key); st.rerun()
                elif assigned:
                    st.success(f"👤 {assigned}")
                    if st.button("❌", key=f"rem_{s_key}"):
                        st.session_state.assigned_today[d_str].discard(assigned)
                        st.session_state.final_schedule.pop(s_key); st.rerun()
                else:
                    if st.button("➕ שבץ", key=f"add_{s_key}", use_container_width=True):
                        show_manual_picker(s_key, d_str, s, req_df, global_balance)
                st.markdown('</div>', unsafe_allow_html=True)
else:
    st.info("👈 העלה קבצים כדי להתחיל.")
