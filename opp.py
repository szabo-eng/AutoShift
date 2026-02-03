import streamlit as st
import pandas as pd
from datetime import datetime, timedelta

# --- הגדרות דף ---
st.set_page_config(page_title="לוח שנה שיבוץ נעוץ", layout="wide")

# --- CSS לתצוגת כותרת נעוצה (Sticky Headers) ---
st.markdown("""
    <style>
    [data-testid="stAppViewContainer"], [data-testid="stSidebar"], .main {
        direction: rtl;
        text-align: right;
    }
    
    /* מכולת הלוח הכללית */
    .calendar-container {
        display: flex;
        flex-direction: column;
    }

    /* כותרת היום והתאריך - נעוצה בראש */
    .sticky-date-header {
        position: -webkit-sticky;
        position: sticky;
        top: 2.8rem; /* גובה שמתאים לסרגל העליון של Streamlit */
        background-color: #f8f9fa;
        z-index: 100;
        padding: 10px 5px;
        border-bottom: 2px solid #1f77b4;
        text-align: center;
        margin-bottom: 10px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
    }
    
    .day-name { font-weight: bold; color: #1f77b4; font-size: 1rem; display: block; }
    .date-val { font-size: 0.8rem; color: #666; }

    /* עיצוב תא יום */
    .calendar-cell {
        border: 1px solid #eee;
        background-color: #ffffff;
        min-height: 200px;
        padding: 0 5px 10px 5px;
        border-radius: 4px;
    }

    /* כרטיס משמרת */
    .shift-card {
        padding: 5px;
        margin-bottom: 4px;
        border-radius: 4px;
        border-right: 5px solid #ccc;
        font-size: 0.8rem;
    }
    .type-atan { border-right-color: #FFA500; background-color: #FFF8EE; }
    .type-standard { border-right-color: #ADD8E6; background-color: #F0F8FF; }

    /* ביטול מרווחים מיותרים של Streamlit */
    [data-testid="stVerticalBlock"] { gap: 0rem !important; }
    </style>
    """, unsafe_allow_html=True)

# --- פונקציות עזר ---
DAYS_HEB = ['ראשון', 'שני', 'שלישי', 'רביעי', 'חמישי', 'שישי', 'שבת']

def get_day_name(dt):
    # weekday() מחזירה 0 ליום שני, לכן נתאים לראשון=0
    idx = (dt.weekday() + 1) % 7
    return DAYS_HEB[idx]

# --- ממשק צד ---
with st.sidebar:
    st.header("טעינת נתונים")
    req_file = st.file_uploader("REQ.csv", type=['csv'])
    shifts_file = st.file_uploader("SHIFTS.csv", type=['csv'])

# --- הצגת הלוח ---
if req_file and shifts_file:
    req_df = pd.read_csv(req_file, encoding='utf-8-sig')
    shifts_template = pd.read_csv(shifts_file, encoding='utf-8-sig')
    
    req_df.columns = req_df.columns.str.strip()
    shifts_template.columns = shifts_template.columns.str.strip()
    
    # חישוב טווח התאריכים
    req_df['dt_obj'] = pd.to_datetime(req_df['תאריך מבוקש'], dayfirst=True)
    dates = sorted(req_df['dt_obj'].unique())
    
    st.title("📅 לוח שיבוץ עם כותרות נעוצות")
    
    # יצירת עמודות לכל יום בטווח (למשל שבוע)
    cols = st.columns(len(dates))
    
    for i, date_np in enumerate(dates):
        current_dt = pd.to_datetime(date_np)
        date_str = current_dt.strftime('%d/%m/%Y')
        
        with cols[i]:
            # הכותרת הנעוצה
            st.markdown(f"""
                <div class="sticky-date-header">
                    <span class="day-name">יום {get_day_name(current_dt)}</span>
                    <span class="date-val">{date_str}</span>
                </div>
            """, unsafe_allow_html=True)
            
            # תוכן היום (המשמרות)
            with st.container():
                st.markdown('<div class="calendar-cell">', unsafe_allow_html=True)
                
                # סינון משמרות ליום זה
                day_shifts = shifts_template.copy()
                for idx, row in day_shifts.iterrows():
                    style = "type-atan" if "אט" in str(row['סוג תקן']) else "type-standard"
                    
                    st.markdown(f"""
                        <div class="shift-card {style}">
                            <b>{row['משמרת']}</b><br>
                            {row['תחנה']}
                        </div>
                    """, unsafe_allow_html=True)
                    
                    # כפתור שיבוץ
                    st.button("➕", key=f"add_{date_str}_{idx}", width='stretch')
                
                st.markdown('</div>', unsafe_allow_html=True)
else:
    st.info("אנא העלה קבצים כדי להציג את הלוח.")
