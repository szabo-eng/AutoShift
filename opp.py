import streamlit as st
import pandas as pd
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime, timedelta

# --- הגדרות דף ---
st.set_page_config(page_title="לוח שנה שיבוץ - תצוגה מתוקנת", layout="wide")

# --- CSS מתוקן למניעת חפיפה ---
st.markdown("""
    <style>
    [data-testid="stAppViewContainer"], [data-testid="stSidebar"], .main {
        direction: rtl;
        text-align: right;
    }
    
    /* כותרת ימי השבוע */
    .calendar-grid-header {
        display: grid;
        grid-template-columns: repeat(7, 1fr);
        background-color: #1f77b4;
        color: white;
        text-align: center;
        font-weight: bold;
        padding: 8px 0;
        border-radius: 5px 5px 0 0;
        margin-bottom: 2px;
    }

    /* תא יום בלוח השנה */
    .calendar-cell {
        border: 1px solid #e6e6e6;
        background-color: #ffffff;
        min-height: 140px; /* הגדלת גובה מינימלי */
        padding: 8px 4px; /* הגדלת ריפוד */
        display: flex;
        flex-direction: column;
        gap: 4px;
    }

    /* הצגת התאריך - מופרד וברור */
    .date-num { 
        font-size: 0.8rem; 
        font-weight: bold; 
        color: #1f77b4; 
        border-bottom: 1px solid #f0f0f0;
        padding-bottom: 4px;
        margin-bottom: 6px; /* רווח ברור לפני המשמרות */
        display: block;
        text-align: center;
    }

    /* כרטיס משמרת */
    .shift-box {
        padding: 4px 6px;
        border-radius: 3px;
        font-size: 0.75rem;
        border-right: 5px solid #ccc;
        background-color: #fdfdfd;
        box-shadow: 1px 1px 2px rgba(0,0,0,0.05);
    }
    .type-atan { border-right-color: #FFA500; background-color: #FFF8EE; }
    .type-standard { border-right-color: #ADD8E6; background-color: #F0F8FF; }
    
    .assigned-name { 
        color: #2e7d32; 
        font-weight: bold; 
        font-size: 0.75rem; 
        margin-top: 2px;
        padding-right: 5px;
    }

    /* ביטול רווחים עודפים של Streamlit */
    [data-testid="stVerticalBlock"] { gap: 0rem !important; }
    div.element-container { margin-bottom: -2px !important; }
    </style>
    """, unsafe_allow_html=True)

# --- Firebase (זהה לקוד הקודם) ---
if not firebase_admin._apps:
    try:
        firebase_info = dict(st.secrets["firebase"])
        cred = credentials.Certificate(firebase_info)
        firebase_admin.initialize_app(cred)
    except: pass
db = firestore.client()

def get_balance():
    scores = {}
    try:
        docs = db.collection('employee_history').stream()
        for doc in docs: scores[doc.id] = doc.to_dict().get('total_shifts', 0)
    except: pass
    return scores

# --- דיאלוג בחירה ---
@st.dialog("בחירת עובד", width="large")
def pick_employee(shift_key, date_str, station, shift_name, v_type, req_df, balance):
    st.write(f"### {date_str} | {station}")
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
        if st.button("אשר", width='stretch'):
            if choice:
                name = options[choice]
                st.session_state.final_schedule[shift_key] = name
                st.session_state.assigned_today.setdefault(date_str, set()).add(name)
                st.rerun()

# --- State ---
if 'final_schedule' not in st.session_state: st.session_state.final_schedule = {}
if 'assigned_today' not in st.session_state: st.session_state.assigned_today = {}

# --- Sidebar & Logic ---
with st.sidebar:
    st.title("⚙️ ניהול")
    req_file = st.file_uploader("REQ.csv", type=['csv'])
    shifts_file = st.file_uploader("SHIFTS.csv", type=['csv'])

if req_file and shifts_file:
    req_df = pd.read_csv(req_file, encoding='utf-8-sig')
    shifts_template = pd.read_csv(shifts_file, encoding='utf-8-sig')
    req_df.columns = req_df.columns.str.strip()
    shifts_template.columns = shifts_template.columns.str.strip()
    
    # חישוב תאריכים
    req_df['dt'] = pd.to_datetime(req_df['תאריך מבוקש'], dayfirst=True)
    dates_sorted = sorted(req_df['dt'].unique())
    start_date = dates_sorted[0]
    start_cal = start_date - timedelta(days=(start_date.weekday() + 1) % 7)
    balance = get_balance()

    # כותרות לוח שנה
    st.markdown('<div class="calendar-grid-header"><div>ראשון</div><div>שני</div><div>שלישי</div><div>רביעי</div><div>חמישי</div><div>שישי</div><div>שבת</div></div>', unsafe_allow_html=True)

    curr = start_cal
    # הצגת השבועות הרלוונטיים (לפי נתוני הקובץ)
    num_weeks = ((dates_sorted[-1] - start_cal).days // 7) + 1
    
    for _ in range(num_weeks):
        cols = st.columns(7, gap="small")
        for i in range(7):
            d_str = curr.strftime('%d/%m/%Y')
            with cols[i]:
                # התחלת תא היום
                st.markdown(f'<div class="calendar-cell"><span class="date-num">{d_str}</span>', unsafe_allow_html=True)
                
                if d_str in req_df['תאריך מבוקש'].values:
                    for idx, s in shifts_template.iterrows():
                        key = f"{d_str}_{s['תחנה']}_{idx}"
                        assigned = st.session_state.final_schedule.get(key)
                        style = "type-atan" if "אט" in str(s['סוג תקן']) else "type-standard"
                        
                        st.markdown(f'<div class="shift-box {style}"><b>{s["משמרת"]}</b> | {s["תחנה"]}</div>', unsafe_allow_html=True)
                        
                        if assigned:
                            st.markdown(f'<div class="assigned-name">✅ {assigned}</div>', unsafe_allow_html=True)
                            if st.button("✖️", key=f"del_{key}"):
                                st.session_state.assigned_today[d_str].discard(assigned)
                                del st.session_state.final_schedule[key]; st.rerun()
                        else:
                            if st.button("➕", key=f"add_{key}", width='stretch'):
                                pick_employee(key, d_str, s['תחנה'], s['משמרת'], s['סוג תקן'], req_df, balance)
                st.markdown('</div>', unsafe_allow_html=True) # סגירת calendar-cell
            curr += timedelta(days=1)
else:
    st.info("העלה קבצי CSV כדי להתחיל בשיבוץ.")
