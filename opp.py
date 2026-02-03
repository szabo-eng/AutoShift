import streamlit as st
import pandas as pd
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime, timedelta

# --- הגדרות דף ---
st.set_page_config(page_title="לוח שנה שיבוץ", layout="wide")

# --- CSS מעודכן לתצוגת לוח שנה מקצועית ---
st.markdown("""
    <style>
    [data-testid="stAppViewContainer"], [data-testid="stSidebar"], .main {
        direction: rtl;
        text-align: right;
    }
    
    /* עיצוב רשת לוח השנה */
    .calendar-grid-header {
        display: grid;
        grid-template-columns: repeat(7, 1fr);
        background-color: #1f77b4;
        color: white;
        text-align: center;
        font-weight: bold;
        padding: 5px 0;
        border-radius: 5px 5px 0 0;
    }

    .calendar-cell {
        border: 1px solid #e6e6e6;
        background-color: #ffffff;
        min-height: 130px;
        padding: 5px;
        transition: background-color 0.2s;
    }
    .calendar-cell:hover { background-color: #fafafa; }

    .date-num {
        font-size: 0.75rem;
        font-weight: bold;
        color: #888;
        margin-bottom: 5px;
        display: block;
    }

    /* כרטיסי משמרת דחוסים */
    .shift-box {
        padding: 3px 5px;
        margin-bottom: 3px;
        border-radius: 3px;
        font-size: 0.7rem;
        border-right: 5px solid #ccc;
        line-height: 1.2;
        background-color: #f9f9f9;
    }
    .type-atan { border-right-color: #FFA500; background-color: #FFF8EE; }
    .type-standard { border-right-color: #ADD8E6; background-color: #F0F8FF; }
    
    .assigned-name {
        color: #2e7d32;
        font-weight: bold;
        font-size: 0.7rem;
        margin-top: 1px;
    }

    /* כפתורים קטנים מאוד */
    .stButton > button {
        padding: 0px 5px !important;
        height: 1.2rem !important;
        font-size: 0.65rem !important;
        min-height: unset !important;
    }
    
    hr { margin: 10px 0 !important; }
    </style>
    """, unsafe_allow_html=True)

# --- אתחול Firebase ---
if not firebase_admin._apps:
    try:
        firebase_info = dict(st.secrets["firebase"])
        cred = credentials.Certificate(firebase_info)
        firebase_admin.initialize_app(cred)
    except: pass
db = firestore.client()

# --- פונקציות עזר ---
def get_balance():
    scores = {}
    try:
        docs = db.collection('employee_history').stream()
        for doc in docs: scores[doc.id] = doc.to_dict().get('total_shifts', 0)
    except: pass
    return scores

def save_to_db(schedule):
    batch = db.batch()
    assigned = [n for n in schedule.values() if n]
    for name in set(assigned):
        count = assigned.count(name)
        ref = db.collection('employee_history').document(name)
        batch.set(ref, {'total_shifts': firestore.Increment(count)}, merge=True)
    batch.commit()
    return len(assigned)

# --- חלונית בחירה (Dialog) ---
@st.dialog("בחירת עובד", width="large")
def pick_employee(shift_key, date_str, station, shift_name, v_type, req_df, balance):
    st.write(f"**{date_str} | {station} | {shift_name}**")
    
    # סינון עובדים פנויים
    already = st.session_state.assigned_today.get(date_str, set())
    avail = req_df[(req_df['תאריך מבוקש'] == date_str) & (~req_df['שם'].isin(already))].copy()
    
    # סינון אט"ן
    if "אט" in str(v_type):
        atan_col = [c for c in req_df.columns if "אט" in c and "מורשה" in c][0]
        avail = avail[avail[atan_col] == 'כן']
    
    if avail.empty:
        st.error("אין עובדים פנויים שתואמים לדרישות.")
    else:
        avail['balance'] = avail['שם'].map(lambda x: balance.get(x, 0))
        avail = avail.sort_values('balance')
        
        options = {f"{r['שם']} (מאזן: {int(r['balance'])}) | {r['תחנה']}": r['שם'] for _, r in avail.iterrows()}
        choice = st.radio("בחר עובד:", list(options.keys()), index=None)
        
        if st.button("אשר שיבוץ", use_container_width=True):
            if choice:
                name = options[choice]
                st.session_state.final_schedule[shift_key] = name
                st.session_state.assigned_today.setdefault(date_str, set()).add(name)
                st.rerun()

