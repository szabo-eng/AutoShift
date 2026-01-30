import streamlit as st
import pandas as pd
from datetime import datetime
import firebase_admin
from firebase_admin import credentials, firestore

# --- הגדרות דף ---
st.set_page_config(page_title="אוטומציית שיבוץ", layout="wide")

# --- חיבור ל-Firebase Firestore ---
# ב-Streamlit Cloud, נשתמש ב-Secrets כדי לשמור על המפתח
if not firebase_admin._apps:
    try:
        # כאן אנחנו טוענים את המפתח מתוך ה-Secrets של Streamlit
        firebase_creds = dict(st.secrets["firebase"])
        cred = credentials.Certificate(firebase_creds)
        firebase_admin.initialize_app(cred)
    except Exception as e:
        st.error("שגיאה בחיבור ל-Firebase. וודא שהגדרת את ה-Secrets.")

db = firestore.client()

# --- פונקציות עזר ללוגיקה ---

def get_history_scores():
    """שליפת היסטוריית המשמרות מ-Firestore"""
    scores = {}
    docs = db.collection('employee_history').stream()
    for doc in docs:
        scores[doc.id] = doc.to_dict().get('total_shifts', 0)
    return scores

def update_history(assigned_names):
    """עדכון מספר המשמרות ב-Firestore לאחר שיבוץ"""
    for name in assigned_names:
        doc_ref = db.collection('employee_history').document(name)
        doc = doc_ref.get()
        if doc.exists:
            doc_ref.update({'total_shifts': firestore.Increment(1)})
        else:
            doc_ref.set({'total_shifts': 1})

# --- ממשק המשתמש ---

st.title("📅 מערכת אוטומציה לשיבוץ משמרות")

with st.sidebar:
    st.header("טעינת קבצים")
    req_file = st.file_uploader("העלה REQ.csv", type=['csv'])
    shifts_file = st.file_uploader("העלה SHIFTS.csv", type=['csv'])

if req_file and shifts_file:
    req_df = pd.read_csv(req_file)
    shifts_template = pd.read_csv(shifts_file)
    
    # חילוץ תאריכים ייחודיים מקובץ הבקשות
    dates = sorted(req_df['תאריך מבוקש'].unique())
    
    st.subheader("ניהול משמרות שבועי")
    st.info("סמן משמרות כ'לא פעילות' במידה ואין בהן צורך ביום ספציפי.")

    # הצגת לוח שנה שבועי (7 עמודות)
    cols = st.columns(len(dates))
    shift_status = {} # מילון לשמירת מצב ה-Toggles

    for i, date_str in enumerate(dates):
        with cols[i]:
            st.markdown(f"**{date_str}**")
            # מעבר על התבנית לכל יום
            for idx, row in shifts_template.iterrows():
                key = f"{date_str}_{row['תחנה']}_{row['משמרת']}_{idx}"
                label = f"{row['משמרת']} - {row['תחנה']}"
                # Toggle לסימון אם המשמרת פעילה
                shift_status[key] = st.toggle(label, value=True, key=key)

    # --- כפתור הפעלה ---
    if st.button("הפעל אלגוריתם שיבוץ חכם", type="primary"):
        with st.spinner("מחשב שיבוץ אופטימלי ומתחשב באיזון..."):
            
            history_scores = get_history_scores()
            final_schedule = []
            already_assigned_today = {date: set() for date in dates}

            # מעבר על כל יום וכל משמרת בתבנית
            for date in dates:
                for idx, shift_row in shifts_template.iterrows():
                    key = f"{date}_{shift_row['תחנה']}_{shift_row['משמרת']}_{idx}"
                    
                    if not shift_status[key]: # אם המשתמש ביטל את המשמרת
                        continue

                    # סינון מועמדים מתאימים מ-REQ
                    candidates = req_df[
                        (req_df['תאריך מבוקש'] == date) & 
                        (req_df['משמרת'] == shift_row['משמרת']) & 
                        (req_df['תחנה'] == shift_row['תחנה'])
                    ]

                    # סינון לפי מורשה אט"ן אם נדרש
                    if "אט\"ן" in str(shift_row['סוג תקן']):
                        candidates = candidates[candidates['"מורשה אט""ן"'] == 'כן']

                    # סינון אנשים שכבר שובצו היום בתחנה אחרת
                    candidates = candidates[~candidates['שם'].isin(already_assigned_today[date])]

                    if not candidates.empty:
                        # הוספת ציון היסטורי לכל מועמד (אם אין לו היסטוריה, הציון הוא 0)
                        candidates = candidates.copy()
                        candidates['score'] = candidates['שם'].map(lambda x: history_scores.get(x, 0))
                        
                        # בחירת העובד עם הציון הנמוך ביותר (הכי פחות משמרות בעבר)
                        chosen_one = candidates.sort_values(by='score').iloc[0]
                        name = chosen_one['שם']
                        
                        # רישום השיבוץ
                        final_schedule.append({
                            'תאריך': date,
                            'משמרת': shift_row['משמרת'],
                            'תחנה': shift_row['תחנה'],
                            'שעות': shift_row['שעות'],
                            'שם משובץ': name
                        })
                        already_assigned_today[date].add(name)
                    else:
                        # משמרת שלא נמצא לה שיבוץ
                        final_schedule.append({
                            'תאריך': date,
                            'משמרת': shift_row['משמרת'],
                            'תחנה': shift_row['תחנה'],
                            'שעות': shift_row['שעות'],
                            'שם משובץ': "❌ לא אויש"
                        })

            # הצגת תוצאות
            results_df = pd.DataFrame(final_schedule)
            st.success("השיבוץ הסתיים!")
            st.dataframe(results_df, use_container_width=True)

            # עדכון Firebase בשיבוצים החדשים (רק עבור אלו שבאמת שובצו)
            names_to_update = [s['שם משובץ'] for s in final_schedule if "❌" not in s['שם משובץ']]
            update_history(names_to_update)

            # אפשרות הורדה
            csv = results_df.to_csv(index=False).encode('utf-8-sig')
            st.download_button("הורד קובץ שיבוץ סופי (CSV)", data=csv, file_name="final_schedule.csv")

else:
    st.warning("אנא העלה את שני קבצי ה-CSV כדי להתחיל.")