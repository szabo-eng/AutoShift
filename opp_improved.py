"""
מערכת שיבוץ מבצעית 2026 - גרסה משופרת
שיפורים עיקריים:
- טיפול מלא בשגיאות
- ולידציה של קבצי קלט
- פונקציית שמירה פעילה
- ארגון קוד משופר
- Caching לביצועים
- לוגים למעקב
"""

import streamlit as st
import pandas as pd
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime
import logging
from html import escape
from typing import Dict, Set, List, Tuple, Optional

# --- הגדרת לוגים ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# --- קבועים ---
REQUIRED_REQUEST_COLUMNS = ['שם', 'תאריך מבוקש', 'משמרת', 'תחנה']
REQUIRED_SHIFT_COLUMNS = ['תחנה', 'משמרת', 'סוג תקן']
DAYS_HEB = {
    'Sunday': 'ראשון', 
    'Monday': 'שני', 
    'Tuesday': 'שלישי', 
    'Wednesday': 'רביעי', 
    'Thursday': 'חמישי', 
    'Friday': 'שישי', 
    'Saturday': 'שבת'
}
DATE_FORMATS = ['%d/%m/%Y', '%Y-%m-%d', '%d-%m-%Y', '%d.%m.%Y']

# --- 1. הגדרות דף ועיצוב ---
st.set_page_config(
    page_title="מערכת שיבוץ מבצעית 2026", 
    layout="wide",
    initial_sidebar_state="expanded"
)

