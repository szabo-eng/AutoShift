import streamlit as st
import pandas as pd
import firebase_admin
from firebase_admin import credentials, firestore

# --- הגדרות דף ---
st.set_page_config(page_title="מערכת שיבוץ חכמה", layout="wide")

# --- חיבור ל-Firebase ---
if not firebase_admin._apps:
    try:
        # טעינת סודות מתוך Streamlit Cloud Secrets
        firebase_info = dict(st.secrets["firebase"])
        cred = credentials.Certificate(firebase_info)
        firebase_admin.initialize_app(cred)
    except Exception as e:
        st.error("שגיאה בחיבור ל-Firebase. וודא שה-Secrets מוגדרים כהלכה.")

db = firestore.client()

# --- פונקציות בסיס נתונים ---

def get_balance_from_db():
    """שליפת הניקוד של כל העובדים מ-Firestore"""
    scores = {}
    docs = db.collection('employee_history').stream()
    for doc in docs:
        scores[doc.id] = doc.to_dict().get('total_shifts', 0)
    return scores

def update_db_balance(assigned_names):
    """עדכון המאזן ב-Firestore עבור אלו ששובצו"""
    batch = db.batch()
    for name in assigned_names:
        doc_ref = db.collection('employee_history').document(name)
        # שימוש ב-Increment כדי למנוע בעיות סנכרון
        batch.set(doc_ref, {'total_shifts': firestore.Increment(1)}, merge=True)
    batch.commit()

# --- ממשק המשתמש ---

st.title("🛡️ מערכת שיבוץ משמרות מאוזנת")

with st.sidebar:
    st.header("1. טעינת נתונים")
    req_file = st.file_uploader("העלה קובץ בקשות (REQ.csv)", type=['csv'])
    shifts_file = st.file_uploader("העלה תבנית משמרות (SHIFTS.csv)", type=['csv'])

if req_file and shifts_file:
    # קריאת הקבצים
    req_df = pd.read_csv(req_file)
    shifts_template = pd.read_csv(shifts_file)
    
    # --- ניקוי עמודות (טיפול ב-KeyError) ---
    req_df.columns = req_df.columns.str.replace('"', '').str.strip()
    shifts_template.columns = shifts_template.columns.str.replace('"', '').str.strip()
    
    # חילוץ תאריכים
    dates = sorted(req_df['תאריך מבוקש'].unique())
    
    st.header("2. בקרה שבועית")
    st.write("כבה משמרות שאינך מעוניין לאייש בשבוע זה:")

    # יצירת לוח השנה
    shift_toggles = {}
    cols = st.columns(len(dates))
    
    for i, date_str in enumerate(dates):
        with cols[i]:
            st.markdown(f"### {date_str}")
            for idx, row in shifts_template.iterrows():
                # מזהה ייחודי למשמרת: תאריך + תחנה + סוג + אינדקס
                key = f"{date_str}_{row['תחנה']}_{row['משמרת']}_{idx}"
                label = f"{row['משמרת']} | {row['תחנה']}"
                shift_toggles[key] = st.toggle(label, value=True, key=key)

    # --- הפעלת האלגוריתם ---
    if st.button("🚀 הרץ שיבוץ אוטומטי", type="primary"):
        with st.spinner("מבצע אופטימיזציה מול היסטוריית Firebase..."):
            
            history_scores = get_balance_from_db()
            final_schedule = []
            assigned_today = {date: set() for date in dates}

            for date in dates:
                for idx, shift_row in shifts_template.iterrows():
                    key = f"{date}_{shift_row['תחנה']}_{shift_row['משמרת']}_{idx}"
                    
                    if not shift_toggles[key]:
                        continue

                    # סינון מועמדים רלוונטיים
                    candidates = req_df[
                        (req_df['תאריך מבוקש'] == date) & 
                        (req_df['משמרת'] == shift_row['משמרת']) & 
                        (req_df['תחנה'] == shift_row['תחנה'])
                    ]

                    # בדיקת מורשה אט"ן
                    if "אט\"ן" in str(shift_row['סוג תקן']):
                        candidates = candidates[candidates['מורשה אט"ן'] == 'כן']

                    # מניעת כפל שיבוץ באותו יום
                    candidates = candidates[~candidates['שם'].isin(assigned_today[date])]

                    if not candidates.empty:
                        # הצמדת ציון היסטורי (איזון)
                        candidates = candidates.copy()
                        candidates['balance_score'] = candidates['שם'].map(lambda x: history_scores.get(x, 0))
                        
                        # בחירת העובד עם הכי פחות משמרות (הציון הכי נמוך)
                        best_match = candidates.sort_values(by='balance_score').iloc[0]
                        name = best_match['שם']
                        
                        final_schedule.append({
                            'תאריך': date,
                            'משמרת': shift_row['משמרת'],
                            'תחנה': shift_row['תחנה'],
                            'שעות': shift_row['שעות'],
                            'שיבוץ': name
                        })
                        assigned_today[date].add(name)
                        # עדכון הניקוד המקומי כדי לא לשבץ אותו פעמיים ברצף אם יש אחרים
                        history_scores[name] = history_scores.get(name, 0) + 1
                    else:
                        final_schedule.append({
                            'תאריך': date,
                            'משמרת': shift_row['משמרת'],
                            'תחנה': shift_row['תחנה'],
                            'שעות': shift_row['שעות'],
                            'שיבוץ': "⚠️ לא נמצא מבקש מתאים"
                        })

            # הצגת תוצאות
            st.header("3. תוצאות השיבוץ")
            res_df = pd.DataFrame(final_schedule)
            st.table(res_df)

            # עדכון בסיס נתונים
            final_names = [s['שיבוץ'] for s in final_schedule if "⚠️" not in s['שיבוץ']]
            update_db_balance(final_names)
            
            st.success(f"השיבוץ הסתיים! עודכנו {len(final_names)} רשומות ב-Firebase.")
            
            # הורדה
            csv_data = res_df.to_csv(index=False).encode('utf-8-sig')
            st.download_button("📥 הורד קובץ שיבוץ", csv_data, "schedule.csv", "text/csv")