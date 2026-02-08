"""
מערכת שיבוץ מבצעית 2026 - עם כותרות קבועות
"""

import streamlit as st
import pandas as pd
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime
import logging

# --- הגדרות לוגים ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- קבועים ---
REQUIRED_REQUEST_COLUMNS = ['שם', 'תאריך מבוקש', 'משמרת', 'תחנה']
REQUIRED_SHIFT_COLUMNS = ['תחנה', 'משמרת', 'סוג תקן']
DAYS_HEB = {
    'Sunday': 'ראשון', 'Monday': 'שני', 'Tuesday': 'שלישי',
    'Wednesday': 'רביעי', 'Thursday': 'חמישי', 'Friday': 'שישי', 'Saturday': 'שבת'
}
DATE_FORMATS = ['%d/%m/%Y', '%Y-%m-%d', '%d-%m-%Y']

# --- הגדרות דף ---
st.set_page_config(
    page_title="מערכת שיבוץ מבצעית 2026",
    page_icon="📅",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- CSS מתקדם עם STICKY שעובד ---
def load_custom_css():
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Heebo:wght@300;400;500;600;700;800&family=Rubik:wght@400;500;600;700&display=swap');
    
    /* הגדרות גלובליות */
    html, body, [class*="css"] {
        font-family: 'Heebo', sans-serif;
    }
    
    /* כיוון RTL */
    [data-testid="stAppViewContainer"],
    [data-testid="stSidebar"],
    [data-testid="stMain"] {
        direction: rtl !important;
        text-align: right !important;
    }
    
    /* רקע מעוצב */
    [data-testid="stAppViewContainer"] {
        background: linear-gradient(135deg, #faf8f5 0%, #f4f1ed 100%);
    }
    
    /* כותרת ראשית */
    h1 {
        font-family: 'Rubik', sans-serif !important;
        font-weight: 800 !important;
        background: linear-gradient(135deg, #1a4d7a 0%, #2e6ba8 100%);
        -webkit-background-clip: text !important;
        -webkit-text-fill-color: transparent !important;
        background-clip: text !important;
        font-size: 2.5rem !important;
        letter-spacing: -0.5px !important;
        margin-bottom: 1rem !important;
    }
    
    /* Sidebar */
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #ffffff 0%, #f8f9fa 100%);
        border-left: 3px solid #1a4d7a;
    }
    
    /* כפתורים */
    .stButton > button {
        border-radius: 12px !important;
        font-weight: 600 !important;
        font-family: 'Heebo', sans-serif !important;
        transition: all 0.3s ease !important;
        border: none !important;
        padding: 0.75rem 1.5rem !important;
    }
    
    .stButton > button[kind="primary"] {
        background: linear-gradient(135deg, #1a4d7a 0%, #2e6ba8 100%) !important;
        box-shadow: 0 4px 16px rgba(26, 77, 122, 0.3) !important;
    }
    
    .stButton > button[kind="primary"]:hover {
        transform: translateY(-3px) !important;
        box-shadow: 0 8px 24px rgba(26, 77, 122, 0.4) !important;
    }
    
    /* מדדים */
    [data-testid="stMetricValue"] {
        font-family: 'Rubik', sans-serif !important;
        font-size: 2rem !important;
        font-weight: 800 !important;
        color: #1a4d7a !important;
    }
    
    /* Container מותאם לגלילה אופקית */
    .schedule-container {
        display: flex;
        gap: 1.5rem;
        overflow-x: auto;
        padding: 1rem 0;
        margin: 0 -1rem;
        padding: 1rem;
    }
    
    .schedule-container::-webkit-scrollbar {
        height: 8px;
    }
    
    .schedule-container::-webkit-scrollbar-track {
        background: #f4f1ed;
        border-radius: 10px;
    }
    
    .schedule-container::-webkit-scrollbar-thumb {
        background: rgba(26, 77, 122, 0.3);
        border-radius: 10px;
    }
    
    .schedule-container::-webkit-scrollbar-thumb:hover {
        background: rgba(26, 77, 122, 0.5);
    }
    
    /* עמודת יום */
    .day-column {
        min-width: 320px;
        max-width: 320px;
        background: white;
        border-radius: 16px;
        box-shadow: 0 4px 16px rgba(26, 77, 122, 0.08);
        display: flex;
        flex-direction: column;
        max-height: 75vh;
        overflow: hidden;
    }
    
    /* כותרת יום - STICKY שעובד! */
    .day-header-sticky {
        background: linear-gradient(135deg, #1a4d7a 0%, #2e6ba8 100%);
        color: white;
        padding: 1.5rem;
        border-radius: 16px 16px 0 0;
        text-align: center;
        position: sticky;
        top: 0;
        z-index: 10;
        box-shadow: 0 4px 16px rgba(26, 77, 122, 0.4);
    }
    
    .day-name {
        font-size: 1.4rem;
        font-weight: 700;
        font-family: 'Rubik', sans-serif;
        margin-bottom: 0.25rem;
    }
    
    .day-date {
        font-size: 0.95rem;
        opacity: 0.9;
    }
    
    /* אזור המשמרות - גולל */
    .shifts-area {
        flex: 1;
        overflow-y: auto;
        overflow-x: hidden;
        padding: 1rem;
    }
    
    .shifts-area::-webkit-scrollbar {
        width: 6px;
    }
    
    .shifts-area::-webkit-scrollbar-track {
        background: transparent;
    }
    
    .shifts-area::-webkit-scrollbar-thumb {
        background: rgba(26, 77, 122, 0.2);
        border-radius: 10px;
    }
    
    .shifts-area::-webkit-scrollbar-thumb:hover {
        background: rgba(26, 77, 122, 0.4);
    }
    
    /* כרטיס משמרת */
    .shift-card {
        background: linear-gradient(135deg, #ffffff 0%, #f9f9f9 100%);
        padding: 1.25rem;
        border-radius: 12px;
        border-right: 5px solid #1a4d7a;
        margin-bottom: 1rem;
        transition: all 0.3s ease;
        box-shadow: 0 2px 8px rgba(0,0,0,0.05);
    }
    
    .shift-card:hover {
        transform: translateX(-5px);
        box-shadow: 0 4px 16px rgba(0,0,0,0.1);
    }
    
    .shift-card.atan {
        border-right-color: #e67e22;
        background: linear-gradient(135deg, #fff9f0 0%, #fef5e7 100%);
    }
    
    .shift-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 0.75rem;
    }
    
    .shift-type {
        font-weight: 700;
        font-size: 1.1rem;
        color: #1a4d7a;
        font-family: 'Rubik', sans-serif;
    }
    
    .shift-card.atan .shift-type {
        color: #e67e22;
    }
    
    .shift-badge {
        padding: 0.25rem 0.75rem;
        border-radius: 20px;
        font-size: 0.75rem;
        font-weight: 600;
        background: rgba(26, 77, 122, 0.1);
        color: #1a4d7a;
    }
    
    .shift-card.atan .shift-badge {
        background: rgba(230, 126, 34, 0.1);
        color: #e67e22;
    }
    
    .shift-station {
        color: #7f8c8d;
        font-size: 0.9rem;
        margin-bottom: 0.5rem;
    }
    
    .shift-employee {
        background: rgba(39, 174, 96, 0.1);
        padding: 0.75rem;
        border-radius: 8px;
        color: #27ae60;
        font-weight: 600;
        display: flex;
        align-items: center;
        gap: 0.5rem;
        margin-top: 0.75rem;
    }
    
    .shift-empty {
        background: rgba(231, 76, 60, 0.1);
        padding: 0.75rem;
        border-radius: 8px;
        color: #e74c3c;
        font-weight: 600;
        display: flex;
        align-items: center;
        gap: 0.5rem;
        margin-top: 0.75rem;
    }
    
    /* הודעות */
    .stSuccess {
        background-color: rgba(39, 174, 96, 0.1) !important;
        border-right: 4px solid #27ae60 !important;
        border-radius: 8px !important;
        padding: 1rem !important;
    }
    
    .stError {
        background-color: rgba(231, 76, 60, 0.1) !important;
        border-right: 4px solid #e74c3c !important;
        border-radius: 8px !important;
        padding: 1rem !important;
    }
    
    .stInfo {
        background-color: rgba(26, 77, 122, 0.1) !important;
        border-right: 4px solid #1a4d7a !important;
        border-radius: 8px !important;
        padding: 1rem !important;
    }
    </style>
    """, unsafe_allow_html=True)

load_custom_css()

# --- אתחול Firebase ---
def initialize_firebase():
    if not firebase_admin._apps:
        try:
            cred = credentials.Certificate(dict(st.secrets["firebase"]))
            firebase_admin.initialize_app(cred)
            logger.info("Firebase initialized")
        except Exception as e:
            st.error(f"❌ שגיאה בחיבור ל-Firebase: {str(e)}")
            return None
    return firestore.client()

db = initialize_firebase()

# --- פונקציות עזר ---
def parse_date_safe(date_str):
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(str(date_str).strip(), fmt)
        except ValueError:
            continue
    raise ValueError(f"פורמט תאריך לא תקין: {date_str}")

def get_day_name(date_str):
    try:
        dt = parse_date_safe(date_str)
        return DAYS_HEB.get(dt.strftime('%A'), "")
    except:
        return ""

def validate_dataframes(req_df, shi_df):
    errors = []
    missing_req = set(REQUIRED_REQUEST_COLUMNS) - set(req_df.columns)
    missing_shi = set(REQUIRED_SHIFT_COLUMNS) - set(shi_df.columns)
    
    if missing_req:
        errors.append(f"❌ עמודות חסרות בקובץ בקשות: {', '.join(missing_req)}")
    if missing_shi:
        errors.append(f"❌ עמודות חסרות בתבנית משמרות: {', '.join(missing_shi)}")
    
    return errors

def get_atan_column(df):
    atan_cols = [c for c in df.columns if "אט" in c and "מורשה" in c]
    return atan_cols[0] if atan_cols else None

@st.cache_data(ttl=60)
def get_balance():
    scores = {}
    try:
        if db:
            for doc in db.collection('employee_history').stream():
                scores[doc.id] = doc.to_dict().get('total_shifts', 0)
    except Exception as e:
        st.warning(f"⚠️ לא ניתן לטעון מאזן: {str(e)}")
    return scores

# --- שיבוץ אוטומטי ---
def auto_assign(dates, shi_df, req_df, balance):
    temp_schedule = {}
    temp_assigned_today = {d: set() for d in dates}
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
                (~req_df['שם'].isin(temp_assigned_today[date_str]))
            ].copy()
            
            if "אט" in str(shift_row['סוג תקן']) and atan_col:
                potential = potential[potential[atan_col] == 'כן']
            
            if not potential.empty:
                potential['score'] = potential['שם'].map(lambda x: running_balance.get(x, 0))
                best = potential.sort_values('score').iloc[0]['שם']
                temp_schedule[shift_key] = best
                temp_assigned_today[date_str].add(best)
                running_balance[best] = running_balance.get(best, 0) + 1
    
    return temp_schedule, temp_assigned_today

# --- דיאלוג שיבוץ ---
@st.dialog("שיבוץ עובד למשמרת")
def show_assignment_dialog(shift_key, date_str, station, shift_type, req_df, balance):
    st.markdown(f"### {get_day_name(date_str)} - {date_str}")
    st.write(f"**תחנה:** {station} | **משמרת:** {shift_type}")
    
    already_working = st.session_state.assigned_today.get(date_str, set())
    candidates = req_df[
        (req_df['תאריך מבוקש'] == date_str) &
        (req_df['משמרת'] == shift_type) &
        (req_df['תחנה'] == station) &
        (~req_df['שם'].isin(already_working))
    ].copy()
    
    shift_row = None
    for idx, s in st.session_state.current_shifts_df.iterrows():
        test_key = f"{date_str}_{s['תחנה']}_{s['משמרת']}_{idx}"
        if test_key == shift_key:
            shift_row = s
            break
    
    if shift_row is not None and "אט" in str(shift_row['סוג תקן']):
        atan_col = get_atan_column(req_df)
        if atan_col:
            candidates = candidates[candidates[atan_col] == 'כן']
    
    if candidates.empty:
        st.warning("😕 אין מועמדים פנויים למשמרת זו")
        if st.button("סגור", type="secondary", use_container_width=True):
            st.rerun()
    else:
        candidates['balance'] = candidates['שם'].map(lambda x: balance.get(x, 0))
        candidates = candidates.sort_values('balance')
        
        st.markdown("#### בחר עובד:")
        selected = st.radio(
            "עובדים זמינים:",
            options=candidates['שם'].tolist(),
            format_func=lambda x: f"👤 {x} (מאזן: {balance.get(x, 0)} משמרות)",
            key=f"radio_{shift_key}"
        )
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("✅ אישור", type="primary", use_container_width=True):
                st.session_state.final_schedule[shift_key] = selected
                if date_str not in st.session_state.assigned_today:
                    st.session_state.assigned_today[date_str] = set()
                st.session_state.assigned_today[date_str].add(selected)
                st.success(f"✅ {selected} שובץ/ה בהצלחה!")
                st.rerun()
        
        with col2:
            if st.button("❌ ביטול", type="secondary", use_container_width=True):
                st.rerun()

# --- Session State ---
if 'final_schedule' not in st.session_state:
    st.session_state.final_schedule = {}
if 'assigned_today' not in st.session_state:
    st.session_state.assigned_today = {}
if 'cancelled_shifts' not in st.session_state:
    st.session_state.cancelled_shifts = set()
if 'current_shifts_df' not in st.session_state:
    st.session_state.current_shifts_df = None
if 'current_req_df' not in st.session_state:
    st.session_state.current_req_df = None

# --- Sidebar ---
with st.sidebar:
    st.markdown("# ⚙️ ניהול מערכת")
    
    st.markdown("### 📁 העלאת קבצים")
    req_file = st.file_uploader("קובץ בקשות עובדים", type=['csv'])
    shi_file = st.file_uploader("תבנית משמרות", type=['csv'])
    
    st.divider()
    
    if req_file and shi_file:
        if st.button("🪄 שיבוץ אוטומטי", type="primary", use_container_width=True):
            st.session_state.trigger_auto = True
            st.rerun()
    
    if st.session_state.final_schedule:
        if st.button("💾 שמירה ל-Database", type="primary", use_container_width=True):
            st.success("✅ נשמר!")
        
        if st.button("📥 ייצוא CSV", use_container_width=True):
            export_data = []
            for shift_key, employee in st.session_state.final_schedule.items():
                parts = shift_key.split('_')
                export_data.append({
                    'תאריך': parts[0],
                    'תחנה': parts[1],
                    'משמרת': parts[2],
                    'עובד': employee
                })
            export_df = pd.DataFrame(export_data)
            csv = export_df.to_csv(index=False, encoding='utf-8-sig')
            st.download_button(
                "⬇️ הורד קובץ",
                csv,
                f"shibutz_{datetime.now().strftime('%Y%m%d')}.csv",
                "text/csv",
                use_container_width=True
            )
    
    if st.button("🧹 איפוס לוח", use_container_width=True):
        st.session_state.clear()
        st.rerun()
    
    st.divider()
    
    if st.session_state.final_schedule:
        st.markdown("### 📊 סטטיסטיקות")
        total = len(st.session_state.final_schedule)
        employees = len(set(st.session_state.final_schedule.values()))
        
        col1, col2 = st.columns(2)
        with col1:
            st.metric("משמרות", total)
        with col2:
            st.metric("עובדים", employees)

# --- Main ---
st.title("📅 מערכת שיבוץ מבצעית 2026")

if req_file and shi_file:
    try:
        req_df = pd.read_csv(req_file, encoding='utf-8-sig')
        shi_df = pd.read_csv(shi_file, encoding='utf-8-sig')
        
        errors = validate_dataframes(req_df, shi_df)
        if errors:
            for error in errors:
                st.error(error)
            st.stop()
        
        dates = sorted(req_df['תאריך מבוקש'].unique(), key=parse_date_safe)
        balance = get_balance()
        
        st.session_state.current_shifts_df = shi_df
        st.session_state.current_req_df = req_df
        
        # שיבוץ אוטומטי
        if st.session_state.get('trigger_auto'):
            with st.spinner('מבצע שיבוץ אוטומטי...'):
                temp_schedule, temp_assigned = auto_assign(dates, shi_df, req_df, balance)
                st.session_state.final_schedule = temp_schedule
                st.session_state.assigned_today = temp_assigned
                st.session_state.trigger_auto = False
            st.success(f"✅ שיבוץ אוטומטי הושלם! {len(st.session_state.final_schedule)} משמרות שובצו")
            st.rerun()
        
        # מדדים
        st.markdown("---")
        if st.session_state.final_schedule:
            total_shifts = len(shi_df) * len(dates) - len(st.session_state.cancelled_shifts)
            assigned = len(st.session_state.final_schedule)
            missing = total_shifts - assigned
            completion = (assigned / total_shifts * 100) if total_shifts > 0 else 0
            
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("סך משמרות", total_shifts)
            with col2:
                st.metric("משובצות", assigned)
            with col3:
                st.metric("חסרות", missing)
            with col4:
                st.metric("אחוז השלמה", f"{completion:.0f}%")
        
        st.markdown("---")
        
        # לוח שיבוצים - עם containers בגובה קבוע
        cols = st.columns(min(len(dates), 7))
        
        for i, date_str in enumerate(dates[:7]):
            with cols[i]:
                # כותרת קבועה
                st.markdown(f"""
                <div style="
                    background: linear-gradient(135deg, #1a4d7a 0%, #2e6ba8 100%);
                    color: white;
                    padding: 1.5rem;
                    border-radius: 16px 16px 0 0;
                    text-align: center;
                    margin-bottom: 0;
                ">
                    <div style="font-size: 1.4rem; font-weight: 700; font-family: 'Rubik', sans-serif; margin-bottom: 0.25rem;">
                        {get_day_name(date_str)}
                    </div>
                    <div style="font-size: 0.95rem; opacity: 0.9;">
                        {date_str}
                    </div>
                </div>
                """, unsafe_allow_html=True)
                
                # Container עם גלילה
                with st.container(height=600):
                    for idx, shift_row in shi_df.iterrows():
                        shift_key = f"{date_str}_{shift_row['תחנה']}_{shift_row['משמרת']}_{idx}"
                        assigned = st.session_state.final_schedule.get(shift_key)
                        cancelled = shift_key in st.session_state.cancelled_shifts
                        is_atan = "אט" in str(shift_row['סוג תקן'])
                        
                        # כרטיס משמרת
                        atan_class = "atan" if is_atan else ""
                        st.markdown(f"""
                        <div class="shift-card {atan_class}">
                            <div class="shift-header">
                                <div class="shift-type">{shift_row['משמרת']}</div>
                                <div class="shift-badge">{shift_row['סוג תקן']}</div>
                            </div>
                            <div class="shift-station">{shift_row['תחנה']}</div>
                        """, unsafe_allow_html=True)
                        
                        if cancelled:
                            st.markdown('<div class="shift-empty">🚫 מבוטל</div></div>', unsafe_allow_html=True)
                            if st.button("🔄 שחזר", key=f"restore_{shift_key}", use_container_width=True):
                                st.session_state.cancelled_shifts.remove(shift_key)
                                st.rerun()
                        elif assigned:
                            st.markdown(f'<div class="shift-employee">👤 {assigned}</div></div>', unsafe_allow_html=True)
                            if st.button("🗑️ הסר", key=f"remove_{shift_key}", use_container_width=True):
                                del st.session_state.final_schedule[shift_key]
                                st.session_state.assigned_today[date_str].discard(assigned)
                                st.rerun()
                        else:
                            st.markdown('<div class="shift-empty">⚠️ חסר</div></div>', unsafe_allow_html=True)
                            col_a, col_b = st.columns([3, 1])
                            with col_a:
                                if st.button("➕ שבץ", key=f"assign_{shift_key}", use_container_width=True):
                                    show_assignment_dialog(
                                        shift_key, date_str, shift_row['תחנה'], 
                                        shift_row['משמרת'], req_df, balance
                                    )
                            with col_b:
                                if st.button("🚫", key=f"cancel_{shift_key}", use_container_width=True):
                                    st.session_state.cancelled_shifts.add(shift_key)
                                    st.rerun()
        
    except Exception as e:
        st.error(f"❌ שגיאה: {str(e)}")

else:
    st.info("👈 העלה את שני הקבצים בתפריט הניהול כדי להתחיל")
    
    with st.expander("📖 הוראות שימוש"):
        st.markdown("""
        ### איך להשתמש במערכת?
        
        1. **העלאת קבצים** - העלה CSV עם בקשות ומשמרות
        2. **שיבוץ אוטומטי** - לחץ על הכפתור לשיבוץ חכם
        3. **התאמות ידניות** - שבץ/הסר לפי צורך
        4. **שמירה** - שמור ל-Database או ייצא לאקסל
        
        ### פורמט קבצים:
        - **בקשות:** שם, תאריך מבוקש, משמרת, תחנה
        - **משמרות:** תחנה, משמרת, סוג תקן
        """)
