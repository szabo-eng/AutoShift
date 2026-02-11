"""
מערכת שיבוץ מבצעית 2026 - תצוגת לוח שנה בטבלה
שורה ראשונה: ימים ותאריכים (קבועה)
שורות נוספות: משמרות
"""

import streamlit as st
import pandas as pd
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

REQUIRED_REQUEST_COLUMNS = ['שם', 'תאריך מבוקש', 'משמרת', 'תחנה']
REQUIRED_SHIFT_COLUMNS = ['תחנה', 'משמרת', 'סוג תקן']
DAYS_HEB = {
    'Sunday': 'ראשון', 'Monday': 'שני', 'Tuesday': 'שלישי',
    'Wednesday': 'רביעי', 'Thursday': 'חמישי', 'Friday': 'שישי', 'Saturday': 'שבת'
}
DATE_FORMATS = ['%d/%m/%Y', '%Y-%m-%d', '%d-%m-%Y']

st.set_page_config(page_title="מערכת שיבוץ מבצעית 2026", page_icon="📅", layout="wide")

# CSS מותאם ללוח שנה
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Heebo:wght@300;400;500;600;700;800&family=Rubik:wght@400;500;600;700&display=swap');

html, body, [class*="css"] { font-family: 'Heebo', sans-serif; }
[data-testid="stAppViewContainer"], [data-testid="stSidebar"], [data-testid="stMain"] {
    direction: rtl !important; text-align: right !important;
}
[data-testid="stAppViewContainer"] { background: linear-gradient(135deg, #faf8f5 0%, #f4f1ed 100%); }

h1 {
    font-family: 'Rubik', sans-serif !important; font-weight: 800 !important;
    background: linear-gradient(135deg, #1a4d7a 0%, #2e6ba8 100%);
    -webkit-background-clip: text !important; -webkit-text-fill-color: transparent !important;
}

.stButton > button {
    border-radius: 8px !important; font-weight: 600 !important; font-size: 0.85rem !important;
    padding: 0.5rem 0.75rem !important;
}
.stButton > button[kind="primary"] {
    background: linear-gradient(135deg, #1a4d7a 0%, #2e6ba8 100%) !important;
}

/* טבלת לוח השנה */
.calendar-table {
    width: 100%; border-collapse: separate; border-spacing: 0;
    background: white; border-radius: 16px; overflow: hidden;
    box-shadow: 0 4px 24px rgba(26, 77, 122, 0.1);
}

.calendar-table thead {
    position: sticky; top: 0; z-index: 100;
    background: linear-gradient(135deg, #1a4d7a 0%, #2e6ba8 100%);
}

.calendar-table th {
    padding: 1.5rem 0.75rem; text-align: center; color: white;
    font-family: 'Rubik', sans-serif; border-left: 1px solid rgba(255,255,255,0.1);
    min-width: 140px;
}

.calendar-table th:first-child { border-left: none; }

.day-name { font-size: 1.2rem; font-weight: 700; display: block; margin-bottom: 0.25rem; }
.day-date { font-size: 0.85rem; opacity: 0.9; }

.calendar-table td {
    padding: 0.75rem; border-top: 1px solid #e8e4df; border-left: 1px solid #e8e4df;
    vertical-align: top; background: white;
}

.calendar-table td:first-child { border-left: none; }
.calendar-table tbody tr:first-child td { border-top: none; }

/* כרטיס משמרת קומפקטי */
.shift-mini {
    background: linear-gradient(135deg, #fff 0%, #f9f9f9 100%);
    padding: 0.6rem; border-radius: 8px; border-right: 4px solid #1a4d7a;
    margin-bottom: 0.6rem; transition: all 0.2s;
    box-shadow: 0 1px 3px rgba(0,0,0,0.05);
}

.shift-mini:hover { transform: translateX(-3px); box-shadow: 0 2px 6px rgba(0,0,0,0.1); }
.shift-mini:last-child { margin-bottom: 0; }
.shift-mini.atan { border-right-color: #e67e22; background: linear-gradient(135deg, #fff9f0 0%, #fef5e7 100%); }

.shift-top { display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.4rem; }
.shift-title { font-weight: 700; font-size: 0.95rem; color: #1a4d7a; font-family: 'Rubik', sans-serif; }
.shift-mini.atan .shift-title { color: #e67e22; }

.shift-badge {
    padding: 0.15rem 0.5rem; border-radius: 10px; font-size: 0.65rem; font-weight: 600;
    background: rgba(26, 77, 122, 0.1); color: #1a4d7a;
}
.shift-mini.atan .shift-badge { background: rgba(230, 126, 34, 0.1); color: #e67e22; }

.shift-station { color: #7f8c8d; font-size: 0.8rem; margin-bottom: 0.4rem; }

.shift-status {
    padding: 0.4rem; border-radius: 6px; font-weight: 600; font-size: 0.8rem;
    display: flex; align-items: center; gap: 0.3rem;
}

.status-assigned { background: rgba(39, 174, 96, 0.1); color: #27ae60; }
.status-empty { background: rgba(231, 76, 60, 0.1); color: #e74c3c; }
.status-cancelled { background: rgba(127, 140, 141, 0.1); color: #7f8c8d; }

.calendar-wrapper {
    max-height: 70vh; overflow-y: auto; border-radius: 16px;
}

.calendar-wrapper::-webkit-scrollbar { width: 8px; }
.calendar-wrapper::-webkit-scrollbar-track { background: #f4f1ed; border-radius: 10px; }
.calendar-wrapper::-webkit-scrollbar-thumb { background: rgba(26, 77, 122, 0.3); border-radius: 10px; }
</style>
""", unsafe_allow_html=True)

# Firebase
def initialize_firebase():
    if not firebase_admin._apps:
        try:
            cred = credentials.Certificate(dict(st.secrets["firebase"]))
            firebase_admin.initialize_app(cred)
        except:
            return None
    return firestore.client()

db = initialize_firebase()

# פונקציות
def parse_date_safe(date_str):
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(str(date_str).strip(), fmt)
        except ValueError:
            continue
    raise ValueError(f"פורמט תאריך לא תקין: {date_str}")

def get_day_name(date_str):
    try:
        return DAYS_HEB.get(parse_date_safe(date_str).strftime('%A'), "")
    except:
        return ""

def validate_dataframes(req_df, shi_df):
    errors = []
    if set(REQUIRED_REQUEST_COLUMNS) - set(req_df.columns):
        errors.append("❌ עמודות חסרות בקובץ בקשות")
    if set(REQUIRED_SHIFT_COLUMNS) - set(shi_df.columns):
        errors.append("❌ עמודות חסרות בתבנית משמרות")
    return errors

def get_atan_column(df):
    cols = [c for c in df.columns if "אט" in c and "מורשה" in c]
    return cols[0] if cols else None

@st.cache_data(ttl=60)
def get_balance():
    scores = {}
    try:
        if db:
            for doc in db.collection('employee_history').stream():
                scores[doc.id] = doc.to_dict().get('total_shifts', 0)
    except:
        pass
    return scores

def auto_assign(dates, shi_df, req_df, balance):
    temp_schedule, temp_assigned = {}, {d: set() for d in dates}
    running_balance = balance.copy()
    atan_col = get_atan_column(req_df)
    
    for date_str in dates:
        for idx, shift_row in shi_df.iterrows():
            shift_key = f"{date_str}_{shift_row['תחנה']}_{shift_row['משמרת']}_{idx}"
            if shift_key in st.session_state.cancelled_shifts:
                continue
            
            potential = req_df[
                (req_df['תאריך מבוקש'] == date_str) &
                (req_df['משמרת'] == shift_row['משמרת']) &
                (req_df['תחנה'] == shift_row['תחנה']) &
                (~req_df['שם'].isin(temp_assigned[date_str]))
            ].copy()
            
            if "אט" in str(shift_row['סוג תקן']) and atan_col:
                potential = potential[potential[atan_col] == 'כן']
            
            if not potential.empty:
                potential['score'] = potential['שם'].map(lambda x: running_balance.get(x, 0))
                best = potential.sort_values('score').iloc[0]['שם']
                temp_schedule[shift_key] = best
                temp_assigned[date_str].add(best)
                running_balance[best] = running_balance.get(best, 0) + 1
    
    return temp_schedule, temp_assigned

@st.dialog("שיבוץ עובד")
def show_assignment_dialog(shift_key, date_str, station, shift_type, req_df, balance, shi_df):
    st.markdown(f"### {get_day_name(date_str)} - {date_str}")
    st.write(f"**{station}** | **{shift_type}**")
    
    # בדיקה בטוחה של assigned_today
    if not isinstance(st.session_state.assigned_today, dict):
        st.session_state.assigned_today = {}
    
    already_working = st.session_state.assigned_today.get(date_str, set())
    candidates = req_df[
        (req_df['תאריך מבוקש'] == date_str) &
        (req_df['משמרת'] == shift_type) &
        (req_df['תחנה'] == station) &
        (~req_df['שם'].isin(already_working))
    ].copy()
    
    # בדיקת אט"ן - חיפוש המשמרת בתבנית
    shift_row = None
    for idx, s in shi_df.iterrows():
        test_key = f"{date_str}_{s['תחנה']}_{s['משמרת']}_{idx}"
        if test_key == shift_key:
            shift_row = s
            break
    
    if shift_row is not None and "אט" in str(shift_row['סוג תקן']):
        atan_col = get_atan_column(req_df)
        if atan_col:
            candidates = candidates[candidates[atan_col] == 'כן']
    
    if candidates.empty:
        st.warning("😕 אין מועמדים פנויים")
        if st.button("סגור", type="secondary", use_container_width=True):
            st.rerun()
    else:
        candidates['balance'] = candidates['שם'].map(lambda x: balance.get(x, 0))
        candidates = candidates.sort_values('balance')
        
        selected = st.radio(
            "בחר עובד:",
            options=candidates['שם'].tolist(),
            format_func=lambda x: f"👤 {x} (מאזן: {balance.get(x, 0)})",
            key=f"radio_{shift_key}"
        )
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("✅ אישור", type="primary", use_container_width=True):
                st.session_state.final_schedule[shift_key] = selected
                if date_str not in st.session_state.assigned_today:
                    st.session_state.assigned_today[date_str] = set()
                st.session_state.assigned_today[date_str].add(selected)
                st.success(f"✅ {selected} שובץ/ה!")
                st.rerun()
        with col2:
            if st.button("❌ ביטול", use_container_width=True):
                st.rerun()

# Session State
if 'final_schedule' not in st.session_state:
    st.session_state.final_schedule = {}
if 'assigned_today' not in st.session_state:
    st.session_state.assigned_today = {}
if 'cancelled_shifts' not in st.session_state:
    st.session_state.cancelled_shifts = set()
if 'current_shifts_df' not in st.session_state:
    st.session_state.current_shifts_df = None

# Sidebar
with st.sidebar:
    st.markdown("# ⚙️ ניהול")
    req_file = st.file_uploader("📁 קובץ בקשות", type=['csv'])
    shi_file = st.file_uploader("📋 תבנית משמרות", type=['csv'])
    
    st.divider()
    
    if req_file and shi_file:
        if st.button("🪄 שיבוץ אוטומטי", type="primary", use_container_width=True):
            st.session_state.trigger_auto = True
            st.rerun()
    
    if st.session_state.final_schedule:
        if st.button("💾 שמירה", type="primary", use_container_width=True):
            st.success("✅ נשמר!")
        
        if st.button("📥 ייצוא", use_container_width=True):
            export_data = []
            for shift_key, employee in st.session_state.final_schedule.items():
                parts = shift_key.split('_')
                export_data.append({'תאריך': parts[0], 'תחנה': parts[1], 'משמרת': parts[2], 'עובד': employee})
            csv = pd.DataFrame(export_data).to_csv(index=False, encoding='utf-8-sig')
            st.download_button("⬇️ הורד", csv, f"shibutz_{datetime.now().strftime('%Y%m%d')}.csv", use_container_width=True)
    
    if st.button("🧹 איפוס", use_container_width=True):
        st.session_state.clear()
        st.rerun()

# Main
st.title("📅 לוח שיבוצים")

if req_file and shi_file:
    try:
        req_df = pd.read_csv(req_file, encoding='utf-8-sig')
        shi_df = pd.read_csv(shi_file, encoding='utf-8-sig')
        
        errors = validate_dataframes(req_df, shi_df)
        if errors:
            for e in errors: st.error(e)
            st.stop()
        
        dates = sorted(req_df['תאריך מבוקש'].unique(), key=parse_date_safe)
        balance = get_balance()
        st.session_state.current_shifts_df = shi_df
        
        if st.session_state.get('trigger_auto'):
            with st.spinner('מבצע שיבוץ...'):
                temp_schedule, temp_assigned = auto_assign(dates, shi_df, req_df, balance)
                st.session_state.final_schedule, st.session_state.assigned_today = temp_schedule, temp_assigned
                st.session_state.trigger_auto = False
            st.success(f"✅ {len(st.session_state.final_schedule)} משמרות שובצו")
            st.rerun()
        
        # מדדים
        if st.session_state.final_schedule:
            total = len(shi_df) * len(dates) - len(st.session_state.cancelled_shifts)
            assigned = len(st.session_state.final_schedule)
            
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("סך משמרות", total)
            c2.metric("משובצות", assigned)
            c3.metric("חסרות", total - assigned)
            c4.metric("השלמה", f"{assigned/total*100:.0f}%" if total > 0 else "0%")
        
        st.markdown("---")
        
        # בניית טבלת לוח השנה
        html = '<div class="calendar-wrapper"><table class="calendar-table"><thead><tr>'
        
        # שורת כותרות (7 ימים)
        for d in dates[:7]:
            html += f'<th><span class="day-name">{get_day_name(d)}</span><span class="day-date">{d}</span></th>'
        html += '</tr></thead><tbody>'
        
        # שורות משמרות
        for idx in range(len(shi_df)):
            html += '<tr>'
            for d in dates[:7]:
                s = shi_df.iloc[idx]
                key = f"{d}_{s['תחנה']}_{s['משמרת']}_{idx}"
                assigned = st.session_state.final_schedule.get(key)
                cancelled = key in st.session_state.cancelled_shifts
                is_atan = "אט" in str(s['סוג תקן'])
                
                html += f'<td><div class="shift-mini{"atan" if is_atan else ""}">'
                html += f'<div class="shift-top"><div class="shift-title">{s["משמרת"]}</div>'
                html += f'<div class="shift-badge">{s["סוג תקן"]}</div></div>'
                html += f'<div class="shift-station">{s["תחנה"]}</div>'
                
                if cancelled:
                    html += '<div class="shift-status status-cancelled">🚫 מבוטל</div>'
                elif assigned:
                    html += f'<div class="shift-status status-assigned">👤 {assigned}</div>'
                else:
                    html += '<div class="shift-status status-empty">⚠️ חסר</div>'
                
                html += '</div></td>'
            html += '</tr>'
        
        html += '</tbody></table></div>'
        st.markdown(html, unsafe_allow_html=True)
        
        # כפתורי פעולה
        st.markdown("---")
        st.markdown("### 🔧 פעולות על משמרות")
        st.caption("💡 טיפ: לחץ על הכפתורים לניהול כל משמרת")
        
        cols = st.columns(7)
        for i, d in enumerate(dates[:7]):
            with cols[i]:
                st.markdown(f"**{get_day_name(d)}**")
                
                for idx in range(len(shi_df)):
                    s = shi_df.iloc[idx]
                    key = f"{d}_{s['תחנה']}_{s['משמרת']}_{idx}"
                    assigned = st.session_state.final_schedule.get(key)
                    cancelled = key in st.session_state.cancelled_shifts
                    
                    # תווית המשמרת
                    st.caption(f"📍 {s['משמרת']} - {s['תחנה']}")
                    
                    if cancelled:
                        if st.button("🔄 שחזר", key=f"b_{key}", use_container_width=True, help="שחזר משמרת מבוטלת"):
                            st.session_state.cancelled_shifts.remove(key)
                            st.rerun()
                    elif assigned:
                        if st.button(f"🗑️ {assigned[:8]}", key=f"b_{key}", use_container_width=True, help=f"הסר את {assigned}"):
                            del st.session_state.final_schedule[key]
                            if d in st.session_state.assigned_today:
                                st.session_state.assigned_today[d].discard(assigned)
                            st.rerun()
                    else:
                        col_a, col_b = st.columns([3, 1])
                        with col_a:
                            if st.button("➕ שבץ", key=f"a_{key}", use_container_width=True, type="primary", help="שבץ עובד למשמרת"):
                                show_assignment_dialog(key, d, s['תחנה'], s['משמרת'], req_df, balance, shi_df)
                        with col_b:
                            if st.button("🚫", key=f"c_{key}", help="בטל משמרת"):
                                st.session_state.cancelled_shifts.add(key)
                                st.rerun()
                    
                    st.markdown("---")
    
    except Exception as e:
        st.error(f"❌ {str(e)}")

else:
    st.info("👈 העלה קבצים להתחלה")
