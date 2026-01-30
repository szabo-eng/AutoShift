import streamlit as st
import pandas as pd
import firebase_admin
from firebase_admin import credentials, firestore

# --- הגדרות דף ---
st.set_page_config(page_title="מערכת שיבוץ חכמה", layout="wide")

# --- חיבור ל-Firebase ---
if not firebase_admin._apps:
    try:
        firebase_info = dict(st.secrets["firebase"])
        cred = credentials.Certificate(firebase_info)
        firebase_admin.initialize_app(cred)
    except Exception as e:
        st.error("שגיאה בחיבור ל-Firebase. וודא שה-Secrets מוגדרים כהלכה.")

db = firestore.client()

# --- פונקציות בסיס נתונים ---
def get_balance_from_db():
    scores = {}
    try:
        docs = db.collection('employee_history').stream()
        for doc in docs:
            scores[doc.id] = doc.to_dict().get('total_shifts', 0)
    except Exception as e:
        st.warning("לא הצלחתי לשלוף היסטוריה, מתחיל מאפס.")
    return scores

def update_db_balance(assigned_names):
    batch = db.batch()
    for name in assigned_names:
        doc_ref = db.collection('employee_history').document(name)
        batch.set(doc_ref, {'total_shifts': firestore.Increment(1)}, merge=True)
    batch.commit()

# --- ממשק המשתמש ---
st.title("🛡️ מערכת שיבוץ משמרות מאוזנת")

with st.sidebar:
    st.header("1. טעינת נתונים")
    # שימוש ב-encoding='utf-8-sig' לקריאה נכונה של עברית מאקסל
    req_file = st.file_uploader("העלה קובץ בקשות (REQ.csv)", type=['csv'])
    shifts_file = st.file_uploader("העלה תבנית משמרות (SHIFTS.csv)", type=['csv'])

if req_file and shifts_file:
    # טעינת נתונים עם תמיכה בעברית
    req_df = pd.read_csv(req_file, encoding='utf-8-sig')
    shifts_template = pd.read_csv(shifts_file, encoding='utf-8-sig')
    
    # ניקוי רווחים בלבד (משאיר את הגרשיים בתוך המילים כמו אט"ן)
    req_df.columns = req_df.columns.str.strip()
    shifts_template.columns = shifts_template.columns.str.strip()
    
    # זיהוי עמודת מורשה אט"ן בצורה חסינה
    # הקוד יחפש עמודה שמכילה את המילה "אט"ן" או "אטן"
    atan_col = [c for c in req_df.columns if "אט" in c and "מורשה" in c]
    atan_col_name = atan_col[0] if atan_col else 'מורשה אט"ן'

    dates = sorted(req_df['תאריך מבוקש'].unique())
    
    st.header("2. בקרה שבועית")
    shift_toggles = {}
    cols = st.columns(len(dates))
    
    for i, date_str in enumerate(dates):
        with cols[i]:
            st.markdown(f"### {date_str}")
            for idx, row in shifts_template.iterrows():
                key = f"{date_str}_{row['תחנה']}_{row['משמרת']}_{idx}"
                label = f"{row['משמרת']} | {row['תחנה']}"
                shift_toggles[key] = st.toggle(label, value=True, key=key)

    if st.button("🚀 הרץ שיבוץ אוטומטי", type="primary"):
        with st.spinner("מחשב שיבוץ..."):
            history_scores = get_balance_from_db()
            final_schedule = []
            assigned_today = {date: set() for date in dates}

            for date in dates:
                for idx, shift_row in shifts_template.iterrows():
                    key = f"{date}_{shift_row['תחנה']}_{shift_row['משמרת']}_{idx}"
                    if not shift_toggles[key]: continue

                    candidates = req_df[
                        (req_df['תאריך מבוקש'] == date) & 
                        (req_df['משמרת'] == shift_row['משמרת']) & 
                        (req_df['תחנה'] == shift_row['תחנה'])
                    ]

                    # סינון אט"ן עם השם הדינמי שמצאנו
                    if "אט\"ן" in str(shift_row['סוג תקן']):
                        candidates = candidates[candidates[atan_col_name] == 'כן']

                    candidates = candidates[~candidates['שם'].isin(assigned_today[date])]

                    if not candidates.empty:
                        candidates = candidates.copy()
                        candidates['score'] = candidates['שם'].map(lambda x: history_scores.get(x, 0))
                        best_match = candidates.sort_values(by='score').iloc[0]
                        name = best_match['שם']
                        
                        final_schedule.append({
                            'תאריך': date, 'משמרת': shift_row['משמרת'],
                            'תחנה': shift_row['תחנה'], 'שעות': shift_row['שעות'], 'שיבוץ': name
                        })
                        assigned_today[date].add(name)
                        history_scores[name] = history_scores.get(name, 0) + 1
                    else:
                        final_schedule.append({
                            'תאריך': date, 'משמרת': shift_row['משמרת'],
                            'תחנה': shift_row['תחנה'], 'שעות': shift_row['שעות'], 'שיבוץ': "⚠️ לא אויש"
                        })

            st.header("3. תוצאות")
            res_df = pd.DataFrame(final_schedule)
            st.dataframe(res_df, use_container_width=True)

            final_names = [s['שיבוץ'] for s in final_schedule if "⚠️" not in s['שיבוץ']]
            update_db_balance(final_names)
            
            csv_data = res_df.to_csv(index=False).encode('utf-8-sig')
            st.download_button("📥 הורד קובץ שיבוץ", csv_data, "schedule_final.csv", "text/csv")
else:
    st.info("אנא העלה קבצים כדי להתחיל.")
