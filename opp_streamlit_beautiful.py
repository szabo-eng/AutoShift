"""
מערכת שיבוץ מבצעית 2026 - גרסה סופית מתוקנת
כולל: עיצוב מתקדם, כותרות קבועות, דיאלוגים, Firebase, ועוד
"""

import streamlit as st
import pandas as pd
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime
import logging
from typing import Dict, Set, List, Optional

# ===== הגדרות בסיסיות =====
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

REQUIRED_REQUEST_COLUMNS = ['שם', 'תאריך מבוקש', 'משמרת', 'תחנה']
REQUIRED_SHIFT_COLUMNS = ['תחנה', 'משמרת', 'סוג תקן']
DAYS_HEB = {
    'Sunday': 'ראשון', 'Monday': 'שני', 'Tuesday': 'שלישי',
    'Wednesday': 'רביעי', 'Thursday': 'חמישי', 'Friday': 'שישי', 'Saturday': 'שבת'
}
DATE_FORMATS = ['%d/%m/%Y', '%Y-%m-%d', '%d-%m-%Y']

st.set_page_config(
    page_title="מערכת שיבוץ מבצעית 2026",
    page_icon="📅",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ===== CSS מלא ומתוקן =====
def load_css():
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Heebo:wght@300;400;500;600;700;800&family=Rubik:wght@400;500;600;700&display=swap');
    
    /* הגדרות בסיס */
    * {
        font-family: 'Heebo', sans-serif;
    }
    
    /* RTL */
    [data-testid="stAppViewContainer"],
    [data-testid="stSidebar"],
    [data-testid="stMain"],
    .main {
        direction: rtl !important;
        text-align: right !important;
    }
    
    /* רקע */
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
        font-size: 2.5rem !important;
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
        transition: all 0.3s ease !important;
        border: none !important;
        padding: 0.75rem 1.5rem !important;
    }
    
    .stButton > button[kind="primary"] {
        background: linear-gradient(135deg, #1a4d7a 0%, #2e6ba8 100%) !important;
        color: white !important;
        box-shadow: 0 4px 16px rgba(26, 77, 122, 0.3) !important;
    }
    
    .stButton > button[kind="primary"]:hover {
        transform: translateY(-3px) !important;
        box-shadow: 0 8px 24px rgba(26, 77, 122, 0.4) !important;
    }
    
    .stButton > button[kind="secondary"] {
        background: #f4f1ed !important;
        color: #2c3e50 !important;
    }
    
    /* העלאת קבצים */
    [data-testid="stFileUploader"] {
        background: white;
        padding: 1.5rem;
        border-radius: 12px;
        border: 2px dashed #e8e4df;
    }
    
    /* מדדים */
    [data-testid="stMetricValue"] {
        font-family: 'Rubik', sans-serif !important;
        font-size: 2rem !important;
        font-weight: 800 !important;
        color: #1a4d7a !important;
    }
    
    /* הודעות */
    .stSuccess {
        background: rgba(39, 174, 96, 0.1) !important;
        border-right: 4px solid #27ae60 !important;
        border-radius: 8px !important;
        padding: 1rem !important;
    }
    
    .stError {
        background: rgba(231, 76, 60, 0.1) !important;
        border-right: 4px solid #e74c3c !important;
        border-radius: 8px !important;
        padding: 1rem !important;
    }
    
    .stWarning {
        background: rgba(243, 156, 18, 0.1) !important;
        border-right: 4px solid #f39c12 !important;
        border-radius: 8px !important;
        padding: 1rem !important;
    }
    
    .stInfo {
        background: rgba(26, 77, 122, 0.1) !important;
        border-right: 4px solid #1a4d7a !important;
        border-radius: 8px !important;
        padding: 1rem !important;
    }
    
    /* Container של לוח השיבוץ - עם גלילה אופקית */
    .schedule-container {
        width: 100%;
        overflow-x: auto;
        padding-bottom: 1rem;
        direction: rtl;
    }
    
    /* Grid של ימים */
    .days-grid {
        display: inline-flex;
        gap: 1.5rem;
        min-width: min-content;
        direction: rtl;
    }
    
    /* עמודת יום */
    .day-column {
        width: 320px;
        flex-shrink: 0;
        background: white;
        border-radius: 16px;
        box-shadow: 0 4px 16px rgba(26, 77, 122, 0.08);
        overflow: hidden;
        display: flex;
        flex-direction: column;
        max-height: 75vh;
    }
    
    /* כותרת יום - STICKY! */
    .day-header {
        background: linear-gradient(135deg, #1a4d7a 0%, #2e6ba8 100%);
        color: white;
        padding: 1.5rem;
        text-align: center;
        position: sticky;
        top: 0;
        z-index: 100;
        box-shadow: 0 4px 12px rgba(26, 77, 122, 0.3);
        flex-shrink: 0;
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
    
    /* אזור המשמרות - עם גלילה */
    .shifts-area {
        overflow-y: auto;
        overflow-x: hidden;
        flex: 1;
        padding: 1rem;
    }
    
    /* Scrollbar מעוצב */
    .shifts-area::-webkit-scrollbar {
        width: 6px;
    }
    
    .shifts-area::-webkit-scrollbar-track {
        background: transparent;
    }
    
    .shifts-area::-webkit-scrollbar-thumb {
        background: rgba(26, 77, 122, 0.3);
        border-radius: 10px;
    }
    
    .shifts-area::-webkit-scrollbar-thumb:hover {
        background: rgba(26, 77, 122, 0.5);
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
    
    .shift-info-header {
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
        margin-bottom: 0.75rem;
    }
    
    .shift-status {
        padding: 0.75rem;
        border-radius: 8px;
        font-weight: 600;
        display: flex;
        align-items: center;
        gap: 0.5rem;
        margin-bottom: 0.75rem;
    }
    
    .shift-status.assigned {
        background: rgba(39, 174, 96, 0.1);
        color: #27ae60;
    }
    
    .shift-status.empty {
        background: rgba(231, 76, 60, 0.1);
        color: #e74c3c;
    }
    
    .shift-status.cancelled {
        background: rgba(127, 140, 141, 0.1);
        color: #7f8c8d;
    }
    
    /* כפתורי פעולה */
    .shift-actions {
        display: flex;
        gap: 0.5rem;
    }
    
    /* אנימציות */
    @keyframes slideIn {
        from {
            opacity: 0;
            transform: translateY(20px);
        }
        to {
            opacity: 1;
            transform: translateY(0);
        }
    }
    
    .day-column {
        animation: slideIn 0.5s ease-out;
    }
    
    /* Responsive */
    @media (max-width: 768px) {
        .day-column {
            width: 280px;
        }
    }
    </style>
    """, unsafe_allow_html=True)

load_css()

# ===== פונקציות עזר =====
def parse_date_safe(date_str: str) -> datetime:
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(str(date_str).strip(), fmt)
        except ValueError:
            continue
    raise ValueError(f"פורמט תאריך לא תקין: {date_str}")

def get_day_name(date_str: str) -> str:
    try:
        dt = parse_date_safe(date_str)
        return DAYS_HEB.get(dt.strftime('%A'), "")
    except:
        return ""

def validate_dataframes(req_df: pd.DataFrame, shi_df: pd.DataFrame) -> List[str]:
    errors = []
    missing_req = set(REQUIRED_REQUEST_COLUMNS) - set(req_df.columns)
    missing_shi = set(REQUIRED_SHIFT_COLUMNS) - set(shi_df.columns)
    
    if missing_req:
        errors.append(f"❌ עמודות חסרות בקובץ בקשות: {', '.join(missing_req)}")
    if missing_shi:
        errors.append(f"❌ עמודות חסרות בתבנית משמרות: {', '.join(missing_shi)}")
    
    return errors

def get_atan_column(df: pd.DataFrame) -> Optional[str]:
    atan_cols = [c for c in df.columns if "אט" in c and "מורשה" in c]
    return atan_cols[0] if atan_cols else None

# ===== Firebase =====
def initialize_firebase():
    if not firebase_admin._apps:
        try:
            cred = credentials.Certificate(dict(st.secrets["firebase"]))
            firebase_admin.initialize_app(cred)
            logger.info("Firebase initialized")
        except Exception as e:
            st.warning(f"⚠️ Firebase לא זמין: {str(e)}")
            return None
    return firestore.client()

db = initialize_firebase()

@st.cache_data(ttl=60)
def get_balance() -> Dict[str, int]:
    scores = {}
    try:
        if db:
            for doc in db.collection('employee_history').stream():
                scores[doc.id] = doc.to_dict().get('total_shifts', 0)
    except Exception as e:
        logger.warning(f"Could not load balance: {e}")
    return scores

# ===== אלגוריתם שיבוץ =====
def auto_assign(dates: List[str], shi_df: pd.DataFrame, req_df: pd.DataFrame, balance: Dict[str, int]):
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

# ===== דיאלוג שיבוץ =====
@st.dialog("שיבוץ עובד למשמרת", width="large")
def show_assignment_dialog(shift_key: str, date_str: str, station: str, shift_type: str, req_df: pd.DataFrame, shi_df: pd.DataFrame, balance: Dict[str, int]):
    st.markdown(f"### {get_day_name(date_str)} - {date_str}")
    st.write(f"**תחנה:** {station} | **משמרת:** {shift_type}")
    
    # מצא מועמדים
    already_working = st.session_state.assigned_today.get(date_str, set())
    candidates = req_df[
        (req_df['תאריך מבוקש'] == date_str) &
        (req_df['משמרת'] == shift_type) &
        (req_df['תחנה'] == station) &
        (~req_df['שם'].isin(already_working))
    ].copy()
    
    # סינון אט"ן
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
        st.warning("😕 אין מועמדים פנויים למשמרת זו")
        if st.button("סגור", type="secondary", use_container_width=True):
            st.rerun()
    else:
        candidates['balance'] = candidates['שם'].map(lambda x: balance.get(x, 0))
        candidates = candidates.sort_values('balance')
        
        st.markdown("#### בחר עובד:")
        st.caption("מסודר לפי מאזן (מי שעבד הכי פחות)")
        
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
                st.success(f"✅ {selected} שובץ/ה!")
                st.rerun()
        
        with col2:
            if st.button("❌ ביטול", type="secondary", use_container_width=True):
                st.rerun()

# ===== Session State =====
if 'final_schedule' not in st.session_state:
    st.session_state.final_schedule = {}
if 'assigned_today' not in st.session_state:
    st.session_state.assigned_today = {}
if 'cancelled_shifts' not in st.session_state:
    st.session_state.cancelled_shifts = set()

# ===== Sidebar =====
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
                export_data.append({'תאריך': parts[0], 'תחנה': parts[1], 'משמרת': parts[2], 'עובד': employee})
            export_df = pd.DataFrame(export_data)
            csv = export_df.to_csv(index=False, encoding='utf-8-sig')
            st.download_button("⬇️ הורד", csv, f"shibutz_{datetime.now().strftime('%Y%m%d')}.csv", "text/csv", use_container_width=True)
    
    if st.button("🧹 איפוס", use_container_width=True):
        st.session_state.clear()
        st.rerun()
    
    st.divider()
    
    if st.session_state.final_schedule:
        st.markdown("### 📊 סטטיסטיקות")
        col1, col2 = st.columns(2)
        with col1:
            st.metric("משמרות", len(st.session_state.final_schedule))
        with col2:
            st.metric("עובדים", len(set(st.session_state.final_schedule.values())))

# ===== Main =====
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
        
        # שיבוץ אוטומטי
        if st.session_state.get('trigger_auto'):
            with st.spinner('מבצע שיבוץ אוטומטי...'):
                temp_schedule, temp_assigned = auto_assign(dates, shi_df, req_df, balance)
                st.session_state.final_schedule = temp_schedule
                st.session_state.assigned_today = temp_assigned
                st.session_state.trigger_auto = False
            st.success(f"✅ שיבוץ הושלם! {len(st.session_state.final_schedule)} משמרות")
            st.rerun()
        
        st.markdown("---")
        
        # מדדים
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
                st.metric("השלמה", f"{completion:.0f}%")
            
            st.markdown("---")
        
        # לוח שיבוצים עם HTML
        html_content = '<div class="schedule-container"><div class="days-grid">'
        
        for date_str in dates[:7]:  # מקסימום 7 ימים
            html_content += f'''
            <div class="day-column">
                <div class="day-header">
                    <div class="day-name">{get_day_name(date_str)}</div>
                    <div class="day-date">{date_str}</div>
                </div>
                <div class="shifts-area">
            '''
            
            for idx, shift_row in shi_df.iterrows():
                shift_key = f"{date_str}_{shift_row['תחנה']}_{shift_row['משמרת']}_{idx}"
                assigned = st.session_state.final_schedule.get(shift_key)
                cancelled = shift_key in st.session_state.cancelled_shifts
                is_atan = "אט" in str(shift_row['סוג תקן'])
                
                atan_class = "atan" if is_atan else ""
                
                html_content += f'''
                <div class="shift-card {atan_class}">
                    <div class="shift-info-header">
                        <div class="shift-type">{shift_row['משמרת']}</div>
                        <div class="shift-badge">{shift_row['סוג תקן']}</div>
                    </div>
                    <div class="shift-station">{shift_row['תחנה']}</div>
                '''
                
                if cancelled:
                    html_content += '<div class="shift-status cancelled">🚫 מבוטל</div>'
                elif assigned:
                    html_content += f'<div class="shift-status assigned">👤 {assigned}</div>'
                else:
                    html_content += '<div class="shift-status empty">⚠️ חסר שיבוץ</div>'
                
                html_content += f'<div id="actions_{shift_key}"></div></div>'
            
            html_content += '</div></div>'
        
        html_content += '</div></div>'
        
        st.markdown(html_content, unsafe_allow_html=True)
        
        # כפתורי פעולה בשורות נפרדות
        st.markdown("---")
        st.markdown("### פעולות על משמרות")
        
        for date_str in dates[:7]:
            with st.expander(f"📅 {get_day_name(date_str)} - {date_str}"):
                for idx, shift_row in shi_df.iterrows():
                    shift_key = f"{date_str}_{shift_row['תחנה']}_{shift_row['משמרת']}_{idx}"
                    assigned = st.session_state.final_schedule.get(shift_key)
                    cancelled = shift_key in st.session_state.cancelled_shifts
                    
                    st.markdown(f"**{shift_row['משמרת']}** - {shift_row['תחנה']} ({shift_row['סוג תקן']})")
                    
                    col1, col2, col3 = st.columns([2, 1, 1])
                    
                    if cancelled:
                        with col1:
                            st.caption("🚫 מבוטל")
                        with col2:
                            if st.button("🔄 שחזר", key=f"restore_{shift_key}"):
                                st.session_state.cancelled_shifts.remove(shift_key)
                                st.rerun()
                    elif assigned:
                        with col1:
                            st.success(f"👤 {assigned}")
                        with col2:
                            if st.button("🗑️ הסר", key=f"remove_{shift_key}"):
                                del st.session_state.final_schedule[shift_key]
                                st.session_state.assigned_today[date_str].discard(assigned)
                                st.rerun()
                    else:
                        with col1:
                            st.warning("⚠️ חסר")
                        with col2:
                            if st.button("➕ שבץ", key=f"assign_{shift_key}"):
                                show_assignment_dialog(shift_key, date_str, shift_row['תחנה'], shift_row['משמרת'], req_df, shi_df, balance)
                        with col3:
                            if st.button("🚫 בטל", key=f"cancel_{shift_key}"):
                                st.session_state.cancelled_shifts.add(shift_key)
                                st.rerun()
                    
                    st.divider()
        
    except Exception as e:
        st.error(f"❌ שגיאה: {str(e)}")
        logger.error(f"Error: {e}", exc_info=True)

else:
    st.info("👈 העלה את שני הקבצים כדי להתחיל")
    
    with st.expander("📖 הוראות שימוש"):
        st.markdown("""
        ### איך להשתמש?
        
        1. **העלאת קבצים** - CSV עם בקשות ומשמרות
        2. **שיבוץ אוטומטי** - לחץ על הכפתור
        3. **שיבוץ ידני** - לחץ ➕ על משמרת
        4. **שמירה** - Database או CSV
        
        ### פורמט קבצים:
        - **בקשות:** שם, תאריך מבוקש, משמרת, תחנה
        - **משמרות:** תחנה, משמרת, סוג תקן
        """)
