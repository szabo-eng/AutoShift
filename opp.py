import streamlit as st
import pandas as pd
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime, timedelta

# --- הגדרות דף ---
st.set_page_config(page_title="לוח שנה שיבוץ מבצעי", layout="wide")

# --- CSS לתצוגת לוח שנה דחוסה ---
st.markdown("""
    <style>
    [data-testid="stAppViewContainer"], [data-testid="stSidebar"], .main {
        direction: rtl;
        text-align: right;
    }
    
    /* עיצוב רשת לוח השנה */
    .calendar-grid {
        display: grid;
        grid-template-columns: repeat(7, 1fr);
        gap: 2px;
        background-color: #e0e0e0;
        border: 1px solid #ccc;
    }
    
    .calendar-day-header {
        background-color: #1f77b4;
        color: white;
        text-align: center;
        padding: 5px;
        font-weight: bold;
        font-size: 0.8rem;
    }
    
    .calendar-day-cell {
        background-color: white;
        min-height: 120px;
        padding: 4px;
        border: 1px solid #eee;
    }
    
    .date-label {
        font-weight: bold;
        font-size: 0.75rem;
        color: #333;
        border-bottom: 1px solid #f0f0f0;
        margin-bottom: 4px;
        display: block;
        text-align: center;
    }

    /* כרטיס משמרת בתוך לוח השנה */
    .shift-mini-card {
        padding: 2px 4px;
        margin-bottom: 2px;
        border-radius: 2px;
        font-size: 0.7rem;
        border-right: 4px solid #ccc;
        line-height: 1.1;
    }
    .type-atan { border-right-color: #FFA500; background-color: #FFF8EE; }
    .type-standard { border-right-color: #ADD8E6; background-color: #F0F8FF; }
    
    /* צמצום מרווחים כללי */
    .stButton > button {
        padding: 0px 4px !important;
        height: 1.2rem !important;
        font-size: 0.65rem !important;
    }
    [data-testid="stVerticalBlock"] { gap: 0rem !important; }
    
    div[role="dialog"] { direction: rtl; text-align: right; }
    </style>
    """, unsafe_allow_html=True)

# --- חיבור Firebase ---
if not firebase_admin._apps:
    try:
        firebase_info = dict(st.secrets["firebase"])
        cred = credentials.Certificate(firebase_info)
        firebase_admin.initialize_app(cred)
    except: pass
db = firestore.client()

# --- פונקציות עזר ---
DAYS_ORDER = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
HEB_DAYS = ['ראשון', 'שני', 'שלישי', 'רביעי', 'חמישי', 'שישי', 'שבת']

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
    for name in set(assigned):
        count = assigned.count(name)
        doc_ref = db.collection('employee_history').document(name)
        batch.set(doc_ref, {'total_shifts': firestore.Increment(count)}, merge=True)
    batch.commit()
    return len(assigned)

# --- חלונית בחירה ---
@st.dialog("שיבוץ עובד", width="large")
def show_selection_dialog(shift_key, date_str, station, shift_name, v_type, req_df, history_scores):
    atan_col = [c for c in req_df.columns if "אט" in c and "מורשה" in c][0]
    hours_col = 'שעות'
    
    st.write(f"**{date_str} | {station} | {shift_name}**")
    already = st.session_state.assigned_today.get(date_str, set())
    avail_df = req_df[(req_df['תאריך מבוקש'] == date_str) & (~req_df['שם'].isin(already))].copy()
    if "אט\"ן" in str(v_type): avail_df = avail_df[avail_df[atan_col] == 'כן']
    
    if avail_df.empty: st.warning("אין פנויים")
    else:
        avail_df['balance'] = avail_df['שם'].map(lambda x: history_scores.get(x, 0))
        avail_df = avail_df.sort_values('balance')
        options = {f"{r['שם']} | מאזן: {int(r['balance'])} | {r['תחנה']} | {r[hours_col]}": r['שם'] for _, r in avail_df.iterrows()}
        choice = st.radio("בחר:", list(options.keys()), index=None)
        if st.button("בצע שיבוץ"):
            if choice:
                st.session_state.final_schedule[shift_key] = options[choice]
                st.session_state.assigned_today.setdefault(date_str, set()).add(options[choice])
                st.rerun()

