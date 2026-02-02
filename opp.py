import streamlit as st
import pandas as pd
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime

# --- הגדרות דף ---
st.set_page_config(page_title="ניהול שיבוץ - ריכוז נתונים", layout="wide")

# --- הזרקת CSS ---
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
    .sticky-header h5 { margin: 0; text-align: center; font-size: 0.9rem !important; }
    .shift-card { padding: 10px; border-radius: 6px; border-right: 10px solid #ccc; margin-bottom: 2px; }
    .type-atan { border-right-color: #FFA500; background-color: #FFF8EE; }
    .type-standard { border-right-color: #ADD8E6; background-color: #F0F8FF; }
    </style>
    """, unsafe_allow_html=True)

# --- חיבור ל-Firebase ---
if not firebase_admin._apps:
    try:
        firebase_info = dict(st.secrets["firebase"])
        cred = credentials.Certificate(firebase_info)
        firebase_admin.initialize_app(cred)
    except:
        pass
db = firestore.client()

# --- פונקציות עזר ---
DAYS_HEBREW = {'Sunday': 'ראשון', 'Monday': 'שני', 'Tuesday': 'שלישי', 'Wednesday': 'רביעי', 'Thursday': 'חמישי', 'Friday': 'שישי', 'Saturday': 'שבת'}
def get_day_name(date_str):
    try: return DAYS_HEBREW[datetime.strptime(date_str, '%d/%m/%Y').strftime('%A')]
    except: return ""

def get_balance_from_db():
    scores = {}
    try:
        docs = db.collection('employee_history').stream()
        for doc in docs: scores[doc.id] = doc.to_dict().get('total_shifts', 0)
    except: pass
    return scores

# --- דיאלוג בחירה ---
@st.dialog("בחירת עובד למשמרת", width="large")
def show_selection_dialog(shift_key, date_str, station, shift_name, v_type, req_df, history_scores, atan_col, hours_col):
    st.write(f"### שיבוץ: {station} | {shift_name} ({date_str})")
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
        for _, row in avail_df.iterrows():
            label = f"{row['שם']} | מאזן: {row['balance']} | {row['תחנה']} | {row[hours_col]}"
            options.append((label, row['שם']))

        selected_label = st.radio("בחר עובד:", [opt[0] for opt in options], index=None)
        if st.button("אשר שיבוץ", type="primary", use_container_width=True):
            if selected_label:
                selected_name = next(opt[1] for opt in options if opt[0] == selected_label)
                st.session_state.final_schedule[shift_key] = selected_name
                st.session_state.assigned_today.setdefault(date_str, set()).add(selected_name)
                st.rerun()

# --- ניהול Session State ---
if 'final_schedule' not in st.session_state: st.session_state.final_schedule = {}
if 'assigned_today' not in st.session_state: st.session_state.assigned_today = {}
if 'cancelled_shifts' not in st.session_state: st.session_state.cancelled_shifts = set()

# --- Sidebar ---
with st.sidebar:
    req_file = st.file_uploader("העלה REQ.csv", type=['csv'])
    shifts_file = st.file_uploader("העלה SHIFTS.csv", type=['csv'])
    if st.button("🧹 איפוס הכל"):
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

    # לוח עבודה ראשי
    grid_cols = st.columns(len(dates))
    for i, date_str in enumerate(dates):
        with grid_cols[i]:
            st.markdown(f'<div class="sticky-header"><h5>יום {get_day_name(date_str)}</h5><p>{date_str}</p></div>', unsafe_allow_html=True)
            for idx, s_row in shifts_template.iterrows():
                shift_key = f"{date_str}_{s_row['תחנה']}_{s_row['משמרת']}_{idx}"
                current = st.session_state.final_schedule.get(shift_key)
                
                with st.container(border=True):
                    st.markdown(f'<div class="shift-card {"type-atan" if "אט" in str(s_row["סוג תקן"]) else "type-standard"}"><b>{s_row["משמרת"]}</b><br>{s_row["תחנה"]}</div>', unsafe_allow_html=True)
                    if current:
                        st.success(f"✅ {current}")
                        if st.button("✖️", key=f"rm_{shift_key}"):
                            st.session_state.assigned_today[date_str].discard(current); st.session_state.final_schedule[shift_key] = None; st.rerun()
                    else:
                        if st.button("➕ בחר", key=f"b_{shift_key}", use_container_width=True):
                            show_selection_dialog(shift_key, date_str, s_row['תחנה'], s_row['משמרת'], s_row['סוג תקן'], req_df, history_scores, atan_col, hours_col)

    # --- טבלת ריכוז שיבוצים (בתחתית הדף) ---
    st.divider()
    st.subheader("📊 טבלת ריכוז וסטטוס שיבוץ")
    
    summary_data = []
    for date in dates:
        for idx, s_row in shifts_template.iterrows():
            shift_key = f"{date}_{s_row['תחנה']}_{s_row['משמרת']}_{idx}"
            assigned_name = st.session_state.final_schedule.get(shift_key)
            
            orig_req_station = "-"
            orig_req_hours = "-"
            status = "❌ לא שובץ"
            
            if assigned_name:
                status = "✅ שובץ"
                # חיפוש נתוני הבקשה המקוריים של העובד לאותו יום
                user_req = req_df[(req_df['תאריך מבוקש'] == date) & (req_df['שם'] == assigned_name)]
                if not user_req.empty:
                    orig_req_station = user_req.iloc[0]['תחנה']
                    orig_req_hours = user_req.iloc[0][hours_col]

            summary_data.append({
                "תאריך": date,
                "תחנה (בפועל)": s_row['תחנה'],
                "משמרת": s_row['משמרת'],
                "סוג": s_row['סוג תקן'],
                "שם משובץ": assigned_name if assigned_name else "---",
                "סטטוס": status,
                "תחנה מבוקשת": orig_req_station,
                "שעות בקשה": orig_req_hours
            })
    
    summary_df = pd.DataFrame(summary_data)
    
    # עיצוב מותנה: צביעת שורות ריקות באדום
    def highlight_missing(s):
        return ['background-color: #ffcccc' if s['סטטוס'] == "❌ לא שובץ" else '' for _ in s]

    st.dataframe(
        summary_df.style.apply(highlight_missing, axis=1),
        use_container_width=True,
        hide_index=True
    )

    if st.button("💾 שמירה סופית", type="primary", use_container_width=True):
        st.balloons(); st.success("השיבוץ נשמר!")
else:
    st.info("העלה קבצים כדי להתחיל.")
