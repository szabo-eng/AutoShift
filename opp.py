import streamlit as st
import pandas as pd
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime, timedelta

# --- הגדרות דף ---
st.set_page_config(page_title="לוח שנה שיבוץ 2026", layout="wide")

# --- CSS מעודכן (RTL + Sticky + Compact) ---
st.markdown("""
    <style>
    [data-testid="stAppViewContainer"], [data-testid="stSidebar"], .main {
        direction: rtl;
        text-align: right;
    }
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
        min-height: 120px;
        padding: 4px;
    }
    .date-num { font-size: 0.75rem; font-weight: bold; color: #888; }
    .shift-box {
        padding: 2px 5px;
        margin-bottom: 2px;
        border-radius: 3px;
        font-size: 0.7rem;
        border-right: 4px solid #ccc;
    }
    .type-atan { border-right-color: #FFA500; background-color: #FFF8EE; }
    .type-standard { border-right-color: #ADD8E6; background-color: #F0F8FF; }
    .assigned-name { color: #2e7d32; font-weight: bold; font-size: 0.7rem; }
    
    /* תיקוני ריווח */
    [data-testid="stVerticalBlock"] { gap: 0rem !important; }
    div.element-container { margin-bottom: -5px !important; }
    </style>
    """, unsafe_allow_html=True)

# --- Firebase ---
if not firebase_admin._apps:
    try:
        firebase_info = dict(st.secrets["firebase"])
        cred = credentials.Certificate(firebase_info)
        firebase_admin.initialize_app(cred)
    except: pass
db = firestore.client()

# --- פונקציות ---
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

def highlight_rows(row):
    if row['סטטוס'] == 'חסר': return ['background-color: #ffcccc'] * len(row)
    if row['תחנה (בפועל)'] != row['תחנה (מקורית)'] and row['תחנה (מקורית)'] != '-':
        return ['background-color: #fff3cd'] * len(row)
    return [''] * len(row)

# --- דיאלוג בחירה ---
@st.dialog("שיבוץ", width="large")
def pick_employee(shift_key, date_str, station, shift_name, v_type, req_df, balance):
    st.write(f"**{date_str} | {station}**")
    already = st.session_state.assigned_today.get(date_str, set())
    avail = req_df[(req_df['תאריך מבוקש'] == date_str) & (~req_df['שם'].isin(already))].copy()
    
    if "אט" in str(v_type):
        atan_col = [c for c in req_df.columns if "אט" in c and "מורשה" in c][0]
        avail = avail[avail[atan_col] == 'כן']
    
    if avail.empty:
        st.error("אין פנויים")
    else:
        avail['bal'] = avail['שם'].map(lambda x: balance.get(x, 0))
        avail = avail.sort_values('bal')
        options = {f"{r['שם']} (מאזן: {int(r['bal'])}) | {r['תחנה']}": r['שם'] for _, r in avail.iterrows()}
        choice = st.radio("בחר עובד:", list(options.keys()), index=None)
        # עדכון width='stretch' בכפתור בתוך הדיאלוג
        if st.button("אשר", width='stretch'):
            if choice:
                name = options[choice]
                st.session_state.final_schedule[shift_key] = name
                st.session_state.assigned_today.setdefault(date_str, set()).add(name)
                st.rerun()

# --- State ---
if 'final_schedule' not in st.session_state: st.session_state.final_schedule = {}
if 'assigned_today' not in st.session_state: st.session_state.assigned_today = {}

# --- Sidebar ---
with st.sidebar:
    st.title("⚙️ ניהול")
    req_file = st.file_uploader("REQ.csv", type=['csv'])
    shifts_file = st.file_uploader("SHIFTS.csv", type=['csv'])

# --- גוף האפליקציה ---
if req_file and shifts_file:
    req_df = pd.read_csv(req_file, encoding='utf-8-sig')
    shifts_template = pd.read_csv(shifts_file, encoding='utf-8-sig')
    req_df.columns = req_df.columns.str.strip()
    shifts_template.columns = shifts_template.columns.str.strip()
    
    dates = sorted(pd.to_datetime(req_df['תאריך מבוקש'], dayfirst=True).unique())
    start_date = dates[0]
    start_cal = start_date - timedelta(days=(start_date.weekday() + 1) % 7)
    balance = get_balance()

    # כותרות לוח שנה
    st.markdown('<div class="calendar-grid-header"><div>ראשון</div><div>שני</div><div>שלישי</div><div>רביעי</div><div>חמישי</div><div>שישי</div><div>שבת</div></div>', unsafe_allow_html=True)

    curr = start_cal
    for _ in range(2): # תצוגת שבועיים
        cols = st.columns(7, gap="small")
        for i in range(7):
            d_str = curr.strftime('%d/%m/%Y')
            with cols[i]:
                st.markdown(f'<div class="calendar-cell"><span class="date-num">{d_str}</span>', unsafe_allow_html=True)
                if d_str in req_df['תאריך מבוקש'].values:
                    for idx, s in shifts_template.iterrows():
                        key = f"{d_str}_{s['תחנה']}_{s['משמרת']}_{idx}"
                        assigned = st.session_state.final_schedule.get(key)
                        style = "type-atan" if "אט" in str(s['סוג תקן']) else "type-standard"
                        st.markdown(f'<div class="shift-box {style}"><b>{s["משמרת"]}</b> | {s["תחנה"]}</div>', unsafe_allow_html=True)
                        if assigned:
                            st.markdown(f'<div class="assigned-name">✅ {assigned}</div>', unsafe_allow_html=True)
                            if st.button("✖️", key=f"del_{key}"):
                                st.session_state.assigned_today[d_str].discard(assigned)
                                del st.session_state.final_schedule[key]; st.rerun()
                        else:
                            # עדכון width='stretch' בכפתור
                            if st.button("➕", key=f"add_{key}", width='stretch'):
                                pick_employee(key, d_str, s['תחנה'], s['משמרת'], s['סוג תקן'], req_df, balance)
                st.markdown('</div>', unsafe_allow_html=True)
            curr += timedelta(days=1)

    # --- טבלת ריכוז סופית (כאן היה ה-Error) ---
    st.divider()
    st.subheader("📊 בקרת שיבוצים")
    summary = []
    for d_str in req_df['תאריך מבוקש'].unique():
        for idx, s in shifts_template.iterrows():
            key = f"{d_str}_{s['תחנה']}_{s['משמרת']}_{idx}"
            assigned = st.session_state.final_schedule.get(key)
            orig = "-"
            if assigned:
                row = req_df[(req_df['שם'] == assigned) & (req_df['תאריך מבוקש'] == d_str)]
                if not row.empty: orig = row.iloc[0]['תחנה']
            
            summary.append({
                "תאריך": d_str, "משמרת": s['משמרת'], "תחנה (בפועל)": s['תחנה'],
                "עובד": assigned if assigned else "⚠️ חסר", "תחנה (מקורית)": orig,
                "סטטוס": "תקין" if assigned else "חסר"
            })
    
    # שימוש ב-width='stretch' החדש
    st.dataframe(pd.DataFrame(summary).style.apply(highlight_rows, axis=1), width='stretch', hide_index=True)

    if st.session_state.final_schedule:
        if st.button("💾 שמירה סופית", type="primary", width='stretch'):
            save_to_db(st.session_state.final_schedule)
            st.balloons(); st.success("נשמר!"); st.session_state.final_schedule = {}
else:
    st.info("העלה קבצים...")