def load_css():
    """טעינת סגנונות CSS"""
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

    /* מכולת הטבלה */
    [data-testid="stHorizontalBlock"] {
        direction: rtl !important;
        overflow-x: auto;
        display: flex;
        flex-direction: row !important;
        gap: 0 !important; 
        border: 2px solid #444;
        border-radius: 4px;
        background-color: #e9ecef;
    }

    /* עיצוב עמודה כתא בטבלה */
    [data-testid="column"] {
        min-width: 280px !important;
        max-width: 280px !important;
        flex: 0 0 280px !important;
        border-right: 1px solid #ccc !important;
        border-left: none !important;
        background-color: #fdfdfd;
        padding: 0 !important;
        margin: 0 !important;
    }

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
    
    .day-name { 
        font-weight: bold; 
        font-size: 1.1rem; 
        display: block; 
    }
    
    .date-val { 
        font-size: 0.85rem; 
        opacity: 0.9; 
    }

    .shift-container {
        border-bottom: 1px solid #eee;
        padding: 8px;
        min-height: 160px;
    }

    .shift-card { 
        padding: 8px; 
        border-radius: 4px; 
        margin-bottom: 5px; 
        border-right: 6px solid #ccc;
        background-color: #fff;
        border-top: 1px solid #eee;
        border-left: 1px solid #eee;
        border-bottom: 2px solid #ddd;
        text-align: right;
    }
    
    .type-atan { 
        border-right-color: #FFA500; 
        background-color: #FFF9F0; 
    }
    
    .type-standard { 
        border-right-color: #2E86C1; 
        background-color: #F0F7FC; 
    }
    
    .shift-info { 
        font-size: 0.85rem; 
        font-weight: bold; 
        color: #222; 
    }

    /* תיקון יישור לדיאלוגים */
    div[role="dialog"] { 
        direction: rtl !important; 
        text-align: right !important; 
    }
    
    .stRadio div[role="radiogroup"] { 
        text-align: right !important; 
    }
    
    /* סטטיסטיקות */
    .stat-box {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 15px;
        border-radius: 8px;
        color: white;
        text-align: center;
        margin: 5px 0;
    }
    
    .stat-number {
        font-size: 2rem;
        font-weight: bold;
    }
    
    .stat-label {
        font-size: 0.9rem;
        opacity: 0.9;
    }
    </style>
    """, unsafe_allow_html=True)

load_css()

# --- 2. אתחול Firebase ---
def initialize_firebase() -> firestore.Client:
    """אתחול חיבור Firebase עם טיפול בשגיאות"""
    if not firebase_admin._apps:
        try:
            cred = credentials.Certificate(dict(st.secrets["firebase"]))
            firebase_admin.initialize_app(cred)
            logger.info("Firebase initialized successfully")
        except KeyError:
            st.error("❌ חסרים פרטי התחברות ל-Firebase ב-secrets")
            logger.error("Firebase secrets not found")
            st.stop()
        except Exception as e:
            st.error(f"❌ שגיאה בחיבור ל-Firebase: {str(e)}")
            logger.error(f"Firebase initialization failed: {e}")
            st.stop()
    
    return firestore.client()

db = initialize_firebase()

# --- 3. פונקציות עזר ---
def parse_date_safe(date_str: str) -> datetime:
    """המרה בטוחה של תאריך עם תמיכה במספר פורמטים"""
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(str(date_str).strip(), fmt)
        except ValueError:
            continue
    raise ValueError(f"פורמט תאריך לא תקין: {date_str}")

def get_day_name(date_str: str) -> str:
    """המרת תאריך לשם יום בעברית"""
    try:
        dt = parse_date_safe(date_str)
        return DAYS_HEB.get(dt.strftime('%A'), "")
    except ValueError:
        logger.warning(f"Invalid date format: {date_str}")
        return ""

def validate_dataframes(req_df: pd.DataFrame, shi_df: pd.DataFrame) -> List[str]:
    """ולידציה של DataFrame - בדיקת עמודות נדרשות"""
    errors = []
    
    missing_req = set(REQUIRED_REQUEST_COLUMNS) - set(req_df.columns)
    missing_shi = set(REQUIRED_SHIFT_COLUMNS) - set(shi_df.columns)
    
    if missing_req:
        errors.append(f"❌ עמודות חסרות בקובץ בקשות: {', '.join(missing_req)}")
    if missing_shi:
        errors.append(f"❌ עמודות חסרות בתבנית משמרות: {', '.join(missing_shi)}")
    
    # בדיקת תאריכים
    try:
        for date_str in req_df['תאריך מבוקש'].unique():
            parse_date_safe(date_str)
    except ValueError as e:
        errors.append(f"❌ {str(e)}")
    
    return errors

def get_atan_column(df: pd.DataFrame) -> Optional[str]:
    """חיפוש בטוח של עמודת אישור אט"ן"""
    atan_cols = [c for c in df.columns if "אט" in c and "מורשה" in c]
    if not atan_cols:
        logger.warning("Atan column not found")
        return None
    return atan_cols[0]

@st.cache_data(ttl=60)
def get_balance() -> Dict[str, int]:
    """טעינת מאזן משמרות לכל עובד מ-Firebase"""
    scores = {}
    try:
        for doc in db.collection('employee_history').stream():
            scores[doc.id] = doc.to_dict().get('total_shifts', 0)
        logger.info(f"Loaded balance for {len(scores)} employees")
    except Exception as e:
        st.warning(f"⚠️ לא ניתן לטעון מאזן עובדים מה-Database: {str(e)}")
        logger.error(f"Failed to load balance: {e}")
    return scores

