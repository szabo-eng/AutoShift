import streamlit as st
import pandas as pd
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime

# --- 1. הגדרות דף ועיצוב (Full RTL Compatibility) ---
st.set_page_config(page_title="מערכת שיבוץ מבצעית 2026", layout="wide")

st.markdown("""
    <style>
    /* הגדרות RTL גלובליות */
    [data-testid="stAppViewContainer"], [data-testid="stSidebar"], .main { 
        direction: rtl !important; 
        text-align: right !important; 
    }
    
    /* סידור Sidebar מימין לשמאל */
    [data-testid="stSidebar"] [data-testid="stVerticalBlock"] {
        direction: rtl !important;
        text-align: right !important;
    }

    /* הקטנת רוחב ה-Sidebar */
    [data-testid="stSidebar"] {
        min-width: 200px !important;
        max-width: 200px !important;
    }

    /* מכולת הטבלה - הגדרת כיוון Flex ל-row-reverse כדי שהיום הראשון יהיה בימין */
    [data-testid="stHorizontalBlock"] {
        direction: rtl !important;
        overflow-x: auto;
        display: flex;
        flex-direction: row !important; /* Streamlit יסדר לפי הסדר שניתן לו */
        gap: 0 !important; 
        border: 2px solid #444;
        border-radius: 4px;
        background-color: #e9ecef;
    }

    /* עיצוב עמודה כתא בטבלה - גבולות בצד ימין */
    [data-testid="column"] {
        min-width: 280px !important;
        max-width: 280px !important;
        flex: 0 0 280px !important;
        border-right: 1px solid #ccc !important; /* גבול מימין ב-RTL */
        border-left: none !important;
        background-color: #fdfdfd;
        padding: 0 !important;
        margin: 0 !important;
    }

    /* הסרת הגבול מהעמודה האחרונה (השמאלית ביותר) */
    [data-testid="column"]:last-child {
        border-left: 1px solid #ccc !important;
    }

    .table-header {
        background-color: #1f77b4;
        color: white;
        padding: 12px 5px;
        text-align: center;
        border-bottom: 2px solid #444;
    }
    
    .day-name { font-weight: bold; font-size: 1.1rem; display: block; }
    .date-val { font-size: 0.85rem; opacity: 0.9; }

    .shift-container {
        border-bottom: 1px solid #eee;
        padding: 8px;
        min-height: 160px;
    }

    .shift-card { 
        padding: 8px; 
        border-radius: 4px; 
        margin-bottom: 5px; 
        border-right: 6px solid #ccc; /* סימון צבע משמרת בימין */
        background-color: #fff;
        border-top: 1px solid #eee;
        border-left: 1px solid #eee;
        border-bottom: 2px solid #ddd;
        text-align: right;
    }
    
    .type-atan { border-right-color: #FFA500; background-color: #FFF9F0; }
    .type-standard { border-right-color: #2E86C1; background-color: #F0F7FC; }
    
    .shift-info { font-size: 0.85rem; font-weight: bold; color: #222; }

    /* תיקון יישור לדיאלוגים ורכיבי קלט */
    div[role="dialog"] { direction: rtl !important; text-align: right !important; }
    .stRadio div[role="radiogroup"] { text-align: right !important; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. אתחול Firebase ---
if not firebase_admin._apps:
    try:
        cred = credentials.Certificate(dict(st.secrets["firebase"]))
        firebase_admin.initialize_app(cred)
    except: st.error("שגיאה בחיבור ל-Database.")
db = firestore.client()

# --- 3. פונקציות עזר ---
DAYS_HEB = {'Sunday': 'ראשון', 'Monday': 'שני', 'Tuesday': 'שלישי', 'Wednesday': 'רביעי', 'Thursday': 'חמישי', 'Friday': 'שישי', 'Saturday': 'שבת'}
def get_day_name(date_str):
    try: return DAYS_HEB[datetime.strptime(date_str, '%d/%m/%Y').strftime('%A')]
    except: return ""

def get_balance():
    scores = {}
    try:
        for doc in db.collection('employee_history').stream():
            scores[doc.id] = doc.to_dict().get('total_shifts', 0)
    except: pass
    return scores

# --- 4. דיאלוג שיבוץ (RTL) ---
@st.dialog("שיבוץ עובד", width="large")
def show_manual_picker(shift_key, date_str, s_row, req_df, balance):
    st.markdown(f"### שיבוץ ליום {get_day_name(date_str)} ({date_str})")
    st.write(f"**תחנה:** {s_row['תחנה']} | **משמרת:** {s_row['משמרת']}")
    
    avail = req_df[req_df['תאריך מבוקש'] == date_str].copy()
    already_working = st.session_state.assigned_today.get(date_str, set())
    avail = avail[~avail['שם'].isin(already_working)]
    
    if "אט" in str(s_row['סוג תקן']):
        atan_col = [c for c in req_df.columns if "אט" in c and "מורשה" in c][0]
        avail = avail[avail[atan_col] == 'כן']
    
    if avail.empty:
        st.warning("אין מועמדים פנויים.")
    else:
        avail['bal'] = avail['שם'].map(lambda x: balance.get(x, 0))
        avail = avail.sort_values('bal')
        options = {f"👤 {r['שם']} (מאזן: {int(r['bal'])})": r['שם'] for _, r in avail.iterrows()}
        choice = st.radio("בחר עובד:", list(options.keys()), index=None)
        
        if st.button("אישור", use_container_width=True, type="primary"):
            if choice:
                name = options[choice]
                st.session_state.final_schedule[shift_key] = name
                st.session_state.assigned_today.setdefault(date_str, set()).add(name)
                st.rerun()

# --- 5. Session State ---
for key in ['final_schedule', 'assigned_today', 'cancelled_shifts']:
    if key not in st.session_state: 
        st.session_state[key] = {} if key != 'cancelled_shifts' else set()

# --- 6. Sidebar (RTL) ---
with st.sidebar:
    st.title("⚙️ ניהול")
    req_f = st.file_uploader("1. קובץ בקשות", type=['csv'])
    shi_f = st.file_uploader("2. תבנית משמרות", type=['csv'])
    
    if st.button("🧹 איפוס לוח", use_container_width=True):
        st.session_state.clear(); st.rerun()
    
    st.divider()
    if req_f and shi_f:
        if st.button("🪄 שיבוץ אוטומטי", type="primary", use_container_width=True):
            st.session_state.trigger_auto = True
    
    if st.session_state.final_schedule:
        if st.button("💾 שמירה סופית", type="primary", use_container_width=True):
            st.session_state.trigger_save = True

# --- 7. גוף האפליקציה (לוח שיבוץ) ---
st.title("📅 מערכת שיבוץ מבצעית")

if req_f and shi_f:
    req_df = pd.read_csv(req_f, encoding='utf-8-sig')
    shi_df = pd.read_csv(shi_f, encoding='utf-8-sig')
    
    # מיון תאריכים כך שהראשון יהיה בימין (כרונולוגי)
    dates = sorted(req_df['תאריך מבוקש'].unique(), key=lambda x: datetime.strptime(x, '%d/%m/%Y'))
    global_balance = get_balance()

    # (אלגוריתם שיבוץ - נשאר זהה)
    if st.session_state.get('trigger_auto'):
        temp_schedule = {}; temp_assigned_today = {d: set() for d in dates}
        running_balance = global_balance.copy()
        for d in dates:
            for idx, s in shi_df.iterrows():
                s_key = f"{d}_{s['תחנה']}_{s['משמרת']}_{idx}"
                if s_key in st.session_state.cancelled_shifts: continue
                pot = req_df[(req_df['תאריך מבוקש'] == d) & (req_df['משמרת'] == s['משמרת']) & 
                             (req_df['תחנה'] == s['תחנה']) & (~req_df['שם'].isin(temp_assigned_today[d]))]
                if "אט" in str(s['סוג תקן']):
                    atan_col = [c for c in req_df.columns if "אט" in c and "מורשה" in c][0]
                    pot = pot[pot[atan_col] == 'כן']
                if not pot.empty:
                    pot = pot.copy(); pot['score'] = pot['שם'].map(lambda x: running_balance.get(x, 0))
                    best = pot.sort_values('score').iloc[0]['שם']
                    temp_schedule[s_key] = best
                    temp_assigned_today[d].add(best); running_balance[best] = running_balance.get(best, 0) + 1
        st.session_state.final_schedule = temp_schedule; st.session_state.assigned_today = temp_assigned_today
        st.session_state.trigger_auto = False; st.rerun()

    # הצגת הטבלה - העמודה הראשונה ב-List תהיה הימנית ביותר בגלל ה-CSS
    cols = st.columns(len(dates))
    for i, d_str in enumerate(dates):
        with cols[i]:
            st.markdown(f'<div class="table-header"><span class="day-name">{get_day_name(d_str)}</span><span class="date-val">{d_str}</span></div>', unsafe_allow_html=True)
            
            for idx, s in shi_df.iterrows():
                s_key = f"{d_str}_{s['תחנה']}_{s['משמרת']}_{idx}"
                assigned = st.session_state.final_schedule.get(s_key)
                cancelled = s_key in st.session_state.cancelled_shifts
                style = "type-atan" if "אט" in str(s['סוג תקן']) else "type-standard"
                
                st.markdown('<div class="shift-container">', unsafe_allow_html=True)
                st.markdown(f'<div class="shift-card {style}"><div class="shift-info">{s["משמרת"]} | {s["סוג תקן"]}<br>{s["תחנה"]}</div></div>', unsafe_allow_html=True)
                
                if cancelled:
                    st.caption("🚫 בוטל")
                    if st.button("שחזר", key=f"res_{s_key}", use_container_width=True): 
                        st.session_state.cancelled_shifts.remove(s_key); st.rerun()
                elif assigned:
                    st.success(f"👤 {assigned}")
                    if st.button("הסר", key=f"rem_{s_key}", use_container_width=True):
                        st.session_state.assigned_today[d_str].discard(assigned); st.session_state.final_schedule.pop(s_key); st.rerun()
                else:
                    st.error("⚠️ חסר")
                    c1, c2 = st.columns([3,1])
                    if c1.button("➕", key=f"add_{s_key}", use_container_width=True):
                        show_manual_picker(s_key, d_str, s, req_df, global_balance)
                    if c2.button("🚫", key=f"can_{s_key}", use_container_width=True):
                        st.session_state.cancelled_shifts.add(s_key); st.rerun()
                st.markdown('</div>', unsafe_allow_html=True)
else:
    st.info("👈 יש להעלות קבצים בניהול כדי להציג את הלוח.")

