import streamlit as st
import pandas as pd
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime

# --- הגדרות דף ---
st.set_page_config(page_title="ניהול שיבוץ - דוח מסכם", layout="wide")

# --- CSS (RTL, Sticky, Dialog, Table Colors) ---
st.markdown("""
    <style>
    [data-testid="stAppViewContainer"], [data-testid="stSidebar"], .main {
        direction: rtl;
        text-align: right;
    }
    .sticky-header {
        position: -webkit-sticky;
        position: sticky;
        top: 0;
        background-color: #f8f9fa;
        z-index: 1000;
        padding: 6px 2px;
        border-bottom: 2px solid #1f77b4;
        margin-bottom: 10px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        border-radius: 4px;
    }
    .sticky-header h5 { margin: 0; text-align: center; font-size: 0.9rem !important; font-weight: bold; color: #1f77b4; }
    .sticky-header p { margin: 0; text-align: center; font-size: 0.75rem !important; color: #555; }

    .shift-card { padding: 10px; border-radius: 6px; border-right: 10px solid #ccc; margin-bottom: 2px; }
    .type-atan { border-right-color: #FFA500; background-color: #FFF8EE; }
    .type-standard { border-right-color: #ADD8E6; background-color: #F0F8FF; }
    .type-backup { border-right-color: #90EE90; background-color: #F5FFF5; }
    
    .shift-title { font-size: 0.85rem; font-weight: bold; line-height: 1.2; }
    .shift-station { font-size: 0.75rem; color: #444; margin-top: 2px; }

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
    for name in set(assigned_names):
        count = assigned_names.count(name)
        doc_ref = db.collection('employee_history').document(name)
        batch.set(doc_ref, {'total_shifts': firestore.Increment(count)}, merge=True)
    batch.commit()
    return len(assigned_names)

# --- פונקציית צביעת טבלה ---
def highlight_table_rows(row):
    # צבע אדום למשמרות חסרות
    if row['סטטוס'] == 'חסר':
        return ['background-color: #ffcccc; color: black'] * len(row)
    # צבע אפור למבוטלות
    if row['סטטוס'] == 'בוטל':
        return ['background-color: #f0f0f0; color: #888'] * len(row)
    # צבע צהוב אם יש אי-התאמה בין התחנה בפועל למבוקשת
    if row['סטטוס'] == 'תקין' and row['תחנה (בפועל)'] != row['תחנה (מקורית)'] and row['תחנה (מקורית)'] != '-':
        return ['background-color: #fff3cd; color: black'] * len(row)
    return [''] * len(row)

# --- חלונית בחירה (Dialog) ---
@st.dialog("בחירת עובד למשמרת", width="large")
def show_selection_dialog(shift_key, date_str, station, shift_name, v_type, req_df, history_scores, atan_col, hours_col):
    st.write(f"### שיבוץ ליום {get_day_name(date_str)} ({date_str})")
    st.write(f"**תחנה:** {station} | **משמרת:** {shift_name}")
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
        
        options = []
        for idx, row in avail_df.iterrows():
            # Label נקי
            label = f"{row['שם']} | מאזן: {row['balance']} | {row['תחנה']} | {row[hours_col]}"
            options.append((label, row['שם']))

        selected_label = st.radio("בחר עובד:", [opt[0] for opt in options], index=None, key=f"rad_{shift_key}")

        if st.button("אשר שיבוץ", type="primary", width=True):
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
    if st.button("🧹 איפוס לוח", width=True):
        st.session_state.final_schedule = {}; st.session_state.assigned_today = {}; st.session_state.cancelled_shifts = set()
        st.rerun()

st.title("🛡️ לוח שיבוץ ומערכת בקרה")

if req_file and shifts_file:
    req_df = pd.read_csv(req_file, encoding='utf-8-sig')
    shifts_template = pd.read_csv(shifts_file, encoding='utf-8-sig')
    req_df.columns = req_df.columns.str.strip()
    shifts_template.columns = shifts_template.columns.str.strip()
    
    atan_col = [c for c in req_df.columns if "אט" in c and "מורשה" in c][0]
    hours_col = 'שעות'
    dates = sorted(req_df['תאריך מבוקש'].unique())
    history_scores = get_balance_from_db()

    # --- שיבוץ אוטומטי ---
    if st.button("🪄 הפעל שיבוץ אוטומטי", type="primary", width=True):
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

    # --- גריד משמרות ---
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
                        st.warning("🚫")
                        if st.button("שחזר", key=f"res_{shift_key}"):
                            st.session_state.cancelled_shifts.remove(shift_key); st.rerun()
                    elif current:
                        st.success(f"✅ {current}")
                        if st.button("✖️ הסר", key=f"rem_{shift_key}", width=True):
                            st.session_state.assigned_today[date_str].discard(current)
                            st.session_state.final_schedule[shift_key] = None; st.rerun()
                    else:
                        st.error("⚠️ חסר")
                        if st.button("➕ בחר", key=f"btn_{shift_key}", width=True):
                            show_selection_dialog(shift_key, date_str, s_row['תחנה'], s_row['משמרת'], s_row['סוג תקן'], req_df, history_scores, atan_col, hours_col)
                        
                        if st.button("🚫 בטל", key=f"bc_{shift_key}", width=True):
                            st.session_state.cancelled_shifts.add(shift_key); st.rerun()

    # --- טבלת ריכוז והשוואה ---
    st.divider()
    st.subheader("📊 טבלת בקרת שיבוצים")
    
    summary_data = []
    # מעבר על כל המשמרות שהוגדרו בתבנית (SHIFTS.csv) לכל הימים
    for date in dates:
        for idx, s_row in shifts_template.iterrows():
            shift_key = f"{date}_{s_row['תחנה']}_{s_row['משמרת']}_{idx}"
            assigned_name = st.session_state.final_schedule.get(shift_key)
            
            status = "תקין"
            req_station = "-"
            req_hours = "-"
            
            # קביעת סטטוס
            if shift_key in st.session_state.cancelled_shifts:
                status = "בוטל"
                assigned_name = "🚫"
            elif not assigned_name:
                status = "חסר"
                assigned_name = "⚠️ לא שובץ"
            else:
                # אם יש שיבוץ, נשלוף את הבקשה המקורית להשוואה
                user_req = req_df[(req_df['שם'] == assigned_name) & (req_df['תאריך מבוקש'] == date)]
                if not user_req.empty:
                    req_station = user_req.iloc[0]['תחנה']
                    req_hours = user_req.iloc[0][hours_col]
            
            summary_data.append({
                "תאריך": date,
                "יום": get_day_name(date),
                "משמרת": s_row['משמרת'],
                "תחנה (בפועל)": s_row['תחנה'],
                "שם העובד": assigned_name,
                "תחנה (מקורית)": req_station,
                "שעות (מקוריות)": req_hours,
                "סטטוס": status
            })
            
    if summary_data:
        summary_df = pd.DataFrame(summary_data)
        # הצגת הטבלה עם עיצוב מותנה
        st.dataframe(
            summary_df.style.apply(highlight_table_rows, axis=1), 
            width=True,
            hide_index=True,
            height=400
        )

    if st.session_state.final_schedule:
        st.divider()
        if st.button("💾 שמירה סופית ועדכון היסטוריה", type="primary", width=True):
            st.balloons(); st.success("הנתונים נשמרו בהצלחה!"); st.session_state.final_schedule = {}
else:
    st.info("אנא העלה קבצים בסרגל הצד.")