def save_to_firebase(schedule: Dict[str, str]) -> bool:
    """שמירת השיבוצים ל-Firebase"""
    try:
        # יצירת batch לשמירה יעילה
        batch = db.batch()
        timestamp = firestore.SERVER_TIMESTAMP
        
        # שמירת כל השיבוצים
        for shift_key, employee in schedule.items():
            parts = shift_key.split('_')
            date_str = parts[0]
            station = parts[1]
            shift_type = parts[2]
            
            doc_ref = db.collection('assignments').document(shift_key)
            batch.set(doc_ref, {
                'employee': employee,
                'date': date_str,
                'station': station,
                'shift': shift_type,
                'timestamp': timestamp
            })
        
        # עדכון מאזן עובדים
        employee_counts = {}
        for employee in schedule.values():
            employee_counts[employee] = employee_counts.get(employee, 0) + 1
        
        for employee, count in employee_counts.items():
            emp_ref = db.collection('employee_history').document(employee)
            batch.set(emp_ref, {
                'total_shifts': firestore.Increment(count),
                'last_updated': timestamp
            }, merge=True)
        
        # ביצוע השמירה
        batch.commit()
        logger.info(f"Saved {len(schedule)} assignments to Firebase")
        return True
        
    except Exception as e:
        st.error(f"❌ שגיאה בשמירת הנתונים: {str(e)}")
        logger.error(f"Firebase save failed: {e}")
        return False

# --- 4. דיאלוג שיבוץ ידני ---
@st.dialog("שיבוץ עובד", width="large")
def show_manual_picker(shift_key: str, date_str: str, s_row: pd.Series, 
                       req_df: pd.DataFrame, balance: Dict[str, int]):
    """דיאלוג לבחירת עובד ידנית למשמרת"""
    st.markdown(f"### שיבוץ ליום {get_day_name(date_str)} ({date_str})")
    st.write(f"**תחנה:** {s_row['תחנה']} | **משמרת:** {s_row['משמרת']}")
    
    # סינון מועמדים זמינים
    avail = req_df[req_df['תאריך מבוקש'] == date_str].copy()
    already_working = st.session_state.assigned_today.get(date_str, set())
    avail = avail[~avail['שם'].isin(already_working)]
    
    # סינון לפי אט"ן אם נדרש
    if "אט" in str(s_row['סוג תקן']):
        atan_col = get_atan_column(req_df)
        if atan_col:
            avail = avail[avail[atan_col] == 'כן']
        else:
            st.warning("⚠️ לא נמצאה עמודת אישור אט\"ן")
    
    if avail.empty:
        st.warning("😕 אין מועמדים פנויים למשמרת זו")
        if st.button("סגור", use_container_width=True):
            st.rerun()
    else:
        # מיון לפי מאזן (מי שעבד הכי פחות יהיה ראשון)
        avail['bal'] = avail['שם'].map(lambda x: balance.get(x, 0))
        avail = avail.sort_values('bal')
        
        # יצירת אפשרויות בחירה
        options = {
            f"👤 {r['שם']} (מאזן: {int(r['bal'])} משמרות)": r['שם'] 
            for _, r in avail.iterrows()
        }
        
        choice = st.radio(
            "בחר עובד:", 
            list(options.keys()), 
            index=None,
            help="העובדים מסודרים לפי מאזן משמרות (מי שעבד הכי פחות יופיע ראשון)"
        )
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("✅ אישור", use_container_width=True, type="primary", disabled=not choice):
                if choice:
                    name = options[choice]
                    st.session_state.final_schedule[shift_key] = name
                    st.session_state.assigned_today.setdefault(date_str, set()).add(name)
                    logger.info(f"Manually assigned {name} to {shift_key}")
                    st.rerun()
        
        with col2:
            if st.button("❌ ביטול", use_container_width=True):
                st.rerun()

# --- 5. אתחול Session State ---
def init_session_state():
    """אתחול משתני מצב"""
    if 'final_schedule' not in st.session_state:
        st.session_state.final_schedule = {}
    if 'assigned_today' not in st.session_state:
        st.session_state.assigned_today = {}
    if 'cancelled_shifts' not in st.session_state:
        st.session_state.cancelled_shifts = set()
    if 'trigger_auto' not in st.session_state:
        st.session_state.trigger_auto = False
    if 'trigger_save' not in st.session_state:
        st.session_state.trigger_save = False

init_session_state()

