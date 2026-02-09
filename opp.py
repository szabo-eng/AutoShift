import streamlit as st
import pandas as pd
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime
import io

# --- 1. הגדרות דף ועיצוב (Full RTL Compatibility) ---
st.set_page_config(page_title="מערכת שיבוץ מבצעית 2026", layout="wide", page_icon="📅")

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

    [data-testid="stSidebar"] {
        min-width: 250px !important;
        max-width: 250px !important;
    }

    /* מכולת הטבלה - הגדרת כיוון Flex */
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
        min-width: 260px !important;
        max-width: 260px !important;
        flex: 0 0 260px !important;
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
    
    .day-name { font-weight: bold; font-size: 1.1rem; display: block; }
    .date-val { font-size: 0.85rem; opacity: 0.9; }

    .shift-container {
        border-bottom: 1px solid #eee;
        padding: 8px;
        min-height: 150px;
        display: flex;
        flex-direction: column;
        justify-content: space-between;
    }

    .shift-card { 
        padding: 8px; 
        border-radius: 4px; 
        margin-bottom: 5px; 
        border-right: 6px solid #ccc;
        background-color: #fff;
        border: 1px solid #ddd;
        border-right-width: 6px;
        text-align: right;
        box-shadow: 0 1px 2px rgba(0,0,0,0.1);
    }
    
    .type-atan { border-right-color: #FFA500; background-color: #FFF9F0; }
    .type-standard { border-right-color: #2E86C1; background-color: #F0F7FC; }
    .shift-info { font-size: 0.85rem; font-weight: bold; color: #222; }
    
    /* תיקונים לרכיבי UI */
    div[role="dialog"] { direction: rtl !important; text-align: right !important; }
    .stRadio div[role="radiogroup"] { text-align: right !important; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. אתחול Firebase ו-Cache ---
@st.cache_resource
def get_db():
    if not firebase_admin._apps:
        try:
            # Check if secrets exist, otherwise handle gracefully
            if "firebase" in st.secrets:
                cred = credentials.Certificate(dict(st.secrets["firebase"]))
                firebase_admin.initialize_app(cred)
            else:
                return None
        except Exception as e:
            st.error(f"שגיאה בחיבור ל-Database: {e}")
            return None
    return firestore.client()

db = get_db()

# --- 3. פונקציות עזר עם Caching ---
DAYS_HEB = {'Sunday': 'ראשון', 'Monday': 'שני', 'Tuesday': 'שלישי', 'Wednesday': 'רביעי', 'Thursday': 'חמישי', 'Friday': 'שישי', 'Saturday': 'שבת'}

def get_day_name(date_str):
    try: return DAYS_HEB[datetime.strptime(date_str, '%d/%m/%Y').strftime('%A')]
    except: return ""

@st.cache_data(ttl=600) # Cache balance for 10 minutes to save reads
def get_balance_map():
    scores = {}
    if not db: return scores
    try:
        docs = db.collection('employee_history').stream()
        for doc in docs:
            data = doc.to_dict()
            scores[doc.id] = data.get('total_shifts', 0)
    except Exception as e:
        print(f"Error reading balance: {e}")
    return scores

@st.cache_data
def load_csv(file):
    return pd.read_csv(file, encoding='utf-8-sig')

# --- 4. לוגיקה עסקית ---
def run_auto_scheduler(dates, req_df, shi_df, current_balance):
    temp_schedule = {}
    temp_assigned_today = {d: set() for d in dates}
    running_balance = current_balance.copy()
    
    for d in dates:
        # Loop through shifts in the template
        for idx, s in shi_df.iterrows():
            s_key = f"{d}_{s['תחנה']}_{s['משמרת']}_{idx}"
            
            # Skip if manually cancelled
            if s_key in st.session_state.cancelled_shifts:
                continue
            
            # Find candidates
            pot = req_df[
                (req_df['תאריך מבוקש'] == d) & 
                (req_df['משמרת'] == s['משמרת']) & 
                (req_df['תחנה'] == s['תחנה']) & 
                (~req_df['שם'].isin(temp_assigned_today[d]))
            ]
            
            # Handle special permission (ATAN)
            if "אט" in str(s['סוג תקן']):
                # Find column containing "אט" and "מורשה"
                atan_cols = [c for c in req_df.columns if "אט" in c and "מורשה" in c]
                if atan_cols:
                    pot = pot[pot[atan_cols[0]] == 'כן']
            
            if not pot.empty:
                # Greedy: Pick person with lowest balance
                pot = pot.copy()
                pot['score'] = pot['שם'].map(lambda x: running_balance.get(x, 0))
                best = pot.sort_values('score').iloc[0]['שם']
                
                temp_schedule[s_key] = best
                temp_assigned_today[d].add(best)
                running_balance[best] = running_balance.get(best, 0) + 1
                
    return temp_schedule, temp_assigned_today

def save_schedule_to_db_and_csv(final_schedule, shi_df):
    """Handles saving to Firebase and generating CSV"""
    # 1. Update Firebase Balance (Batch write)
    if db:
        batch = db.batch()
        updates = {}
        for name in final_schedule.values():
            updates[name] = updates.get(name, 0) + 1
            
        for name, count in updates.items():
            doc_ref = db.collection('employee_history').document(name)
            batch.set(doc_ref, {'total_shifts': firestore.Increment(count)}, merge=True)
        
        try:
            batch.commit()
            st.toast("✅ נתונים נשמרו ב-Firebase בהצלחה!", icon="🔥")
            get_balance_map.clear() # Clear cache so next load gets new balances
        except Exception as e:
            st.error(f"שגיאה בשמירה ל-DB: {e}")

    # 2. Create Export CSV
    export_data = []
    for s_key, name in final_schedule.items():
        parts = s_key.split('_') # date, station, shift, index
        export_data.append({
            "תאריך": parts[0],
            "תחנה": parts[1],
            "משמרת": parts[2],
            "עובד משובץ": name
        })
    
    return pd.DataFrame(export_data)

# --- 5. דיאלוג שיבוץ (RTL) ---
@st.dialog("שיבוץ עובד ידני")
def show_manual_picker(shift_key, date_str, s_row, req_df, balance):
    st.write(f"**תחנה:** {s_row['תחנה']} | **משמרת:** {s_row['משמרת']}")
    
    avail = req_df[req_df['תאריך מבוקש'] == date_str].copy()
    already_working = st.session_state.assigned_today.get(date_str, set())
    avail = avail[~avail['שם'].isin(already_working)]
    
    if "אט" in str(s_row['סוג תקן']):
        atan_cols = [c for c in req_df.columns if "אט" in c and "מורשה" in c]
        if atan_cols:
            avail = avail[avail[atan_cols[0]] == 'כן']
    
    if avail.empty:
        st.warning("אין עובדים פנויים שעונים לקריטריונים.")
    else:
        avail['bal'] = avail['שם'].map(lambda x: balance.get(x, 0))
        avail = avail.sort_values('bal')
        
        # Create labels
        options = {f"{r['שם']} (מאזן: {int(r['bal'])})": r['שם'] for _, r in avail.iterrows()}
        choice_label = st.radio("בחר עובד:", list(options.keys()))
        
        if st.button("בצע שיבוץ", type="primary", use_container_width=True):
            if choice_label:
                name = options[choice_label]
                st.session_state.final_schedule[shift_key] = name
                st.session_state.assigned_today.setdefault(date_str, set()).add(name)
                st.rerun()

# --- 6. Session State ---
if 'init' not in st.session_state:
    st.session_state.final_schedule = {}
    st.session_state.assigned_today = {}
    st.session_state.cancelled_shifts = set()
    st.session_state.trigger_auto = False
    st.session_state.init = True

# --- 7. Sidebar ---
with st.sidebar:
    st.title("⚙️ ניהול משמרות")
    
    st.info("שלב 1: העלאת נתונים")
    req_f = st.file_uploader("בקשות עובדים (CSV)", type=['csv'])
    shi_f = st.file_uploader("תבנית משמרות (CSV)", type=['csv'])
    
    st.divider()
    
    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("🧹 נקה", use_container_width=True):
            st.session_state.final_schedule = {}
            st.session_state.assigned_today = {}
            st.session_state.cancelled_shifts = set()
            st.rerun()
    with col_b:
        if req_f and shi_f:
             if st.button("🪄 שדרג", type="primary", use_container_width=True):
                st.session_state.trigger_auto = True

    st.divider()
    
    # Save Section
    if st.session_state.final_schedule:
        st.success(f"שובצו: {len(st.session_state.final_schedule)} משמרות")
        if st.button("💾 שמור וייצא", type="primary", use_container_width=True):
            if req_f and shi_f:
                # Perform Save
                shi_df_save = load_csv(shi_f) # Reload for save logic context
                df_export = save_schedule_to_db_and_csv(st.session_state.final_schedule, shi_df_save)
                
                # Convert to CSV for download
                csv_buffer = df_export.to_csv(index=False, encoding='utf-8-sig').encode('utf-8-sig')
                st.download_button(
                    label="📥 הורד קובץ שיבוץ",
                    data=csv_buffer,
                    file_name="final_schedule.csv",
                    mime="text/csv",
                    use_container_width=True
                )

# --- 8. Main App ---
st.title("📅 לוח שיבוץ 2026")

if req_f and shi_f:
    # Use cached loaders
    req_df = load_csv(req_f)
    shi_df = load_csv(shi_f)
    
    dates = sorted(req_df['תאריך מבוקש'].unique(), key=lambda x: datetime.strptime(x, '%d/%m/%Y'))
    global_balance = get_balance_map()

    # --- Auto Scheduler Execution ---
    if st.session_state.trigger_auto:
        sched, assigned = run_auto_scheduler(dates, req_df, shi_df, global_balance)
        st.session_state.final_schedule = sched
        st.session_state.assigned_today = assigned
        st.session_state.trigger_auto = False
        st.rerun()

    # --- Render Grid ---
    cols = st.columns(len(dates))
    
    for i, d_str in enumerate(dates):
        with cols[i]:
            # Header
            st.markdown(f'''
                <div class="table-header">
                    <span class="day-name">{get_day_name(d_str)}</span>
                    <span class="date-val">{d_str}</span>
                </div>
            ''', unsafe_allow_html=True)
            
            # Shifts
            for idx, s in shi_df.iterrows():
                s_key = f"{d_str}_{s['תחנה']}_{s['משמרת']}_{idx}"
                assigned_name = st.session_state.final_schedule.get(s_key)
                is_cancelled = s_key in st.session_state.cancelled_shifts
                
                # Visual Style
                css_class = "type-atan" if "אט" in str(s['סוג תקן']) else "type-standard"
                if is_cancelled: css_class += " opacity-50"
                
                st.markdown('<div class="shift-container">', unsafe_allow_html=True)
                
                # Shift Details Card
                st.markdown(f'''
                    <div class="shift-card {css_class}">
                        <div class="shift-info">
                            {s["משמרת"]} <br>
                            <span style="font-weight:normal">{s["תחנה"]}</span>
                        </div>
                    </div>
                ''', unsafe_allow_html=True)
                
                # Actions Area
                if is_cancelled:
                    st.caption("🚫 בוטל")
                    if st.button("שחזר", key=f"res_{s_key}", use_container_width=True): 
                        st.session_state.cancelled_shifts.remove(s_key)
                        st.rerun()
                
                elif assigned_name:
                    st.success(f"👤 {assigned_name}")
                    if st.button("❌ הסר", key=f"rem_{s_key}", use_container_width=True):
                        st.session_state.assigned_today[d_str].discard(assigned_name)
                        st.session_state.final_schedule.pop(s_key)
                        st.rerun()
                
                else:
                    # Empty State
                    st.markdown(":orange[⚠️ לא משובץ]")
                    b1, b2 = st.columns([3, 1])
                    if b1.button("➕ שבת", key=f"add_{s_key}", use_container_width=True):
                        show_manual_picker(s_key, d_str, s, req_df, global_balance)
                    
                    if b2.button("🚫", key=f"can_{s_key}", use_container_width=True, help="בטל משמרת זו"):
                        st.session_state.cancelled_shifts.add(s_key)
                        st.rerun()
                        
                st.markdown('</div>', unsafe_allow_html=True)

else:
    st.info("👈 אנא העלה את קבצי הבקשות והתבנית בתפריט הצד כדי להתחיל.")
    st.markdown("""
    **קבצים נדרשים:**
    1. **קובץ בקשות:** עמודות (תאריך מבוקש, שם, משמרת, תחנה, אט מורשה...)
    2. **קובץ תבנית:** עמודות (משמרת, תחנה, סוג תקן)
    """)
