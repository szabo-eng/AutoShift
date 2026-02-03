import streamlit as st
import pandas as pd
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime

# --- הגדרות דף ---
st.set_page_config(page_title="ניהול שיבוץ - כותרות דביקות", layout="wide")

# --- הזרקת CSS לשיפור ה-Sticky והתצוגה ---
st.markdown("""
    <style>
    [data-testid="stAppViewContainer"], [data-testid="stSidebar"], .main {
        direction: rtl;
        text-align: right;
    }
    
    /* הגדרת הכותרת הדביקה */
    .sticky-header {
        position: -webkit-sticky;
        position: sticky;
        top: 2.85rem; /* גובה הסרגל של Streamlit */
        background-color: white; /* רקע לבן כדי שהטקסט לא יתערבב עם הקלפים שמתחתיו */
        z-index: 1000;
        padding: 15px 5px;
        border-bottom: 3px solid #1f77b4;
        margin-bottom: 15px;
        box-shadow: 0 4px 6px -2px rgba(0,0,0,0.1);
    }
    .sticky-header h5 { margin: 0; text-align: center; font-size: 1.1rem !important; font-weight: bold; color: #1f77b4; }
    .sticky-header p { margin: 0; text-align: center; font-size: 0.9rem !important; color: #666; }

    /* כרטיסי משמרות */
    .shift-card { padding: 12px; border-radius: 8px; border-right: 12px solid #ccc; margin-bottom: 5px; }
    .type-atan { border-right-color: #FFA500; background-color: #FFF8EE; }
    .type-standard { border-right-color: #ADD8E6; background-color: #F0F8FF; }
    .type-backup { border-right-color: #90EE90; background-color: #F5FFF5; }
    
    .shift-title { font-size: 0.9rem; font-weight: bold; }
    .shift-station { font-size: 0.8rem; color: #444; }

    /* התאמת הדיאלוג ל-RTL */
    div[role="dialog"] { direction: rtl; text-align: right; }
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

# --- פונקציות עזר ---
DAYS_HEBREW = {'Sunday': 'ראשון', 'Monday': 'שני', 'Tuesday': 'שלישי', 'Wednesday': 'רביעי', 'Thursday': 'חמישי', 'Friday': 'שישי', 'Saturday': 'שבת'}
def get_day_name(date_str):
    try: return DAYS_HEBREW[datetime.strptime(date_str, '%d/%m/%Y').strftime('%A')]
    except: return ""

def get_shift_style(v_type):
    v_type = str(v_type)
    if "אט" in v_type: return "type-atan"
    if "תקן" in v_type: return "type-standard"
    if "תגבור" in v_type: return "type-backup"
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
    assigned_names = [name for name in schedule_dict.values() if name and "⚠️" not in str(name)]
    if not assigned_names: return 0
    for name in set(assigned_names):
        count = assigned_names.count(name)
        doc_ref = db.collection('employee_history').document(name)
        batch.set(doc_ref, {'total_shifts': firestore.Increment(count), 'last_update': firestore.SERVER_TIMESTAMP}, merge=True)
    batch.commit()
    return len(assigned_names)

def highlight_table_rows(row):
    if row['סטטוס'] == 'חסר': return ['background-color: #ffcccc'] * len(row)
    if row['סטטוס'] == 'בוטל': return ['background-color: #f0f0f0; color: #888'] * len(row)
    if row['סטטוס'] == 'תקין' and row['תחנה (בפועל)'] != row['תחנה (מקורית)'] and row['תחנה (מקורית)'] != '-':
        return ['background-color: #fff3cd'] * len(row)
    return [''] * len(row)

# --- חלונית בחירה (Full-size Dialog) ---
@st.dialog("בחירת עובד למשמרת", width="large")
def show_selection_dialog(shift_key, date_str, station, shift_name, v_type, req_df, history_scores, atan_col, hours_col):
    st.write(f"### שיבוץ: יום {get_day_name(date_str)} | {station} | {shift_name}")
    st.divider()

    already_assigned = st.session_state.assigned_today.get(date_str, set())
    avail_df = req_df[req_df['תאריך מבוקש'] == date_str].copy()
    avail_df = avail_df[~avail_df['שם'].isin(already_assigned)]
    
    if "אט\"ן" in str(v_type):
        avail_df = avail_df[avail_df[atan_col] == 'כן']

    if avail_df.empty:
        st.warning("אין עובדים פנויים.")
    else:
        avail_df['balance'] = avail_df['שם'].map(lambda x: history_scores.get(x, 0))
        avail_df = avail_df.sort_values('balance')
        
        # יצירת אפשרויות ללא סוגריים
        options = []
        for idx, row in avail_df.iterrows():
            label = f"{row['שם']} | מאזן: {row['balance']} | {row['תחנה']} | {row[hours_col]}"
            options.append((label, row['שם']))

        selected_label = st.radio("בחר עובד:", [opt[0] for opt in options], index=None)

        if st.button("אשר שיבוץ", type="primary", use_container_width=True):
            if selected_label:
                selected_name = next(opt[1] for opt in options if opt[0] == selected_label)
                st.session_state.final_schedule[shift_key] = selected_name
                st.session_state.assigned_today.setdefault(date_str, set()).add(selected_name)
                st.rerun()

# --- Session State ---
if 'final_schedule' not in st.session_state: st.session_state.final_schedule = {}
if 'assigned_today' not in st.session_state: st.session_state.assigned_today = {}
if 'cancelled_shifts' not in st.session_state: st.session_state.cancelled_shifts = set()

# --- UI Sidebar ---
with st.sidebar:
    st.header("⚙️ נתונים")
    req_file = st.file_uploader("העלה REQ.csv", type=['csv'])
    shifts_file = st.file_uploader("העלה SHIFTS.csv", type=['csv'])
    if st.button("🧹 איפוס לוח נוכחי", use_container_width=True):
        st.session_state.final_schedule = {}; st.session_state.assigned_today = {}; st.session_state.cancelled_shifts = set()
        st.rerun()

st.title("🛡️ לוח שיבוץ מבצעי")

if req_file and shifts_file:
    req_df = pd.read_csv(req_file, encoding='utf-8-sig')
    shifts_template = pd.read_csv(shifts_file, encoding='utf-8-sig')
    req_df.columns = req_df.columns.str.strip()
    shifts_template.columns = shifts_template.columns.str.strip()
    
    atan_col = [c for c in req_df.columns if "אט" in c and "מורשה" in c][0]
    hours_col = 'שעות'
    dates = sorted(req_df['תאריך מבוקש'].unique())
    history_scores = get_balance_from_db()

    if st.button("🪄 הפעל שיבוץ אוטומטי", type="primary", use_container_width=True):
        temp_schedule = {}; temp_assigned_today = {d: set() for d in dates}
        current_scores = history_scores.copy()
        for date in dates:
            for idx, s_row in shifts_template.iterrows():
                shift_key = f"{date}_{s_row['תחנה']}_{s_row['משמרת']}_{idx}"
                if shift_key in st.session_state.cancelled_shifts: continue
                pot = req_df[(req_df['תאריך מבוקש'] == date) & (req_df['משמרת'] == s_row['משמרת']) & (req_df['תחנה'] == s_row['תחנה'])]
                if "אט\"ן" in str(s_row['סוג תקן']): pot = pot[pot[atan_col] == 'כן']
                pot = pot[~pot['שם'].isin(temp_assigned_today[date])]
                if not pot.empty:
                    pot = pot.copy(); pot['score'] = pot['שם'].map(lambda x: current_scores.get(x, 0))
                    best = pot.sort_values('score').iloc[0]['שם']
                    temp_schedule[shift_key] = best; temp_assigned_today[date].add(best)
                    current_scores[best] = current_scores.get(best, 0) + 1
        st.session_state.final_schedule = temp_schedule; st.session_state.assigned_today = temp_assigned_today
        st.rerun()

    st.divider()
    grid_cols = st.columns(len(dates))
    
    for i, date_str in enumerate(dates):
        with grid_cols[i]:
            # כותרת דביקה (נעוצה)
            st.markdown(f"""
                <div class="sticky-header">
                    <h5>יום {get_day_name(date_str)}</h5>
                    <p>{date_str}</p>
                </div>
            """, unsafe_allow_html=True)
            
            for idx, s_row in shifts_template.iterrows():
                shift_key = f"{date_str}_{s_row['תחנה']}_{s_row['משמרת']}_{idx}"
                is_cancelled = shift_key in st.session_state.cancelled_shifts
                current = st.session_state.final_schedule.get(shift_key)
                
                with st.container(border=True):
                    st.markdown(f'<div class="shift-card {get_shift_style(s_row["סוג תקן"])}"><div class="shift-title">{s_row["משמרת"]} - {s_row["סוג תקן"]}</div><div class="shift-station">{s_row["תחנה"]}</div></div>', unsafe_allow_html=True)
                    
                    if is_cancelled:
                        st.warning("🚫")
                        if st.button("שחזר", key=f"res_{shift_key}"):
                            st.session_state.cancelled_shifts.remove(shift_key); st.rerun()
                    elif current:
                        st.success(f"✅ {current}")
                        if st.button("✖️ הסר", key=f"rem_{shift_key}", use_container_width=True):
                            st.session_state.assigned_today[date_str].discard(current); st.session_state.final_schedule[shift_key] = None; st.rerun()
                    else:
                        st.error("⚠️ חסר")
                        if st.button("➕ בחר", key=f"btn_{shift_key}", use_container_width=True):
                            show_selection_dialog(shift_key, date_str, s_row['תחנה'], s_row['משמרת'], s_row['סוג תקן'], req_df, history_scores, atan_col, hours_col)

    # --- טבלת ריכוז סופית ---
    st.divider()
    st.subheader("📊 בקרת שיבוצים והשוואה")
    summary_data = []
    for date in dates:
        for idx, s_row in shifts_template.iterrows():
            shift_key = f"{date}_{s_row['תחנה']}_{s_row['משמרת']}_{idx}"
            assigned_name = st.session_state.final_schedule.get(shift_key)
            status, req_station, req_hours = "תקין", "-", "-"
            if shift_key in st.session_state.cancelled_shifts: status, assigned_name = "בוטל", "🚫"
            elif not assigned_name: status, assigned_name = "חסר", "⚠️ לא שובץ"
            else:
                user_req = req_df[(req_df['שם'] == assigned_name) & (req_df['תאריך מבוקש'] == date)]
                if not user_req.empty:
                    req_station, req_hours = user_req.iloc[0]['תחנה'], user_req.iloc[0][hours_col]
            summary_data.append({"תאריך": date, "יום": get_day_name(date), "משמרת": s_row['משמרת'], "תחנה (בפועל)": s_row['תחנה'], "שם העובד": assigned_name, "תחנה (מקורית)": req_station, "סטטוס": status})
    
    if summary_data:
        st.dataframe(pd.DataFrame(summary_data).style.apply(highlight_table_rows, axis=1), use_container_width=True, hide_index=True)

    if st.session_state.final_schedule:
        st.divider()
        if st.button("💾 שמירה סופית ועדכון מאזן", type="primary", use_container_width=True):
            count = update_db_balance(st.session_state.final_schedule)
            st.balloons(); st.success(f"נשמר בהצלחה! {count} משמרות עודכנו."); st.session_state.final_schedule = {}
else:
    st.info("אנא העלה קבצים בסרגל הצד.")