# --- 6. אלגוריתם שיבוץ אוטומטי ---
def auto_assign(dates: List[str], shi_df: pd.DataFrame, 
                req_df: pd.DataFrame, balance: Dict[str, int]) -> Tuple[Dict, Dict]:
    """שיבוץ אוטומטי של כל המשמרות"""
    temp_schedule = {}
    temp_assigned_today = {d: set() for d in dates}
    running_balance = balance.copy()
    
    atan_col = get_atan_column(req_df)
    
    assigned_count = 0
    missing_count = 0
    
    for date_str in dates:
        for idx, shift_row in shi_df.iterrows():
            shift_key = f"{date_str}_{shift_row['תחנה']}_{shift_row['משמרת']}_{idx}"
            
            # דלג על משמרות מבוטלות
            if shift_key in st.session_state.cancelled_shifts:
                continue
            
            # מצא מועמדים פוטנציאליים
            potential = req_df[
                (req_df['תאריך מבוקש'] == date_str) & 
                (req_df['משמרת'] == shift_row['משמרת']) & 
                (req_df['תחנה'] == shift_row['תחנה']) & 
                (~req_df['שם'].isin(temp_assigned_today[date_str]))
            ].copy()
            
            # סינון לפי אט"ן אם נדרש
            if "אט" in str(shift_row['סוג תקן']) and atan_col:
                potential = potential[potential[atan_col] == 'כן']
            
            if not potential.empty:
                # מיון לפי מאזן ובחירת המתאים ביותר
                potential['score'] = potential['שם'].map(lambda x: running_balance.get(x, 0))
                best_employee = potential.sort_values('score').iloc[0]['שם']
                
                temp_schedule[shift_key] = best_employee
                temp_assigned_today[date_str].add(best_employee)
                running_balance[best_employee] = running_balance.get(best_employee, 0) + 1
                assigned_count += 1
            else:
                missing_count += 1
    
    logger.info(f"Auto-assignment: {assigned_count} assigned, {missing_count} missing")
    return temp_schedule, temp_assigned_today

# --- 7. Sidebar ---
with st.sidebar:
    st.title("⚙️ ניהול המערכת")
    
    st.markdown("### 📁 העלאת קבצים")
    req_file = st.file_uploader(
        "קובץ בקשות עובדים", 
        type=['csv'],
        help="CSV עם עמודות: שם, תאריך מבוקש, משמרת, תחנה"
    )
    shi_file = st.file_uploader(
        "תבנית משמרות", 
        type=['csv'],
        help="CSV עם עמודות: תחנה, משמרת, סוג תקן"
    )
    
    st.divider()
    
    # כפתורי פעולה
    if st.button("🧹 איפוס לוח", use_container_width=True, help="מחיקת כל השיבוצים"):
        for key in ['final_schedule', 'assigned_today', 'cancelled_shifts']:
            if key in st.session_state:
                if key == 'cancelled_shifts':
                    st.session_state[key] = set()
                else:
                    st.session_state[key] = {}
        logger.info("Schedule cleared")
        st.rerun()
    
    if req_file and shi_file:
        if st.button("🪄 שיבוץ אוטומטי", type="primary", use_container_width=True):
            st.session_state.trigger_auto = True
            st.rerun()
    
    if st.session_state.final_schedule:
        if st.button("💾 שמירה ל-Database", type="primary", use_container_width=True):
            st.session_state.trigger_save = True
            st.rerun()
        
        if st.button("📥 ייצוא לאקסל", use_container_width=True):
            st.session_state.trigger_export = True
    
    st.divider()
    
    # סטטיסטיקות
    if st.session_state.final_schedule:
        st.markdown("### 📊 סטטיסטיקות")
        total_shifts = len(st.session_state.final_schedule)
        total_cancelled = len(st.session_state.cancelled_shifts)
        unique_employees = len(set(st.session_state.final_schedule.values()))
        
        st.markdown(f"""
        <div class="stat-box">
            <div class="stat-number">{total_shifts}</div>
            <div class="stat-label">משמרות משובצות</div>
        </div>
        """, unsafe_allow_html=True)
        
        st.markdown(f"""
        <div class="stat-box">
            <div class="stat-number">{unique_employees}</div>
            <div class="stat-label">עובדים פעילים</div>
        </div>
        """, unsafe_allow_html=True)
        
        if total_cancelled > 0:
            st.markdown(f"""
            <div class="stat-box">
                <div class="stat-number">{total_cancelled}</div>
                <div class="stat-label">משמרות מבוטלות</div>
            </div>
            """, unsafe_allow_html=True)
    
    st.divider()
    st.caption("מערכת שיבוץ מבצעית 2026 v2.0")