# --- ניהול State ---
if 'final_schedule' not in st.session_state: st.session_state.final_schedule = {}
if 'assigned_today' not in st.session_state: st.session_state.assigned_today = {}

# --- ממשק צד ---
with st.sidebar:
    st.title("⚙️ הגדרות")
    req_file = st.file_uploader("טען REQ.csv", type=['csv'])
    shifts_file = st.file_uploader("טען SHIFTS.csv", type=['csv'])
    if st.button("🧹 נקה הכל"):
        st.session_state.final_schedule = {}; st.session_state.assigned_today = {}; st.rerun()

# --- לוח השנה הראשי ---
if req_file and shifts_file:
    req_df = pd.read_csv(req_file, encoding='utf-8-sig')
    shifts_template = pd.read_csv(shifts_file, encoding='utf-8-sig')
    req_df.columns = req_df.columns.str.strip()
    shifts_template.columns = shifts_template.columns.str.strip()
    
    # חישוב תאריכים
    req_df['dt'] = pd.to_datetime(req_df['תאריך מבוקש'], dayfirst=True)
    dates_sorted = sorted(req_df['dt'].unique())
    start_date = dates_sorted[0]
    
    # התחלה מיום ראשון של אותו שבוע
    start_of_calendar = start_date - timedelta(days=(start_date.weekday() + 1) % 7)
    balance = get_balance()

    # כותרות ימים
    st.markdown("""
        <div class="calendar-grid-header">
            <div>ראשון</div><div>שני</div><div>שלישי</div><div>רביעי</div><div>חמישי</div><div>שישי</div><div>שבת</div>
        </div>
    """, unsafe_allow_html=True)

    # ריצה על שבועות
    curr = start_of_calendar
    for week in range(2): # מציג שבועיים קדימה (ניתן לשינוי)
        cols = st.columns(7, gap="small")
        for i in range(7):
            date_str = curr.strftime('%d/%m/%Y')
            with cols[i]:
                st.markdown(f'<div class="calendar-cell"><span class="date-num">{date_str}</span>', unsafe_allow_html=True)
                
                # הצגת משמרות אם התאריך קיים בנתונים
                if date_str in req_df['תאריך מבוקש'].values:
                    for idx, s_row in shifts_template.iterrows():
                        s_key = f"{date_str}_{s_row['תחנה']}_{s_row['משמרת']}_{idx}"
                        assigned = st.session_state.final_schedule.get(s_key)
                        style = "type-atan" if "אט" in str(s_row['סוג תקן']) else "type-standard"
                        
                        st.markdown(f'<div class="shift-box {style}"><b>{s_row["משמרת"]}</b> | {s_row["תחנה"]}</div>', unsafe_allow_html=True)
                        
                        if assigned:
                            st.markdown(f'<div class="assigned-name">✅ {assigned}</div>', unsafe_allow_html=True)
                            if st.button("✖️", key=f"del_{s_key}"):
                                st.session_state.assigned_today[date_str].discard(assigned)
                                del st.session_state.final_schedule[s_key]; st.rerun()
                        else:
                            if st.button("➕", key=f"add_{s_key}", use_container_width=True):
                                pick_employee(s_key, date_str, s_row['תחנה'], s_row['משמרת'], s_row['סוג תקן'], req_df, balance)
                st.markdown('</div>', unsafe_allow_html=True)
            curr += timedelta(days=1)
        if curr > dates_sorted[-1] + timedelta(days=7): break

    # כפתור שמירה
    st.divider()
    if st.session_state.final_schedule:
        if st.button("💾 שמירה סופית ועדכון מאזן עובדים", type="primary", use_container_width=True):
            count = save_to_db(st.session_state.final_schedule)
            st.balloons()
            st.success(f"נשמר בהצלחה! {count} שיבוצים עודכנו ב-DB.")
            st.session_state.final_schedule = {}; st.session_state.assigned_today = {}
else:
    st.info("העלה קבצי CSV כדי להתחיל בשיבוץ.")
