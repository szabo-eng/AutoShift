import streamlit as st
import pandas as pd
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime

# --- הגדרות דף ---
st.set_page_config(page_title="ניהול שיבוץ - גרסה בדוקה", layout="wide")

# --- CSS מעודכן (Sticky Header חזק + RTL) ---
st.markdown("""
    <style>
    [data-testid="stAppViewContainer"], [data-testid="stSidebar"], .main {
        direction: rtl;
        text-align: right;
    }
    
    /* הבטחת הכותרת הדביקה בתוך הטורים */
    .sticky-header {
        position: -webkit-sticky;
        position: sticky;
        top: 0px; /* נצמד לקצה העליון של הקונטיינר שלו */
        background-color: #ffffff;
        z-index: 99;
        padding: 10px;
        border-bottom: 3px solid #1f77b4;
        margin-bottom: 10px;
        box-shadow: 0 2px 5px rgba(0,0,0,0.1);
    }
    
    /* מניעת הסתרה ע"י הסרגל של Streamlit */
    [data-testid="stVerticalBlock"] > div:has(div.sticky-header) {
        position: sticky;
        top: 2.85rem;
        z-index: 100;
    }

    .shift-card { padding: 10px; border-radius: 6px; border-right: 10px solid #ccc; margin-bottom: 5px; }
    .type-atan { border-right-color: #FFA500; background-color: #FFF8EE; }
    .type-standard { border-right-color: #ADD8E6; background-color: #F0F8FF; }
    
    .shift-title { font-size: 0.85rem; font-weight: bold; }
    .shift-station { font-size: 0.75rem; color: #444; }

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
    assigned_names = [name for name in schedule_dict.values() if name and "⚠️" not in str(name)]
    if not assigned_names: return 0
    for name in set(assigned_names):
        count = assigned_names.count(name)
        doc_ref = db.collection('employee_history').document(name)
        batch.set(doc_ref, {'total_shifts': firestore.Increment(count), 'last_update': firestore.SERVER_TIMESTAMP}, merge=True)
    batch.commit()
    return len(assigned_names)

def highlight_table_rows(row):
    if row['סטטוס'] == 'חסר': return ['background-color: #ffcccc; color: black'] * len(row)
    if row['סטטוס'] == 'בוטל': return ['background-color: #f0f0f0; color: #888'] * len(row)
    if row['סטטוס'] == 'תקין' and row['תחנה (בפועל)'] != row['תחנה (מקורית)'] and row['תחנה (מקורית)'] != '-':
        return ['background-color: #fff3cd; color: black'] * len(row)
    return [''] * len(row)

# --- חלונית בחירה (Dialog) ---
@st.dialog("בחירת עובד", width="large")
def show_selection_dialog(shift_key, date_str, station, shift_name, v_type, req_df, history_scores, atan_col, hours_col):
    st.write(f"### שיבוץ: {get_day_name(date_str)} | {station} | {shift_name}")
    st.divider()

    already_assigned = st.session_state.assigned_today.get(date_str, set())
    avail_df = req_df[req_df['תאריך מבוקש'] == date_str].copy()
    avail_df = avail_df[~avail_df['שם'].isin(already_assigned)]
    
    if "אט\"ן" in str(v_type):
        avail_df = avail_df[avail_df[atan_col] == 'כן']

    if avail_df.empty:
        st.warning("אין מחליפים פנויים התואמים לדרישות.")
    else:
        avail_df['balance'] = avail_df['שם'].map(lambda x: history_scores.get(x, 0))
        avail_df = avail_df.sort_values('balance')
        
        # תצוגה נקייה ללא סוגריים: שם | מאזן | תחנה | שעות
        options = []
        for idx, row in avail_df.iterrows():
            label = f"{row['שם']} | מאזן: {row['balance']} | {row['תחנה']} | {row[hours_col]}"
            options.append((label, row['שם']))

        selected_label = st.radio("בחר מהרשימה:", [opt[0] for opt in options], index=None)

        if st.button("בצע שיבוץ", type="primary", use_container_width=True):
            if selected_label:
                selected_name = next(opt[1] for opt in options if opt[0] == selected_label)
                st.session_state.final_schedule[shift_key] = selected_name
                st.session_state.assigned_today.setdefault(date_str, set()).add(selected_name)
                st.rerun()

# --- Session State ---
if 'final_schedule' not in st.session_state: st.session_state.final_schedule = {}
if 'assigned_today' not in st.session_state: st.session_state.assigned_today = {}
if 'cancelled_shifts' not in st.session_state: st.session_state.cancelled_shifts = set()

# --- Sidebar ---
with st.sidebar:
    st.header("⚙️ נתונים")
    req_file = st.file_uploader("העלה REQ.csv", type=['csv'])
    shifts_file = st.file_uploader("העלה SHIFTS.csv", type=['csv'])
    if st.button("🧹 נקה לוח נוכחי", use_container_width=True):
        st.session_state.final_schedule = {}; st.session_state.assigned_today = {}; st.session_state.cancelled_shifts = set()
        st.rerun()

st.title("🛡️ ניהול שיבוץ מבצעי")

if req_file and shifts_file:
    req_df = pd.read_csv(req_file, encoding='utf-8-sig')
    shifts_template = pd.read_csv(shifts_file, encoding='utf-8-sig')
    req_df.columns = req_df.columns.str.strip()
    shifts_template.columns = shifts_template.columns.str.strip()
    
    atan_col = [c for c in req_df.columns if "אט" in c and "מורשה" in c][0]
    hours_col = 'שעות'
    dates = sorted(req_df['תאריך מבוקש'].unique())
    history_scores = get_balance_from_db()

    # --- גריד משמרות עם כותרות דביקות ---
    st.divider()
    grid_cols = st.columns(len(dates))
    
    for i, date_str in enumerate(dates):
        with grid_cols[i]:
            st.markdown(f'<div class="sticky-header"><h5>יום {get_day_name(date_str)}</h5><p>{date_str}</p></div>', unsafe_allow_html=True)
            
            for idx, s_row in shifts_template.iterrows():
                shift_key = f"{date_str}_{s_row['תחנה']}_{s_row['משמרת']}_{idx}"
                is_cancelled = shift_key in st.session_state.cancelled_shifts
                current = st.session_state.final_schedule.get(shift_key)
                
                with st.container(border=True):
                    st.markdown(f'<div class="shift-card {get_shift_style(s_row["סוג תקן"])}"><div class="shift-title">{s_row["משמרת"]} - {s_row["סוג תקן"]}</div><div class="shift-station">{s_row["תחנה"]}</div></div>', unsafe_allow_html=True)
                    
                    if is_cancelled:
                        st.warning("🚫 בוטל")
                        if st.button("שחזר", key=f"res_{shift_key}"):
                            st.session_state.cancelled_shifts.remove(shift_key); st.rerun()
                    elif current:
                        st.success(f"✅ {current}")
                        if st.button("✖️", key=f"rem_{shift_key}"):
                            st.session_state.assigned_today[date_str].discard(current); st.session_state.final_schedule[shift_key] = None; st.rerun()
                    else:
                        st.error("⚠️ חסר")
                        if st.button("➕ בחר", key=f"btn_{shift_key}", use_container_width=True):
                            show_selection_dialog(shift_key, date_str, s_row['תחנה'], s_row['משמרת'], s_row['סוג תקן'], req_df, history_scores, atan_col, hours_col)

    # --- טבלת ריכוז בקרקעית הדף ---
    st.divider()
    st.subheader("📋 ריכוז נתוני שיבוץ")
    
    summary_data = []
    for date in dates:
        for idx, s_row in shifts_template.iterrows():
            shift_key = f"{date}_{s_row['תחנה']}_{s_row['משמרת']}_{idx}"
            assigned_name = st.session_state.final_schedule.get(shift_key)
            status, req_station = "תקין", "-"
            
            if shift_key in st.session_state.cancelled_shifts:
                status, assigned_name = "בוטל", "🚫"
            elif not assigned_name:
                status, assigned_name = "חסר", "⚠️ חסר"
            else:
                user_req = req_df[(req_df['שם'] == assigned_name) & (req_df['תאריך מבוקש'] == date)]
                if not user_req.empty: req_station = user_req.iloc[0]['תחנה']
            
            summary_data.append({
                "תאריך": date,
                "משמרת": s_row['משמרת'],
                "תחנה (בפועל)": s_row['תחנה'],
                "שם": assigned_name,
                "תחנה (מקורית)": req_station,
                "סטטוס": status
            })
    
    if summary_data:
        st.dataframe(pd.DataFrame(summary_data).style.apply(highlight_table_rows, axis=1), use_container_width=True, hide_index=True)

    if st.session_state.final_schedule:
        if st.button("💾 שמירה סופית ועדכון DB", type="primary", use_container_width=True):
            update_db_balance(st.session_state.final_schedule)
            st.balloons(); st.success("נשמר בהצלחה!"); st.session_state.final_schedule = {}
else:
    st.info("אנא העלה קבצים בסרגל הצד.")
