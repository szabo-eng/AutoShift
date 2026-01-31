import streamlit as st
import pandas as pd
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime

# --- הגדרות דף ---
st.set_page_config(page_title="ניהול שיבוץ - תצוגה מלאה", layout="wide")

# --- הזרקת CSS ל-RTL וכותרות דביקות קומפקטיות ---
st.markdown("""
    <style>
    [data-testid="stAppViewContainer"], [data-testid="stSidebar"] {
        direction: rtl;
        text-align: right;
    }
    .sticky-header {
        position: -webkit-sticky;
        position: sticky;
        top: 0;
        background-color: #f8f9fa;
        z-index: 1000;
        padding: 5px 2px;
        border-bottom: 2px solid #1f77b4;
        margin-bottom: 8px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        border-radius: 4px;
    }
    .sticky-header h5 {
        margin: 0; text-align: center; font-size: 0.95rem !important; font-weight: bold; color: #1f77b4;
    }
    .sticky-header p {
        margin: 0; text-align: center; font-size: 0.8rem !important; color: #555;
    }
    /* התאמת כרטיס המשמרת */
    .shift-card-text {
        font-size: 0.9rem;
        line-height: 1.2;
    }
    [data-testid="stVerticalBlock"] > div:has(div.sticky-header) {
        position: sticky;
        top: 2.85rem;
        z-index: 999;
    }
    </style>
    """, unsafe_allow_html=True)

# --- חיבור ל-Firebase ---
if not firebase_admin._apps:
    try:
        firebase_info = dict(st.secrets["firebase"])
        cred = credentials.Certificate(firebase_info)
        firebase_admin.initialize_app(cred)
    except:
        st.error("שגיאה בחיבור ל-Firebase.")
db = firestore.client()

# --- עזרי תאריכים ---
DAYS_HEBREW = {'Sunday': 'ראשון', 'Monday': 'שני', 'Tuesday': 'שלישי', 'Wednesday': 'רביעי', 'Thursday': 'חמישי', 'Friday': 'שישי', 'Saturday': 'שבת'}
def get_day_name(date_str):
    try:
        date_obj = datetime.strptime(date_str, '%d/%m/%Y')
        return DAYS_HEBREW[date_obj.strftime('%A')]
    except: return ""

# --- פונקציות בסיס נתונים ---
def get_balance_from_db():
    scores = {}
    docs = db.collection('employee_history').stream()
    for doc in docs: scores[doc.id] = doc.to_dict().get('total_shifts', 0)
    return scores

def update_db_balance(schedule_dict):
    batch = db.batch()
    assigned_names = [name for name in schedule_dict.values() if name and "⚠️" not in name]
    for name in set(assigned_names):
        count = assigned_names.count(name)
        doc_ref = db.collection('employee_history').document(name)
        batch.set(doc_ref, {'total_shifts': firestore.Increment(count)}, merge=True)
    batch.commit()
    return len(assigned_names)

# --- ניהול זיכרון ---
if 'final_schedule' not in st.session_state: st.session_state.final_schedule = {}
if 'assigned_today' not in st.session_state: st.session_state.assigned_today = {}
if 'cancelled_shifts' not in st.session_state: st.session_state.cancelled_shifts = set()

# --- ממשק משתמש ---
st.title("🛡️ לוח בקרה ושיבוץ")

with st.sidebar:
    st.header("⚙️ הגדרות")
    req_file = st.file_uploader("העלה REQ.csv", type=['csv'])
    shifts_file = st.file_uploader("העלה SHIFTS.csv", type=['csv'])
    if st.button("🧹 נקה לוח שנה", use_container_width=True):
        st.session_state.final_schedule = {}; st.session_state.assigned_today = {}; st.session_state.cancelled_shifts = set()
        st.rerun()