# --- Session State ---
if 'final_schedule' not in st.session_state: st.session_state.final_schedule = {}
if 'assigned_today' not in st.session_state: st.session_state.assigned_today = {}

# --- Sidebar ---
with st.sidebar:
    st.subheader("📁 טעינת קבצים")
    req_file = st.file_uploader("REQ.csv", type=['csv'])
    shifts_file = st.file_uploader("SHIFTS.csv", type=['csv'])
    if st.button("🧹 איפוס"):
        st.session_state.final_schedule = {}; st.session_state.assigned_today = {}; st.rerun()

# --- Main App ---
st.title("📅 לוח שיבוץ תבלאי")

if req_file and shifts_file:
    req_df = pd.read_csv(req_file, encoding='utf-8-sig')
    shifts_template = pd.read_csv(shifts_file, encoding='utf-8-sig')
    req_df.columns = req_df.columns.str.strip()
    shifts_template.columns = shifts_template.columns.str.strip()
    
    dates_in_data = sorted(pd.to_datetime(req_df['תאריך מבוקש'], dayfirst=True).unique())
    start_date = dates_in_data[0]
    end_date = dates_in_data[-1]
    
    # יצירת טווח תאריכים מלא לתצוגת לוח שנה (מתחיל מיום ראשון הקרוב לתאריך ההתחלה)
    first_day_offset = (start_date.weekday() + 1) % 7 # 0=Sunday
    calendar_start = start_date - timedelta(days=first_day_offset)
    
    history_scores = get_balance_from_db()

    # יצירת כותרות ימים
    cols = st.columns(7)
    for i, day in enumerate(HEB_DAYS):
        cols[i].markdown(f'<div class="calendar-day-header">{day}</div>', unsafe_allow_html=True)

    # מילוי לוח השנה
    current_date = calendar_start
    while current_date <= end_date or current_date.weekday() != 5: # רץ עד סוף השבוע של התאריך האחרון
        week_cols = st.columns(7)
        for i in range(7):
            date_str = current_date.strftime('%d/%m/%Y')
            with week_cols[i]:
                # משבצת יום
                st.markdown(f'<div class="calendar-day-cell"><span class="date-label">{date_str}</span>', unsafe_allow_html=True)
                
                # האם התאריך קיים בנתונים שהועלו?
                if date_str in req_df['תאריך מבוקש'].values:
                    day_shifts = shifts_template.copy()
                    for idx, s_row in day_shifts.iterrows():
                        shift_key = f"{date_str}_{s_row['תחנה']}_{idx}"
                        assigned = st.session_state.final_schedule.get(shift_key)
                        style = "type-atan" if "אט" in str(s_row['סוג תקן']) else "type-standard"
                        
                        # כרטיס משמרת קטנטן
                        st.markdown(f'<div class="shift-mini-card {style}"><b>{s_row["משמרת"]}</b>: {s_row["תחנה"]}</div>', unsafe_allow_html=True)
                        
                        if assigned:
                            st.caption(f"👤 {assigned}")
                            if st.button("✖️", key=f"rem_{shift_key}"):
                                st.session_state.assigned_today[date_str].discard(assigned)
                                del st.session_state.final_schedule[shift_key]; st.rerun()
                        else:
                            if st.button("➕", key=f"btn_{shift_key}", use_container_width=True):
                                show_selection_dialog(shift_key, date_str, s_row['תחנה'], s_row['משמרת'], s_row['סוג תקן'], req_df, history_scores)
                st.markdown('</div>', unsafe_allow_html=True)
            current_date += timedelta(days=1)
        if current_date > end_date: break

    # --- סיכום ושמירה ---
    st.divider()
    if st.session_state.final_schedule:
        if st.button("💾 שמירת שיבוץ סופית", type="primary", use_container_width=True):
            update_db_balance(st.session_state.final_schedule)
            st.success("הנתונים נשמרו ב-Firebase!"); st.session_state.final_schedule = {}; st.rerun()
else:
    st.info("אנא העלה קבצים בסרגל הצד כדי להציג את לוח השנה.")
