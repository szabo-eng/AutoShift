import streamlit as st
import pandas as pd
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime

# --- 1. הגדרות דף ועיצוב (Grid/Table with Internal Borders) ---
st.set_page_config(page_title="מערכת שיבוץ מבצעית 2026", layout="wide")

st.markdown("""
    <style>
    /* הגדרות RTL */
    [data-testid="stAppViewContainer"], [data-testid="stSidebar"], .main { 
        direction: rtl; 
        text-align: right; 
    }
    
    /* Sidebar מצומצם */
    [data-testid="stSidebar"] {
        min-width: 220px !important;
        max-width: 220px !important;
    }

    /* מכולת הטבלה הראשית */
    [data-testid="stHorizontalBlock"] {
        overflow-x: auto;
        display: flex;
        flex-wrap: nowrap;
        gap: 0 !important; 
        border: 2px solid #bdc3c7; /* גבול חיצוני עבה יותר */
        border-radius: 4px;
    }

    /* עמודת יום (תא אנכי) */
    [data-testid="column"] {
        min-width: 280px !important;
        max-width: 280px !important;
        flex: 0 0 280px !important;
        border-left: 1px solid #bdc3c7; /* גבול פנימי אנכי */
        margin: 0 !important;
        padding: 0 !important;
        background-color: #ffffff;
    }

    /* כותרת יום */
    .table-header {
        background-color: #ecf0f1;
        padding: 12px;
        border-bottom: 2px solid #2980b9;
        text-align: center;
        font-weight: bold;
    }

    /* תא משמרת פנימי */
    .shift-cell {
        border-bottom: 1px solid #ecf0f1; /* גבול פנימי אופקי */
        padding: 10px;
        transition: background-color 0.2s;
    }
    .shift-cell:hover {
        background-color: #fdfdfe;
    }

    /* כרטיס המשמרת עצמו */
    .shift-card { 
        padding: 8px; 
        border-radius: 4px; 
        border-right: 6px solid #ccc; 
        background-color: #fff;
        border: 1px solid #dcdde1;
        border-right-width: 6px;
        margin-bottom: 5px;
    }
    .type-atan { border-right-color: #e67e22; }
    .type-standard { border-right-color: #3498db; }
    .shift-info { font-size: 0.85rem; font-weight: bold; color: #2c3e50; }
    
    /* ביטול ריווחים של Streamlit */
    [data-testid="stVerticalBlock"] { gap: 0rem !important; }
    .stButton button { margin-top: 2px; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. אתחול Firebase ---
if not firebase_admin._apps:
    try:
        cred = credentials.Certificate(dict(st.secrets["firebase"]))
        firebase_admin.initialize_app(cred)
    except: st.error("שגיאה בחיבור ל-Firebase.")
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

def convert_df_to_csv(df):
    return df.to_csv(index=False).encode('utf-8-sig')

# --- 4. דיאלוג בחירה ידנית ---
@st.dialog("שיבוץ עובד", width="large")
def show_manual_picker(shift_key, date_str, s_row, req_df, balance):
    st.write(f"### {s_row['משמרת']} | {s_row['תחנה']}")
    avail = req_df[req_df['תאריך מבוקש'] == date_str].copy()
    already_working = st.session_state.assigned_today.get(date_str, set())
    avail = avail[~avail['שם'].isin(already_working)]
    if "אט" in str(s_row['סוג תקן']):
        atan_col = [c for c in req_df.columns if "אט" in c and "מורשה" in c][0]
        avail = avail[avail[atan_col] == 'כן']
    
    if avail.empty:
        st.warning("אין מועמדים זמינים.")
    else:
        avail['bal'] = avail['שם'].map(lambda x: balance.get(x, 0))
        avail = avail.sort_values('bal')
        options = {f"👤 {r['שם']} (מאזן: {int(r['bal'])})": r['שם'] for _, r in avail.iterrows()}
        choice = st.radio("בחר עובד:", list(options.keys()), index=None)
        if st.button("אשר שיבוץ", width='stretch', type="primary"):
            if choice:
                name = options[choice]
                st.session_state.final_schedule[shift_key] = name
                st.session_state.assigned_today.setdefault(date_str, set()).add(name)
                st.rerun()

# --- 5. Session State ---
for key in ['final_schedule', 'assigned_today', 'cancelled_shifts']:
    if key not in st.session_state: 
        st.session_state[key] = {} if key != 'cancelled_shifts' else set()

# --- 6. Sidebar (ניהול וייצוא) ---
with st.sidebar:
    st.title("⚙️ ניהול")
    req_f = st.file_uploader("בקשות REQ", type=['csv'])
    shi_f = st.file_uploader("תבנית SHIFTS", type=['csv'])
    
    if st.button("🧹 איפוס לוח", width='stretch'):
        st.session_state.clear(); st.rerun()
    
    st.divider()
    if req_f and shi_f:
        if st.button("🪄 שיבוץ אוטומטי", type="primary", width='stretch'):
            st.session_state.trigger_auto = True
    
    if st.session_state.final_schedule:
        if st.button("💾 שמור ל-DB", type="primary", width='stretch'):
            st.session_state.trigger_save = True

    st.divider()
    st.subheader("📥 ייצוא לאקסל")
    if st.session_state.final_schedule:
        weekly_data = [{"תאריך": k.split('_')[0], "תחנה": k.split('_')[1], "משמרת": k.split('_')[2], "עובד": v} 
                        for k, v in st.session_state.final_schedule.items()]
        st.download_button("📊 סיכום שבועי", data=convert_df_to_csv(pd.DataFrame(weekly_data)), 
                           file_name="weekly_schedule.csv", mime="text/csv")

    if st.button("🔍 שליפת מאזן מה-DB", width='stretch'):
        docs = list(db.collection('employee_history').stream())
        if docs:
            df_hist = pd.DataFrame([{"שם": d.id, "משמרות": d.to_dict().get('total_shifts', 0)} for d in docs])
            st.session_state.hist_report = df_hist.sort_values("משמרות", ascending=False)

    if 'hist_report' in st.session_state:
        st.download_button("📜 הורד מאזן כללי", data=convert_df_to_csv(st.session_state.hist_report), 
                           file_name="global_history.csv", mime="text/csv")

# --- 7. גוף האפליקציה (טבלת המשמרות) ---
st.title("📅 לוח שיבוץ מבצעי")

if req_f and shi_f:
    req_df = pd.read_csv(req_f, encoding='utf-8-sig')
    shi_df = pd.read_csv(shi_f, encoding='utf-8-sig')
    req_df.columns = req_df.columns.str.strip()
    shi_df.columns = shi_df.columns.str.strip()
    
    dates = sorted(req_df['תאריך מבוקש'].unique(), key=lambda x: datetime.strptime(x, '%d/%m/%Y'))
    global_balance = get_balance()

    # שיבוץ אוטומטי ושמירה (לוגיקה קיימת)
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

    if st.session_state.get('trigger_save'):
        batch = db.batch()
        for name in [v for k, v in st.session_state.final_schedule.items() if v]:
            batch.set(db.collection('employee_history').document(name), {'total_shifts': firestore.Increment(1)}, merge=True)
        batch.commit(); st.session_state.trigger_save = False; st.balloons(); st.success("נשמר!")

    # הצגת הטבלה עם גבולות פנימיים
    cols = st.columns(len(dates))
    for i, d_str in enumerate(dates):
        with cols[i]:
            # כותרת היום
            st.markdown(f'<div class="table-header"><div class="day-name">{get_day_name(d_str)}</div><div class="date-val">{d_str}</div></div>', unsafe_allow_html=True)
            
            # מעבר על המשמרות
            for idx, s in shi_df.iterrows():
                s_key = f"{d_str}_{s['תחנה']}_{s['משמרת']}_{idx}"
                assigned = st.session_state.final_schedule.get(s_key)
                cancelled = s_key in st.session_state.cancelled_shifts
                style = "type-atan" if "אט" in str(s['סוג תקul']) else "type-standard"
                
                # פתיחת תא משמרת (Cell)
                st.markdown('<div class="shift-cell">', unsafe_allow_html=True)
                
                st.markdown(f'<div class="shift-card {style}"><div class="shift-info">{s["משמרת"]} {s["סוג תקן"]} {s["תחנה"]}</div></div>', unsafe_allow_html=True)
                
                if cancelled:
                    st.caption("🚫 מבוטל")
                    if st.button("שחזר", key=f"res_{s_key}", width='stretch'): 
                        st.session_state.cancelled_shifts.remove(s_key); st.rerun()
                elif assigned:
                    st.success(f"✅ {assigned}")
                    if st.button("הסר", key=f"rem_{s_key}", width='stretch'):
                        st.session_state.assigned_today[d_str].discard(assigned); st.session_state.final_schedule.pop(s_key); st.rerun()
                else:
                    st.error("⚠️ חסר")
                    c1, c2 = st.columns([4,1])
                    if c1.button("➕", key=f"add_{s_key}", width='stretch'): show_manual_picker(s_key, d_str, s, req_df, global_balance)
                    if c2.button("🚫", key=f"can_{s_key}", width='stretch'): st.session_state.cancelled_shifts.add(s_key); st.rerun()
                
                st.markdown('</div>', unsafe_allow_html=True) # סגירת תא משמרת
else:
    st.info("👈 טען קבצים בניהול כדי להציג את היומן.")
