import streamlit as st
import pandas as pd
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime

# --- הגדרות דף ---
st.set_page_config(page_title="ניהול שיבוץ - צבעוני", layout="wide")

# --- הזרקת CSS ל-RTL, כותרות דביקות וצבעי משמרות ---
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

    /* עיצוב כרטיסי משמרות לפי סוג תקן */
    .shift-card {
        padding: 8px;
        border-radius: 5px;
        margin-bottom: 5px;
        border-right: 8px solid #ccc; /* ברירת מחדל */
    }
    .type-atan { border-right-color: #FFA500; background-color: #FFF5E6; }   /* כתום */
    .type-standard { border-right-color: #ADD8E6; background-color: #F0F8FF; } /* כחול בהיר */
    .type-backup { border-right-color: #90EE90; background-color: #F5FFF5; }   /* ירוק בהיר */
    
    .shift-card-text { font-size: 0.85rem; line-height: 1.2; font-weight: bold; }
    
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

# --- פונקציות עזר וניהול זיכרון ---
if 'final_schedule' not in st.session_state: st.session_state.final_schedule = {}
if 'assigned_today' not in st.session_state: st.session_state.assigned_today = {}
if 'cancelled_shifts' not in st.session_state: st.session_state.cancelled_shifts = set()

def get_shift_style(v_type):
    v_type = str(v_type)
    if "אט" in v_type: return "type-atan"
    if "תקן" in v_type: return "type-standard"
    if "תגבור" in v_type: return "type-backup"
    return ""

# --- ממשק משתמש ---
st.title("🛡️ לוח בקרה ושיבוץ")

with st.sidebar:
    st.header("⚙️ הגדרות")
    req_file = st.file_uploader("העלה REQ.csv", type=['csv'])
    shifts_file = st.file_uploader("העלה SHIFTS.csv", type=['csv'])
    
    st.markdown("### מקרא צבעים:")
    st.markdown("🟧 **אט\"ן** | 🟦 **תקן** | 🟩 **תגבור**")
    
    if st.button("🧹 נקה לוח שנה", use_container_width=True):
        st.session_state.final_schedule = {}; st.session_state.assigned_today = {}; st.session_state.cancelled_shifts = set()
        st.rerun()

if req_file and shifts_file:
    req_df = pd.read_csv(req_file, encoding='utf-8-sig')
    shifts_template = pd.read_csv(shifts_file, encoding='utf-8-sig')
    req_df.columns = req_df.columns.str.strip()
    shifts_template.columns = shifts_template.columns.str.strip()
    
    atan_col = [c for c in req_df.columns if "אט" in c and "מורשה" in c][0]
    dates = sorted(req_df['תאריך מבוקש'].unique())

    # כפתור שיבוץ אוטומטי (ללא שינוי לוגי)
    if st.button("🪄 בצע שיבוץ אוטומטי", type="primary", use_container_width=True):
        # ... (קוד השיבוץ מהשלב הקודם) ...
        pass

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
                
                v_type = s_row['סוג תקן'] if 'סוג תקן' in s_row else ""
                style_class = get_shift_style(v_type)
                
                with st.container(border=True):
                    # הצגת המשמרת עם עיצוב הצבעים
                    st.markdown(f"""
                        <div class="shift-card {style_class}">
                            <div class="shift-card-text">{s_row['משמרת']} - {v_type}</div>
                            <div style="font-size: 0.8rem; color: #666;">{s_row['תחנה']}</div>
                        </div>
                    """, unsafe_allow_html=True)
                    
                    if is_cancelled:
                        st.warning("🚫")
                        if st.button("שחזר", key=f"res_{shift_key}"):
                            st.session_state.cancelled_shifts.remove(shift_key); st.rerun()
                    elif current:
                        st.success(f"✅ {current}")
                        c1, c2 = st.columns(2)
                        with c1:
                            if st.button("✖️", key=f"rem_{shift_key}", help="הסר"):
                                st.session_state.assigned_today[date_str].discard(current)
                                st.session_state.final_schedule[shift_key] = None; st.rerun()
                        with c2:
                            if st.button("🚫", key=f"can_{shift_key}", help="בטל"):
                                st.session_state.cancelled_shifts.add(shift_key)
                                st.session_state.assigned_today[date_str].discard(current)
                                st.session_state.final_schedule[shift_key] = None; st.rerun()
                    else:
                        st.error("⚠️")
                        pot = req_df[(req_df['תאריך מבוקש'] == date_str) & (req_df['משמרת'] == s_row['משמרת']) & (req_df['תחנה'] == s_row['תחנה'])]
                        if "אט\"ן" in str(v_type): pot = pot[pot[atan_col] == 'כן']
                        
                        avail = pot[~pot['שם'].isin(st.session_state.assigned_today.get(date_str, set()))]['שם'].tolist()
                        if avail:
                            choice = st.selectbox("בחר:", ["-"] + avail, key=f"sel_{shift_key}", label_visibility="collapsed")
                            if choice != "-":
                                st.session_state.final_schedule[shift_key] = choice
                                st.session_state.assigned_today.setdefault(date_str, set()).add(choice); st.rerun()
                        if st.button("🚫 בטל", key=f"bc_{shift_key}", use_container_width=True):
                            st.session_state.cancelled_shifts.add(shift_key); st.rerun()

    # ... (כפתור שמירה סופי) ...
