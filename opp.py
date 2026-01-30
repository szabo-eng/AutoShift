import streamlit as st
import pandas as pd
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime

# --- הגדרות דף ---
st.set_page_config(page_title="ניהול שיבוץ - גרסת ניהול", layout="wide")

# --- חיבור ל-Firebase ---
if not firebase_admin._apps:
    try:
        firebase_info = dict(st.secrets["firebase"])
        cred = credentials.Certificate(firebase_info)
        firebase_admin.initialize_app(cred)
    except:
        st.error("שגיאה בחיבור ל-Firebase. בדוק את ה-Secrets.")
db = firestore.client()

# --- עזרי תאריכים ---
DAYS_HEBREW = {
    'Sunday': 'ראשון', 'Monday': 'שני', 'Tuesday': 'שלישי', 
    'Wednesday': 'רביעי', 'Thursday': 'חמישי', 'Friday': 'שישי', 'Saturday': 'שבת'
}

def get_day_name(date_str):
    try:
        date_obj = datetime.strptime(date_str, '%d/%m/%Y')
        return DAYS_HEBREW[date_obj.strftime('%A')]
    except:
        return ""

# --- פונקציות בסיס נתונים ---
def get_balance_from_db():
    scores = {}
    docs = db.collection('employee_history').stream()
    for doc in docs:
        scores[doc.id] = doc.to_dict().get('total_shifts', 0)
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

# --- ניהול זיכרון (Session State) ---
if 'final_schedule' not in st.session_state:
    st.session_state.final_schedule = {}
if 'assigned_today' not in st.session_state:
    st.session_state.assigned_today = {}

# --- פונקציית ניקוי ---
def reset_schedule():
    st.session_state.final_schedule = {}
    st.session_state.assigned_today = {}
    st.toast("השיבוץ נוקה בהצלחה!", icon="🧹")

# --- ממשק משתמש ---
st.title("🗓️ מרכז שליטה ובקרת שיבוץ")

with st.sidebar:
    st.header("⚙️ הגדרות ונתונים")
    req_file = st.file_uploader("העלה קובץ בקשות (REQ)", type=['csv'])
    shifts_file = st.file_uploader("העלה תבנית משמרות (SHIFTS)", type=['csv'])
    
    st.divider()
    if st.button("🧹 נקה את כל השיבוצים", use_container_width=True):
        reset_schedule()

if req_file and shifts_file:
    req_df = pd.read_csv(req_file, encoding='utf-8-sig')
    shifts_template = pd.read_csv(shifts_file, encoding='utf-8-sig')
    req_df.columns = req_df.columns.str.strip()
    shifts_template.columns = shifts_template.columns.str.strip()
    
    atan_col = [c for c in req_df.columns if "אט" in c and "מורשה" in c][0]
    dates = sorted(req_df['תאריך מבוקש'].unique())

    # כפתור הפעלה ראשי
    col_act1, col_act2 = st.columns([1, 4])
    with col_act1:
        if st.button("🪄 שיבוץ אוטומטי", type="primary", use_container_width=True):
            history_scores = get_balance_from_db()
            temp_schedule = {}
            temp_assigned_today = {d: set() for d in dates}

            for date in dates:
                for idx, s_row in shifts_template.iterrows():
                    candidates = req_df[
                        (req_df['תאריך מבוקש'] == date) & 
                        (req_df['משמרת'] == s_row['משמרת']) & 
                        (req_df['תחנה'] == s_row['תחנה'])
                    ]
                    if "אט\"ן" in str(s_row['סוג תקן']):
                        candidates = candidates[candidates[atan_col] == 'כן']
                    
                    candidates = candidates[~candidates['שם'].isin(temp_assigned_today[date])]

                    shift_key = f"{date}_{s_row['תחנה']}_{s_row['משמרת']}_{idx}"
                    if not candidates.empty:
                        candidates = candidates.copy()
                        candidates['score'] = candidates['שם'].map(lambda x: history_scores.get(x, 0))
                        best_name = candidates.sort_values('score').iloc[0]['שם']
                        temp_schedule[shift_key] = best_name
                        temp_assigned_today[date].add(best_name)
                        history_scores[best_name] = history_scores.get(best_name, 0) + 1
                    else:
                        temp_schedule[shift_key] = None
            
            st.session_state.final_schedule = temp_schedule
            st.session_state.assigned_today = temp_assigned_today

    # --- תצוגת הלוח ---
    st.divider()
    grid_cols = st.columns(len(dates))
    
    for i, date_str in enumerate(dates):
        with grid_cols[i]:
            day_name = get_day_name(date_str)
            st.markdown(f"### יום {day_name}\n#### {date_str}")
            
            for idx, s_row in shifts_template.iterrows():
                shift_key = f"{date_str}_{s_row['תחנה']}_{s_row['משמרת']}_{idx}"
                current_assigned = st.session_state.final_schedule.get(shift_key)
                
                with st.container(border=True):
                    st.write(f"**{s_row['משמרת']} | {s_row['תחנה']}**")
                    
                    if current_assigned:
                        st.success(f"✅ {current_assigned}")
                        if st.button("הסר", key=f"rem_{shift_key}"):
                            st.session_state.assigned_today[date_str].remove(current_assigned)
                            st.session_state.final_schedule[shift_key] = None
                            st.rerun()
                    else:
                        st.error("⚠️ לא אויש")
                        potential = req_df[
                            (req_df['תאריך מבוקש'] == date_str) & 
                            (req_df['משמרת'] == s_row['משמרת']) & 
                            (req_df['תחנה'] == s_row['תחנה'])
                        ]
                        assigned_names = st.session_state.assigned_today.get(date_str, set())
                        available = potential[~potential['שם'].isin(assigned_names)]['שם'].tolist()
                        
                        if available:
                            choice = st.selectbox("שיבוץ ידני:", ["--בחר--"] + available, key=f"sel_{shift_key}")
                            if choice != "--בחר--":
                                st.session_state.final_schedule[shift_key] = choice
                                st.session_state.assigned_today.setdefault(date_str, set()).add(choice)
                                st.rerun()

    # --- אישור ועדכון בסיס נתונים ---
    st.divider()
    if st.session_state.final_schedule:
        if st.button("💾 אשר שיבוץ סופי ועדכן היסטוריה ב-Firebase", type="primary", use_container_width=True):
            count = update_db_balance(st.session_state.final_schedule)
            st.balloons()
            st.success(f"השיבוץ ננעל ועודכן! סה\"כ {count} משמרות נוספו למאזן העובדים.")
            # איפוס הזיכרון לאחר שמירה מוצלחת
            st.session_state.final_schedule = {}
            st.session_state.assigned_today = {}

else:
    st.info("אנא העלה קבצים בסרגל הצד כדי להתחיל.")
