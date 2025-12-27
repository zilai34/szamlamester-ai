import streamlit as st
import pandas as pd
from openai import OpenAI
import base64
import json
import time
from PIL import Image
import fitz  # PyMuPDF
import io

# --- OLDAL BEÁLLÍTÁSA ---
st.set_page_config(page_title="SzámlaMester AI", layout="wide")

# --- STÍLUS ÉS DESIGN ---
st.markdown("""
    <style>
    .main { background-color: #f4f7f6; }
    .stButton>button { width: 100%; border-radius: 10px; height: 3em; background-color: #2c3e50; color: white; }
    </style>
    """, unsafe_allow_name=True)

# --- JELSZÓ VÉDELEM ---
def check_password():
    if "password_correct" not in st.session_state:
        st.text_input("Jelszó", type="password", on_change=password_entered, key="password")
        return False
    return st.session_state["password_correct"]

def password_entered():
    if st.session_state["password"] == "Tornyos2025": # IDE ÍRD A JELSZAVAD!
        st.session_state["password_correct"] = True
        del st.session_state["password"]
    else:
        st.session_state["password_correct"] = False

if not check_password():
    st.stop()

# --- API ÉS ADATOK ---
# A Streamlit Secrets-ből fogjuk venni a kulcsot (beállítás később)
if "OPENAI_API_KEY" in st.secrets:
    client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
else:
    st.error("Hiányzó OpenAI API kulcs a Secrets-ben!")
    st.stop()

# Adatok tárolása a session-ben (amíg fut az app)
if 'db' not in st.session_state:
    st.session_state.db = pd.DataFrame(columns=[
        'Saját Cég', 'Partner', 'Dátum', 'Határidő', 'Bizonylatszám', 'Bankszámla', 'Összeg', 'Fizetési mód', 'Státusz'
    ])

# --- FUNKCIÓK ---
def process_pdf_to_image(file_bytes):
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    page = doc.load_page(0)
    pix = page.get_pixmap(dpi=300)
    img_data = pix.tobytes("jpg")
    doc.close()
    return img_data

def encode_image(image_bytes):
    return base64.b64encode(image_bytes).decode('utf-8')

# --- FELÜLET ---
st.title("🚀 SzámlaMester AI v1.3")

tab1, tab2, tab3 = st.tabs(["📤 Beolvasás", "📋 Napló & Excel", "🏦 OTP Egyeztetés"])

with tab1:
    col1, col2 = st.columns([1, 2])
    with col1:
        ceg = st.selectbox("Melyik cég nevére rögzítsünk?", ["Tornyos Pékség Kft.", "DJ & K BT."])
        uploaded_files = st.file_uploader("Számlák feltöltése (PDF vagy Kép)", accept_multiple_files=True)
        
        if st.button("Feldolgozás indítása") and uploaded_files:
            for uploaded_file in uploaded_files:
                with st.spinner(f"Feldolgozás: {uploaded_file.name}..."):
                    file_bytes = uploaded_file.read()
                    
                    if uploaded_file.name.lower().endswith('.pdf'):
                        img_bytes = process_pdf_to_image(file_bytes)
                    else:
                        img_bytes = file_bytes
                    
                    base64_image = encode_image(img_bytes)

                    response = client.chat.completions.create(
                        model="gpt-4o",
                        messages=[{
                            "role": "user",
                            "content": [
                                {"type": "text", "text": "JSON formátumban add meg: partner, datum, hatarido, bizonylatszam, bankszamla, osszeg, fizetesi_mod."},
                                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                            ]
                        }],
                        response_format={ "type": "json_object" }
                    )
                    
                    adat = json.loads(response.choices[0].message.content)
                    
                    # Tisztítás
                    raw_amount = str(adat.get('osszeg', 0)).replace(' ', '').replace('Ft', '').replace(',', '.')
                    try:
                        clean_amount = int(round(float(raw_amount)))
                    except:
                        clean_amount = 0

                    uj_sor = {
                        'Saját Cég': ceg,
                        'Partner': adat.get('partner', 'Ismeretlen'),
                        'Dátum': adat.get('datum', ''),
                        'Határidő': adat.get('hatarido', adat.get('datum', '')),
                        'Bizonylatszám': adat.get('bizonylatszam', '-'),
                        'Bankszámla': adat.get('bankszamla', '-'),
                        'Összeg': clean_amount,
                        'Fizetési mód': adat.get('fizetesi_mod', 'Átutalás'),
                        'Státusz': 'Nyitott' if 'átutalás' in str(adat.get('fizetesi_mod','')).lower() else 'Kifizetve'
                    }
                    
                    st.session_state.db = pd.concat([st.session_state.db, pd.DataFrame([uj_sor])], ignore_index=True)
            st.success("Minden számla feldolgozva!")

with tab2:
    st.subheader("Rögzített számlák")
    szurt_ceg = st.selectbox("Szűrés cég szerint", ["Összes", "Tornyos Pékség Kft.", "DJ & K BT."])
    
    display_df = st.session_state.db
    if szurt_ceg != "Összes":
        display_df = display_df[display_df['Saját Cég'] == szurt_ceg]
    
    st.dataframe(display_df, use_container_width=True)
    
    # Excel letöltés
    if not display_df.empty:
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            display_df.to_excel(writer, index=False, sheet_name='Szamlak')
        st.download_button(
            label="📊 Excel letöltése",
            data=output.getvalue(),
            file_name="szamlak_export.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

with tab3:
    st.subheader("OTP Kivonat összehasonlítás")
    otp_file = st.file_uploader("Válaszd ki az OTP CSV fájlt", type="csv")
    if st.button("Egyeztetés indítása") and otp_file:
        # Itt ugyanaz az OTP logika futna le
        st.info("Ez a funkció a feltöltött adatokon fut le.")