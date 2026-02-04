import streamlit as st
import pandas as pd
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime

# --- 1. הגדרות דף ועיצוב (RTL & Sticky) ---
st.set_page_config(page_title="מערכת שיבוץ מבצעית 2026", layout="wide")

st.markdown("""
    <style>
    /* הגדרות RTL כלליות */
    [data-testid="stAppViewContainer"], [data-testid="stSidebar"], .main {
        direction: rtl;
        text-align: right;
    }
    
    /* כותרות יום נעוצות (Sticky Headers) */
    .sticky-date-header {
        position: -webkit-sticky;
        position: sticky;
        top: 2.85rem; 
        background-color: #ffffff;
        z-index: 1000;
        padding: 12px;
        border-bottom: 4px solid #1f77b4;
        text-align: center;
        border-radius: 8px 8px 0 0;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        margin-bottom: 10px;
    }
    .day-name { font-weight: bold; color: #1f77b4; font-size: 1.2rem; display: block; }
    .date-val { font-size: 0.9rem; color: #666; }

    /* כרטיסי משמרות מעוצבים */
    .shift-card { 
        padding: 10px; 
        border-radius: 8px; 
        border-right: 10px solid #ccc; 
        margin-bottom: 8px;
        box-shadow: 1px 1px 3px rgba(0,0,0,0.1);
    }
    .type-atan { border-right-color: #FFA500; background-color: #FFF8EE; }
    .type-standard { border-right-color: #ADD8E6; background-color: #F0F8FF; }
    
    .shift-title { font-size: 0.95rem; font-weight: bold; margin-bottom: 2px; }
    .shift-station { font-size: 0.85rem; color: #555; }
    
    /* תיקוני ריווח ל-Streamlit */
    [data-testid="stVerticalBlock"] { gap: 0.3rem !important; }
    div[role="dialog"] { direction: rtl; text-align: right; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. אתחול Firebase ---
if not firebase_admin._apps:
    try:
        cred = credentials.Certificate(dict(st.secrets["firebase"]))
        firebase_admin.initialize_app(cred)
    except Exception as e:
        st.error(f"שגיאה בחיבור ל-Firebase: {e}")
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

def highlight_qc_table(row):
    """צביעת טבלת בקרת האיכות לפי הלוגיקה שהוגדרה"""
    if row['סטטוס'] == 'חסר': return ['background-color: #ffcccc'] * len(row) # אדום
    if row['סטטוס'] == 'בוטל': return ['background-color: #f0f0f0; color: #999'] * len(row) # אפור
    if row['תחנה (בפועל)'] != row['תחנה (מקורית)'] and row['תחנה (מקורית)'] != '-':
        return ['background-color: #fff3cd'] * len(row) # צהוב - חריגה
    return [''] * len(row)

# --- 4. דיאלוג בחירה ידנית ---
@st.dialog("בחירת עובד למשמרת", width="large")
def show_manual_picker(shift_key, date_str, s_row, req_df, balance):
    st.write(f"### {s_row['משמרת']} | {s_row['תחנה']}")
    st.caption(f"יום {get_day_name(date_str)}, {date_str}")
    
    already = st.session_state.assigned_today.get(date_str, set())
    # סינון: רק מי שביקש את היום הזה וטרם שובץ
    avail = req_df[(req_df['תאריך מבוקש'] == date_str) & (~req_df['שם'].isin(already))].copy()
    
    # סינון מורשי אט"ן במידה ונדרש
    if "אט" in str(s_row['סוג תקן']):
        atan_col = [c for c in req_df.columns if "אט" in c and "מורשה" in c][0]
        avail = avail[avail[atan_col] == 'כן']
    
    if avail.empty:
        st.warning("אין עובדים פנויים התואמים לדרישות.")
    else:
        avail['bal'] = avail['שם'].map(lambda x: balance.get(x, 0))
        avail = avail.sort_values('bal') # הוגנות: מאזן נמוך למעלה
        
        options = {f"{r['שם']} (מאזן: {int(r['bal'])}) | ביקש: {r['תחנה']}": r['שם'] for _, r in avail.iterrows()}
        choice = st.radio("בחר עובד מהרשימה:", list(options.keys()), index=None)
        
        if st.button("אישור שיבוץ", width='stretch', type="primary"):
            if choice:
                selected_name = options[choice]
                st.session_state.final_schedule[shift_key] = selected_name
                st.session_state.assigned_today.setdefault(date_str, set()).add(selected_name)
                st.rerun()

# --- 5. ניהול State ---
for key in ['final_schedule', 'assigned_today', 'cancelled_shifts']:
    if key not in st.session_state: 
        st.session_state[key] = {} if key != 'cancelled_shifts' else set()

# --- 6. ממשק משתמש ראשי ---
with st.sidebar:
    st.title("🛡️ הגדרות")
    req_f = st.file_uploader("העלה דרישות (REQ.csv)", type=['csv'])
    shi_f = st.file_uploader("העלה תבנית (SHIFTS.csv)", type=['csv'])
    
    if st.button("🧹 איפוס לוח", width='stretch'):
        st.session_state.final_schedule = {}
        st.session_state.assigned_today = {}
        st.session_state.cancelled_shifts = set()
        st.rerun()

st.title("📅 מערכת שיבוץ ובקרת איכות")

if req_f and shi_f:
    req_df = pd.read_csv(req_f, encoding='utf-8-sig')
    shi_df = pd.read_csv(shi_f, encoding='utf-8-sig')
    req_df.columns = req_df.columns.str.strip()
    shi_df.columns = shi_df.columns.str.strip()
    
    dates = sorted(req_df['תאריך מבוקש'].unique(), key=lambda x: datetime.strptime(x, '%d/%m/%Y'))
    balance = get_balance()

    # --- כפתור שיבוץ אוטומטי ---
    if st.button("🪄 הפעל שיבוץ אוטומטי מלא", type="primary", width='stretch'):
        with st.spinner("מחשב שיבוץ אופטימלי..."):
            temp_schedule = {}
            temp_assigned_today = {d: set() for d in dates}
            curr_bal = balance.copy()
            
            for d in dates:
                for idx, s in shi_df.iterrows():
                    s_key = f"{d}_{s['תחנה']}_{s['משמרת']}_{idx}"
                    if s_key in st.session_state.cancelled_shifts: continue
                    
                    pot = req_df[(req_df['תאריך מבוקש'] == d) & 
                                 (req_df['תחנה'] == s['תחנה']) & 
                                 (~req_df['שם'].isin(temp_assigned_today[d]))]
                    
                    if "אט" in str(s['סוג תקן']):
                        atan_col = [c for c in req_df.columns if "אט" in c and "מורשה" in c][0]
                        pot = pot[pot[atan_col] == 'כן']
                    
                    if not pot.empty:
                        pot = pot.copy()
                        pot['score'] = pot['שם'].map(lambda x: curr_bal.get(x, 0))
                        best = pot.sort_values('score').iloc[0]['שם']
                        temp_schedule[s_key] = best
                        temp_assigned_today[d].add(best)
                        curr_bal[best] = curr_bal.get(best, 0) + 1
            
            st.session_state.final_schedule = temp_schedule
            st.session_state.assigned_today = temp_assigned_today
            st.rerun()

    st.divider()

    # --- 7. גריד שיבוץ (עם Sticky Headers) ---
    cols = st.columns(len(dates))
    for i, d_str in enumerate(dates):
        with cols[i]:
            # כותרת יום נעוצה
            st.markdown(f"""
                <div class="sticky-date-header">
                    <span class="day-name">{get_day_name(d_str)}</span>
                    <span class="date-val">{d_str}</span>
                </div>
            """, unsafe_allow_html=True)
            
            for idx, s in shi_df.iterrows():
                s_key = f"{d_str}_{s['תחנה']}_{s['משמרת']}_{idx}"
                assigned = st.session_state.final_schedule.get(s_key)
                cancelled = s_key in st.session_state.cancelled_shifts
                
                # עיצוב כרטיס לפי סוג תקן
                card_style = "type-atan" if "אט" in str(s['סוג תקן']) else "type-standard"
                st.markdown(f"""
                    <div class="shift-card {card_style}">
                        <div class="shift-title">{s['משמרת']}</div>
                        <div class="shift-station">{s['תחנה']}</div>
                    </div>
                """, unsafe_allow_html=True)
                
                if cancelled:
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
                        show_manual_picker(s_key, d_str, s, req_df, balance)
                    if c2.button("🚫", key=f"can_{s_key}", width='stretch'):
                        st.session_state.cancelled_shifts.add(s_key); st.rerun()

    # --- 8. טבלת בקרת איכות (QC) ---
    st.divider()
    st.subheader("📊 בקרת איכות וסיכום סופי")
    
    summary_data = []
    for d in dates:
        for idx, s in shi_df.iterrows():
            s_key = f"{d}_{s['תחנה']}_{s['משמרת']}_{idx}"
            assigned = st.session_state.final_schedule.get(s_key)
            status, orig_station = "תקין", "-"
            
            if s_key in st.session_state.cancelled_shifts: 
                status, assigned = "בוטל", "🚫"
            elif not assigned: 
                status, assigned = "חסר", "⚠️ חסר"
            else:
                match = req_df[(req_df['שם'] == assigned) & (req_df['תאריך מבוקש'] == d)]
                if not match.empty: orig_station = match.iloc[0]['תחנה']
            
            summary_data.append({
                "תאריך": d, "משמרת": s['משמרת'], "תחנה (בפועל)": s['תחנה'], 
                "עובד": assigned, "תחנה (מקורית)": orig_station, "סטטוס": status
            })
    
    if summary_data:
        df_sum = pd.DataFrame(summary_data)
        st.dataframe(df_sum.style.apply(highlight_qc_table, axis=1), width='stretch', hide_index=True)

    # --- 9. שמירה סופית ל-Firebase ---
    st.divider()
    if st.button("💾 שמירה סופית ועדכון מאזנים", type="primary", width='stretch'):
        batch = db.batch()
        count = 0
        for name in [v for k, v in st.session_state.final_schedule.items() if v and "⚠️" not in str(v)]:
            doc_ref = db.collection('employee_history').document(name)
            batch.set(doc_ref, {'total_shifts': firestore.Increment(1)}, merge=True)
            count += 1
        batch.commit()
        st.balloons()
        st.success(f"נשמרו {count} שיבוצים. המאזנים עודכנו בהצלחה!")
else:
    st.info("אנא העלה את קבצי ה-CSV בסרגל הצד כדי להתחיל.")