# --- 8. גוף האפליקציה ---
st.title("📅 מערכת שיבוץ מבצעית")

# טיפול בשמירה
if st.session_state.get('trigger_save'):
    with st.spinner('שומר נתונים ל-Database...'):
        if save_to_firebase(st.session_state.final_schedule):
            st.success("✅ השיבוץ נשמר בהצלחה ל-Database!")
            # ניקוי cache של המאזן
            get_balance.clear()
        st.session_state.trigger_save = False

# טיפול בייצוא
if st.session_state.get('trigger_export'):
    if st.session_state.final_schedule:
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
            label="📥 הורד קובץ CSV",
            data=csv,
            file_name=f"shibutz_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv"
        )
    st.session_state.trigger_export = False

# טעינה ועיבוד קבצים
if req_file and shi_file:
    try:
        # טעינת קבצים
        req_df = pd.read_csv(req_file, encoding='utf-8-sig')
        shi_df = pd.read_csv(shi_file, encoding='utf-8-sig')
        
        # ולידציה
        validation_errors = validate_dataframes(req_df, shi_df)
        if validation_errors:
            st.error("### שגיאות בקבצים:")
            for error in validation_errors:
                st.error(error)
            st.stop()
        
        # מיון תאריכים
        dates = sorted(
            req_df['תאריך מבוקש'].unique(), 
            key=parse_date_safe
        )
        
        # טעינת מאזן עובדים
        global_balance = get_balance()
        
        # שיבוץ אוטומטי
        if st.session_state.get('trigger_auto'):
            with st.spinner('מבצע שיבוץ אוטומטי...'):
                temp_schedule, temp_assigned = auto_assign(
                    dates, shi_df, req_df, global_balance
                )
                st.session_state.final_schedule = temp_schedule
                st.session_state.assigned_today = temp_assigned
                st.session_state.trigger_auto = False
                logger.info("Auto-assignment completed")
            st.success("✅ שיבוץ אוטומטי הושלם!")
            st.rerun()
        
        # הצגת לוח השיבוצים
        st.markdown("---")
        cols = st.columns(len(dates))
        
        for i, date_str in enumerate(dates):
            with cols[i]:
                # כותרת היום
                st.markdown(
                    f'<div class="table-header">'
                    f'<span class="day-name">{get_day_name(date_str)}</span>'
                    f'<span class="date-val">{date_str}</span>'
                    f'</div>', 
                    unsafe_allow_html=True
                )
                
                # משמרות היום
                for idx, shift_row in shi_df.iterrows():
                    shift_key = f"{date_str}_{shift_row['תחנה']}_{shift_row['משמרת']}_{idx}"
                    assigned = st.session_state.final_schedule.get(shift_key)
                    cancelled = shift_key in st.session_state.cancelled_shifts
                    
                    # קביעת סגנון לפי סוג תקן
                    style_class = "type-atan" if "אט" in str(shift_row['סוג תקן']) else "type-standard"
                    
                    st.markdown('<div class="shift-container">', unsafe_allow_html=True)
                    
                    # כרטיס משמרת
                    st.markdown(
                        f'<div class="shift-card {style_class}">'
                        f'<div class="shift-info">'
                        f'{escape(str(shift_row["משמרת"]))} | {escape(str(shift_row["סוג תקן"]))}<br>'
                        f'{escape(str(shift_row["תחנה"]))}'
                        f'</div></div>', 
                        unsafe_allow_html=True
                    )
                    
                    # סטטוס ופעולות
                    if cancelled:
                        st.caption("🚫 משמרת מבוטלת")
                        if st.button("🔄 שחזר", key=f"restore_{shift_key}", use_container_width=True):
                            st.session_state.cancelled_shifts.remove(shift_key)
                            logger.info(f"Shift restored: {shift_key}")
                            st.rerun()
                    
                    elif assigned:
                        st.success(f"👤 {assigned}")
                        col1, col2 = st.columns([3, 1])
                        with col1:
                            if st.button("🗑️ הסר", key=f"remove_{shift_key}", use_container_width=True):
                                st.session_state.assigned_today[date_str].discard(assigned)
                                del st.session_state.final_schedule[shift_key]
                                logger.info(f"Assignment removed: {shift_key}")
                                st.rerun()
                        with col2:
                            if st.button("✏️", key=f"edit_{shift_key}", use_container_width=True):
                                st.session_state.assigned_today[date_str].discard(assigned)
                                del st.session_state.final_schedule[shift_key]
                                show_manual_picker(shift_key, date_str, shift_row, req_df, global_balance)
                    
                    else:
                        st.error("⚠️ חסר שיבוץ")
                        col1, col2 = st.columns([3, 1])
                        with col1:
                            if st.button("➕ שבץ", key=f"assign_{shift_key}", use_container_width=True):
                                show_manual_picker(shift_key, date_str, shift_row, req_df, global_balance)
                        with col2:
                            if st.button("🚫", key=f"cancel_{shift_key}", use_container_width=True):
                                st.session_state.cancelled_shifts.add(shift_key)
                                logger.info(f"Shift cancelled: {shift_key}")
                                st.rerun()
                    
                    st.markdown('</div>', unsafe_allow_html=True)
        
        # סיכום בתחתית
        st.markdown("---")
        col1, col2, col3 = st.columns(3)
        with col1:
            total_assigned = len(st.session_state.final_schedule)
            total_shifts = len(shi_df) * len(dates) - len(st.session_state.cancelled_shifts)
            st.metric("משמרות משובצות", f"{total_assigned}/{total_shifts}")
        with col2:
            completion = (total_assigned / total_shifts * 100) if total_shifts > 0 else 0
            st.metric("אחוז השלמה", f"{completion:.1f}%")
        with col3:
            missing = total_shifts - total_assigned
            st.metric("משמרות חסרות", missing)
        
    except Exception as e:
        st.error(f"❌ שגיאה בעיבוד הקבצים: {str(e)}")
        logger.error(f"File processing error: {e}", exc_info=True)
        st.stop()

else:
    # הנחיות ראשוניות
    st.info("👈 יש להעלות את שני הקבצים בתפריט הניהול כדי להתחיל")
    
    with st.expander("📖 הוראות שימוש"):
        st.markdown("""
        ### איך להשתמש במערכת?
        
        1. **העלאת קבצים:**
           - העלה קובץ בקשות עובדים (CSV)
           - העלה תבנית משמרות (CSV)
        
        2. **שיבוץ אוטומטי:**
           - לחץ על כפתור "שיבוץ אוטומטי"
           - המערכת תשבץ אוטומטית לפי מאזן משמרות
        
        3. **שיבוץ ידני:**
           - לחץ על "➕ שבץ" בכל משמרת ריקה
           - בחר עובד מהרשימה
        
        4. **שמירה:**
           - לחץ על "שמירה ל-Database" לשמירת השיבוצים
           - ניתן גם לייצא לאקסל
        
        ### פורמט הקבצים:
        
        **קובץ בקשות:** שם, תאריך מבוקש, משמרת, תחנה
        
        **תבנית משמרות:** תחנה, משמרת, סוג תקן
        """)
