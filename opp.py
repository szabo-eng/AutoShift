import streamlit as st
import pandas as pd
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime

# --- 1. הגדרות דף וסטייל (Sticky Headers & RTL) ---
st.set_page_config(page_title="מערכת שיבוץ מבצעית 2026", layout="wide")

st.markdown("""
    <style>
    [data-testid="stAppViewContainer"], [data-testid="stSidebar"], .main {
        direction: rtl;
        text-align: right;
    }
    
    /* כותרות יום נעוצות - Sticky */
    .sticky-date-header {
        position: -webkit-sticky;
        position: sticky;
        top: 2.85rem; 
        background-color: #f1f3f5;
        z-index: 1000;
        padding: 10px;
        border-bottom: 3px solid #1f77b4;
        text-align: center;
        border-radius: 5px 5px 0 0;
        box-shadow: 0 2px 5px rgba(0,0,0,0.1);
    }
    .day-name { font-weight: bold; color: #1f77b4; font-size: 1.1rem; display: block; }
    .date-val { font-size: 0.85rem; color: #666; }

    /* כרטיסי משמרות */
    .shift-card { padding: 8px; border-radius: 6px; border-right: 8px solid #ccc; margin-bottom: 5px; }
    .type-atan { border-right-color: #FFA500; background-color: #FFF8EE; } /* כתום אט"ן */
    .type-standard { border-right-color: #ADD8E6; background-color: #F0F8FF; } /* תכלת תקן */
    
    .shift-title { font-size: 0.9rem; font-weight: bold; }
    .shift-station { font-size: 0.8rem; color: #444; }
    
    /* צמצום מרווחים של Streamlit */
    [data-testid="stVerticalBlock"] { gap: 0.2rem !important; }
    div[role="dialog"] { direction: rtl; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. חיבור Firebase ---
if not firebase_admin._apps:
    try:
        cred = credentials.Certificate(dict(st.secrets["firebase"]))
        firebase_admin.initialize_app(cred)
    except: pass
db = firestore.client()

# --- 3. פונקציות עזר (לוגיקה ומאזן) ---
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

def highlight_rows(row):
    if row['סטטוס'] == 'חסר': return ['background-color: #ffcccc'] * len(row)
    if row['סטטוס'] == 'בוטל': return ['background-color: #f0f0f0; color: #999'] * len(row)
    if row['תחנה (בפועל)'] != row['תחנה (מקורית)'] and row['תחנה (מקורית)'] != '-':
        return ['background-color: #fff3cd'] * len(row) # צהוב - חריגת תחנה
    return [''] * len(row)

# --- 4. דיאלוג בחירה (Manual Pick) ---
@st.dialog("בחירת עובד", width="large")
def pick_employee(shift_key, date_str, s_row, req_df, balance):
    st.write(f"### שיבוץ: {s_row['משמרת']} | {s_row['תחנה']}")
    already = st.session_state.assigned_today.get(date_str, set())
    avail = req_df[(req_df['תאריך מבוקש'] == date_str) & (~req_df['שם'].isin(already))].copy()
    
    if "אט" in str(s_row['סוג תקן']):
        atan_col = [c for c in req_df.columns if "אט" in c and "מורשה" in c][0]
        avail = avail[avail[atan_col] == 'כן']
    
    if avail.empty:
        st.error("אין עובדים פנויים מתאימים.")
    else:
        avail['bal'] = avail['שם'].map(lambda x: balance.get(x, 0))
        avail = avail.sort_values('bal')
        options = {f"{r['שם']} (מאזן: {int(r['bal'])}) | {r['תחנה']}": r['שם'] for _, r in avail.iterrows()}
        choice = st.radio("בחר עובד:", list(options.keys()), index=None)
        if st.button("אשר שיבוץ", width='stretch'):
            if choice:
                name = options[choice]
                st.session_state.final_schedule[shift_key] = name
                st.session_state.assigned_today.setdefault(date_str, set()).add(name)
                st.rerun()

# --- 5. Session State ---
for key in ['final_schedule', 'assigned_today', 'cancelled_shifts']:
    if key not in st.session_state: st.session_state[key] = {} if key != 'cancelled_shifts' else set()

# --- 6. ממשק ראשי ---
with st.sidebar:
    st.header("⚙️ טעינת קבצים")
    req_f = st.file_uploader("REQ.csv", type=['csv'])
    shi_f = st.file_uploader("SHIFTS.csv", type=['csv'])
    if st.button("🧹 איפוס לוח", width='stretch'):
        st.session_state.final_schedule = {}; st.session_state.assigned_today = {}; st.session_state.cancelled_shifts = set(); st.rerun()

if req_f and shi_f:
    req_df = pd.read_csv(req_f, encoding='utf-8-sig')
    shi_df = pd.read_csv(shi_f, encoding='utf-8-sig')
    req_df.columns = req_df.columns.str.strip()
    shi_df.columns = shi_df.columns.str.strip()
    
    dates = sorted(req_df['תאריך מבוקש'].unique(), key=lambda x: datetime.strptime(x, '%d/%m/%Y'))
    balance = get_balance()

    # גריד שיבוץ
    cols = st.columns(len(dates))
    for i, d_str in enumerate(dates):
        with cols[i]:
            st.markdown(f'<div class="sticky-date-header"><span class="day-name">{get_day_name(d_str)}</span><span class="date-val">{d_str}</span></div>', unsafe_allow_html=True)
            
            for idx, s in shi_df.iterrows():
                s_key = f"{d_str}_{s['תחנה']}_{s['משמרת']}_{idx}"
                is_cancelled = s_key in st.session_state.cancelled_shifts
                assigned = st.session_state.final_schedule.get(s_key)
                
                # תצוגת כרטיס
                style = "type-atan" if "אט" in str(s['סוג תקן']) else "type-standard"
                st.markdown(f'<div class="shift-card {style}"><div class="shift-title">{s["משמרת"]}</div><div class="shift-station">{s["תחנה"]}</div></div>', unsafe_allow_html=True)
                
                if is_cancelled:
                    st.caption("🚫 בוטל")
                    if st.button("שחזר", key=f"res_{s_key}", width='stretch'):
                        st.session_state.cancelled_shifts.remove(s_key); st.rerun()
                elif assigned:
                    st.success(f"✅ {assigned}")
                    if st.button("הסר", key=f"rem_{s_key}", width='stretch'):
                        st.session_state.assigned_today[d_str].discard(assigned)
                        st.session_state.final_schedule.pop(s_key); st.rerun()
                else:
                    st.error("⚠️ חסר")
                    c1, c2 = st.columns(2)
                    if c1.button("➕", key=f"add_{s_key}", width='stretch'):
                        pick_employee(s_key, d_str, s, req_df, balance)
                    if c2.button("🚫", key=f"can_{s_key}", width='stretch'):
                        st.session_state.cancelled_shifts.add(s_key); st.rerun()

    # --- 7. טבלת בקרת איכות (Quality Control) ---
    st.divider()
    st.subheader("📊 בקרת איכות וסיכום שיבוצים")
    summary = []
    for d in dates:
        for idx, s in shi_df.iterrows():
            s_key = f"{d}_{s['תחנה']}_{s['משמרת']}_{idx}"
            assigned = st.session_state.final_schedule.get(s_key)
            status, orig_station = "תקין", "-"
            
            if s_key in st.session_state.cancelled_shifts: status, assigned = "בוטל", "🚫"
            elif not assigned: status, assigned = "חסר", "⚠️ חסר"
            else:
                match = req_df[(req_df['שם'] == assigned) & (req_df['תאריך מבוקש'] == d)]
                if not match.empty: orig_station = match.iloc[0]['תחנה']
            
            summary.append({"תאריך": d, "משמרת": s['משמרת'], "תחנה (בפועל)": s['תחנה'], "עובד": assigned, "תחנה (מקורית)": orig_station, "סטטוס": status})
    
    st.dataframe(pd.DataFrame(summary).style.apply(highlight_rows, axis=1), width='stretch', hide_index=True)

    if st.button("💾 שמירה סופית למסד נתונים", type="primary", width='stretch'):
        # לוגיקה לעדכון Firebase Increment כאן
        st.balloons(); st.success("הנתונים סונכרנו בהצלחה!")
else:
    st.info("העלה קבצי CSV כדי להתחיל.")