if req_file and shifts_file:
    req_df = pd.read_csv(req_file, encoding='utf-8-sig')
    shifts_template = pd.read_csv(shifts_file, encoding='utf-8-sig')
    req_df.columns = req_df.columns.str.strip()
    shifts_template.columns = shifts_template.columns.str.strip()
    
    # זיהוי עמודת אט"ן בקובץ REQ
    atan_col = [c for c in req_df.columns if "אט" in c and "מורשה" in c][0]
    dates = sorted(req_df['תאריך מבוקש'].unique())

    if st.button("🪄 בצע שיבוץ אוטומטי", type="primary", use_container_width=True):
        history_scores = get_balance_from_db()
        temp_schedule = {}; temp_assigned_today = {d: set() for d in dates}
        for date in dates:
            for idx, s_row in shifts_template.iterrows():
                shift_key = f"{date}_{s_row['תחנה']}_{s_row['משמרת']}_{idx}"
                if shift_key in st.session_state.cancelled_shifts: continue
                
                pot = req_df[(req_df['תאריך מבוקש'] == date) & (req_df['משמרת'] == s_row['משמרת']) & (req_df['תחנה'] == s_row['תחנה'])]
                
                # בדיקת סוג תקן להתאמת אט"ן
                if "אט\"ן" in str(s_row['סוג תקן']):
                    pot = pot[pot[atan_col] == 'כן']
                
                pot = pot[~pot['שם'].isin(temp_assigned_today[date])]
                if not pot.empty:
                    pot = pot.copy()
                    pot['score'] = pot['שם'].map(lambda x: history_scores.get(x, 0))
                    best = pot.sort_values('score').iloc[0]['שם']
                    temp_schedule[shift_key] = best
                    temp_assigned_today[date].add(best)
                    history_scores[best] = history_scores.get(best, 0) + 1
        st.session_state.final_schedule = temp_schedule; st.session_state.assigned_today = temp_assigned_today
        st.rerun()

    st.divider()
    grid_cols = st.columns(len(dates))
    
    for i, date_str in enumerate(dates):
        with grid_cols[i]:
            day_name = get_day_name(date_str)
            st.markdown(f"""<div class="sticky-header"><h5>יום {day_name}</h5><p>{date_str}</p></div>""", unsafe_allow_html=True)
            
            for idx, s_row in shifts_template.iterrows():
                shift_key = f"{date_str}_{s_row['תחנה']}_{s_row['משמרת']}_{idx}"
                is_cancelled = shift_key in st.session_state.cancelled_shifts
                current = st.session_state.final_schedule.get(shift_key)
                
                # חילוץ סוג תקן לתצוגה
                v_type = s_row['סוג תקן'] if 'סוג תקן' in s_row else ""
                
                with st.container(border=True):
                    # שורת תיאור משמרת כולל סוג תקן ותחנה
                    st.markdown(f"<div class='shift-card-text'><b>{s_row['משמרת']} - {v_type}</b><br>{s_row['תחנה']}</div>", unsafe_allow_html=True)
                    
                    if is_cancelled:
                        st.warning("🚫")
                        if st.button("שחזר", key=f"res_{shift_key}"):
                            st.session_state.cancelled_shifts.remove(shift_key); st.rerun()
                    elif current:
                        st.success(f"✅ {current}")
                        c1, c2 = st.columns(2)
                        with c1:
                            if st.button("✖️", key=f"rem_{shift_key}", help="הסר עובד"):
                                st.session_state.assigned_today[date_str].discard(current)
                                st.session_state.final_schedule[shift_key] = None; st.rerun()
                        with c2:
                            if st.button("🚫", key=f"can_{shift_key}", help="בטל משמרת"):
                                st.session_state.cancelled_shifts.add(shift_key)
                                st.session_state.assigned_today[date_str].discard(current)
                                st.session_state.final_schedule[shift_key] = None; st.rerun()
                    else:
                        st.error("⚠️")
                        pot = req_df[(req_df['תאריך מבוקש'] == date_str) & (req_df['משמרת'] == s_row['משמרת']) & (req_df['תחנה'] == s_row['תחנה'])]
                        if "אט\"ן" in str(v_type):
                            pot = pot[pot[atan_col] == 'כן']
                        
                        avail = pot[~pot['שם'].isin(st.session_state.assigned_today.get(date_str, set()))]['שם'].tolist()
                        if avail:
                            choice = st.selectbox("בחר:", ["-"] + avail, key=f"sel_{shift_key}", label_visibility="collapsed")
                            if choice != "-":
                                st.session_state.final_schedule[shift_key] = choice
                                st.session_state.assigned_today.setdefault(date_str, set()).add(choice); st.rerun()
                        if st.button("🚫 בטל", key=f"bc_{shift_key}", use_container_width=True):
                            st.session_state.cancelled_shifts.add(shift_key); st.rerun()

    if st.session_state.final_schedule:
        st.divider()
        if st.button("💾 שמירה סופית ל-Firebase", type="primary", use_container_width=True):
            count = update_db_balance(st.session_state.final_schedule)
            st.balloons(); st.success(f"נשמר! {count} רשומות עודכנו."); st.session_state.final_schedule = {}

else:
    st.info("אנא העלה קבצים בסרגל הצד.")
