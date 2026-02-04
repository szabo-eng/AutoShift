import streamlit as st
import pandas as pd
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime

# --- 1. הגדרות דף ועיצוב (RTL, Sticky Headers, Cards) ---
st.set_page_config(page_title="מערכת שיבוץ - חוקים קשיחים 2026", layout="wide")

st.markdown("""
    <style>
    /* יישור לימין ופונטים */
    [data-testid="stAppViewContainer"], [data-testid="stSidebar"], .main { direction: rtl; text-align: right; }
    
    /* כותרות יום נעוצות (Sticky) */
    .sticky-date-header {
        position: -webkit-sticky; position: sticky; top: 2.85rem; 
        background-color: white; z-index: 1000; padding: 12px;
        border-bottom: 4px solid #1f77b4; text-align: center;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1); margin-bottom: 10px;
    }
    .day-name { font-weight: bold; color: #1f77b4; font-size: 1.2rem; display: block; }
    .date-val { font-size: 0.9rem; color: #666; }

    /* עיצוב כרטיסי משמרות */
    .shift-card { 
        padding: 10px; border-radius: 8px; border-right: 10px solid #ccc; 
        margin-bottom: 8px; box-shadow: 1px 1px 3px rgba(0,0,0,0.1);
    }
    .type-atan { border-right-color: #FFA500; background-color: #FFF8EE; }
    .type-standard { border-right-color: #ADD8E6; background-color: #F0F8FF; }

    /* תיקוני ריווח ו-RTL לדיאלוגים */
    [data-testid="stVerticalBlock"] { gap: 0.3rem !important; }
    div[role="dialog"] { direction: rtl; text-align: right; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. אתחול Firebase ---
if not firebase_admin._apps:
    try:
        cred = credentials.Certificate(dict(st.secrets["firebase"]))
        firebase_admin.initialize_app(cred)
    except: st.error("שגיאה בחיבור ל-Firebase. בדוק את ה-Secrets.")
db = firestore.client()

# --- 3. פונקציות עזר ולוגיקה ---
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

def convert_to_csv(df):
    return df.to_csv(index=False).encode('utf-8-sig')

# --- 4. דיאלוג בחירה ידנית (Manual Override) ---
@st.dialog("בחירת עובד זמין (סינון חוקי סף)", width="large")
def show_manual_picker(shift_key, date_str, s_row, req_df, balance):
    st.write(f"### {s_row['משמרת']} | {s_row['תחנה']}")
    
    # אכיפת חוקי סף: תאריך + משמרת + תחנה
    avail = req_df[
        (req_df['תאריך מבוקש'] == date_str) & 
        (req_df['משמרת'] == s_row['משמרת']) & 
        (req_df['תחנה'] == s_row['תחנה'])
    ].copy()
    
    # חוק מניעת כפל שיבוץ
    already_working = st.session_state.assigned_today.get(date_str, set())
    avail = avail[~avail['שם'].isin(already_working)]
    
    # חוק הסמכת אט"ן
    if "אט" in str(s_row['סוג תקן']):
        atan_col = [c for c in req_df.columns if "אט" in c and "מורשה" in c][0]
        avail = avail[avail[atan_col] == 'כן']
    
    if avail.empty:
        st.warning("אין מועמדים העומדים בחוקי הסף למשמרת זו.")
    else:
        avail['bal'] = avail['שם'].map(lambda x: balance.get(x, 0))
        avail = avail.sort_values('bal')
        options = {f"{r['שם']} (מאזן: {int(r['bal'])})": r['שם'] for _, r in avail.iterrows()}
        choice = st.radio("בחר עובד לשיבוץ:", list(options.keys()), index=None)
        
        if st.button("אשר שיבוץ ידני", width='stretch', type="primary"):
            if choice:
                name = options[choice]
                st.session_state.final_schedule[shift_key] = name
                st.session_state.assigned_today.setdefault(date_str, set()).add(name)
                st.rerun()

# --- 5. ניהול Session State ---
for key in ['final_schedule', 'assigned_today', 'cancelled_shifts']:
    if key not in st.session_state: 
        st.session_state[key] = {} if key != 'cancelled_shifts' else set()

# --- 6. ממשק ראשי וטעינה ---
with st.sidebar:
    st.header("⚙️ קבצי נתונים")
    req_f = st.file_uploader("REQ.csv", type=['csv'])
    shi_f = st.file_uploader("SHIFTS.csv", type=['csv'])
    if st.button("🧹 איפוס לוח", width='stretch'):
        st.session_state.clear(); st.rerun()

st.title("🛡️ ניהול שיבוץ: אכיפת חוקי סף והוגנות")

if req_f and shi_f:
    req_df = pd.read_csv(req_f, encoding='utf-8-sig')
    shi_df = pd.read_csv(shi_f, encoding='utf-8-sig')
    req_df.columns = req_df.columns.str.strip()
    shi_df.columns = shi_df.columns.str.strip()
    
    dates = sorted(req_df['תאריך מבוקש'].unique(), key=lambda x: datetime.strptime(x, '%d/%m/%Y'))
    global_balance = get_balance()

    # --- 7. אלגוריתם שיבוץ אוטומטי (Fairness Rule) ---
    if st.button("🪄 הפעל אלגוריתם שיבוץ הוגן", type="primary", width='stretch'):
        with st.spinner("מחשב שיבוץ..."):
            temp_schedule = {}
            temp_assigned_today = {d: set() for d in dates}
            running_balance = global_balance.copy() # עדכון דינמי תוך כדי ריצה
            
            for d in dates:
                for idx, s in shi_df.iterrows():
                    s_key = f"{d}_{s['תחנה']}_{s['משמרת']}_{idx}"
                    if s_key in st.session_state.cancelled_shifts: continue
                    
                    # סינון חוקי סף
                    pot = req_df[
                        (req_df['תאריך מבוקש'] == d) & 
                        (req_df['משמרת'] == s['משמרת']) & 
                        (req_df['תחנה'] == s['תחנה']) &
                        (~req_df['שם'].isin(temp_assigned_today[d]))
                    ]
                    
                    if "אט" in str(s['סוג תקן']):
                        atan_col = [c for c in req_df.columns if "אט" in c and "מורשה" in c][0]
                        pot = pot[pot[atan_col] == 'כן']
                    
                    # שובר שוויון לפי הוגנות
                    if not pot.empty:
                        pot = pot.copy()
                        pot['score'] = pot['שם'].map(lambda x: running_balance.get(x, 0))
                        best = pot.sort_values('score').iloc[0]['שם']
                        
                        temp_schedule[s_key] = best
                        temp_assigned_today[d].add(best)
                        running_balance[best] = running_balance.get(best, 0) + 1 # עדכון זמני בזיכרון
            
            st.session_state.final_schedule = temp_schedule
            st.session_state.assigned_today = temp_assigned_today
            st.rerun()

    st.divider()

    # --- 8. תצוגת לוח (Sticky Headers) ---
    cols = st.columns(len(dates))
    for i, d_str in enumerate(dates):
        with cols[i]:
            st.markdown(f'<div class="sticky-date-header"><span class="day-name">{get_day_name(d_str)}</span><span class="date-val">{d_str}</span></div>', unsafe_allow_html=True)
            for idx, s in shi_df.iterrows():
                s_key = f"{d_str}_{s['תחנה']}_{s['משמרת']}_{idx}"
                assigned = st.session_state.final_schedule.get(s_key)
                cancelled = s_key in st.session_state.cancelled_shifts
                
                style = "type-atan" if "אט" in str(s['סוג תקן']) else "type-standard"
                st.markdown(f'<div class="shift-card {style}"><div class="shift-title">{s["משמרת"]}</div><div class="shift-station">{s["תחנה"]}</div></div>', unsafe_allow_html=True)
                
                if cancelled:
                    st.caption("🚫 מבוטל")
                    if st.button("שחזר", key=f"res_{s_key}", width='stretch'):
                        st.session_state.cancelled_shifts.remove(s_key); st.rerun()
                elif assigned:
                    st.success(f"✅ {assigned}")
                    if st.button("הסר", key=f"rem_{s_key}", width='stretch'):
                        st.session_state.assigned_today[d_str].discard(assigned)
                        st.session_state.final_schedule.pop(s_key); st.rerun()
                else:
                    st.error("⚠️ חסר")
                    c1, c2 = st.columns([3,1])
                    if c1.button("➕ בחר", key=f"add_{s_key}", width='stretch'):
                        show_manual_picker(s_key, d_str, s, req_df, global_balance)
                    if c2.button("🚫", key=f"can_{s_key}", width='stretch'):
                        st.session_state.cancelled_shifts.add(s_key); st.rerun()

    # --- 9. בקרת איכות וייצוא ---
    st.divider()
    summary = []
    for d in dates:
        for idx, s in shi_df.iterrows():
            s_key = f"{d}_{s['תחנה']}_{s['משמרת']}_{idx}"
            assigned = st.session_state.final_schedule.get(s_key)
            status = "תקין"
            if s_key in st.session_state.cancelled_shifts: status, assigned = "בוטל", "🚫"
            elif not assigned: status, assigned = "חסר", "⚠️ חסר"
            summary.append({"תאריך": d, "יום": get_day_name(d), "משמרת": s['משמרת'], "תחנה": s['תחנה'], "עובד": assigned, "סטטוס": status})
    
    if summary:
        st.subheader("📊 דוחות וסיכומים")
        df_sum = pd.DataFrame(summary)
        st.dataframe(df_sum, width='stretch', hide_index=True)
        
        c1, c2 = st.columns(2)
        c1.download_button("📥 הורד סיכום שבועי (Excel)", data=convert_to_csv(df_sum), file_name="weekly_schedule.csv", mime="text/csv", width='stretch')
        
        if c2.button("📈 הורד מאזן היסטורי מה-DB", width='stretch'):
            all_stats = [{"שם עובד": d.id, "משמרות": d.to_dict().get('total_shifts', 0)} for d in db.collection('employee_history').stream()]
            df_stats = pd.DataFrame(all_stats).sort_values("משמרות", ascending=False)
            st.download_button("📥 שמור מאזן מצטבר", data=convert_to_csv(df_stats), file_name="global_balance.csv", mime="text/csv", width='stretch')

    # --- 10. חוק הנעילה ---
    st.divider()
    if st.button("💾 אישור סופי ועדכון Firebase", type="primary", width='stretch'):
        batch = db.batch()
        for name in [v for k, v in st.session_state.final_schedule.items() if v and "⚠️" not in str(v)]:
            batch.set(db.collection('employee_history').document(name), {'total_shifts': firestore.Increment(1)}, merge=True)
        batch.commit()
        st.balloons(); st.success("השיבוץ ננעל והמאזן עודכן!")
else:
    st.info("אנא העלה קבצים כדי להתחיל.")
