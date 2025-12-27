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

# --- JELSZÓ VÉDELEM ---
def check_password():
    def password_entered():
        if st.session_state["password"] == "Tornyos2025":
            st.session_state["password_correct"] = True
            del st.session_state["password"]
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        st.text_input("Jelszó", type="password", on_change=password_entered, key="password")
        if "password_correct" in st.session_state and not st.session_state["password_correct"]:
            st.error("Helytelen jelszó!")
        return False
    return st.session_state["password_correct"]

if not check_password():
    st.stop()

# --- API KULCS BEOLVASÁSA ---
if "OPENAI_API_KEY" in st.secrets:
    client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
else:
    st.error("Hiba: Az OPENAI_API_KEY hiányzik a Secrets-ből!")
    st.stop()

# --- ADATBÁZIS INICIALIZÁLÁS ---
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
st.info("Tipp: Ha frissíted az oldalt (F5), az adatok elvesznek. Használd az Excel letöltést mentéshez!")

tab1, tab2, tab3 = st.tabs(["📤 Beolvasás", "📋 Napló & Excel", "🏦 OTP Egyeztetés"])

with tab1:
    col1, col2 = st.columns([1, 2])
    with col1:
        ceg = st.selectbox("Melyik cég nevére rögzítsünk?", ["Tornyos Pékség Kft.", "DJ & K BT."])
        uploaded_files = st.file_uploader("Számlák feltöltése (PDF vagy Kép)", accept_multiple_files=True)
        
        if st.button("Feldolgozás indítása") and uploaded_files:
            for uploaded_file in uploaded_files:
                with st.spinner(f"Feldolgozás: {uploaded_file.name}..."):
                    try:
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
            {
                "type": "text", 
                "text": """Elemezd a számlát és adj vissza JSON-t. 
                FONTOS: A 'partner' mezőbe a SZÁMLA KIÁLLÍTÓJÁT (eladó/szolgáltató) írd, 
                NE a vevőt! 
                Mezők: partner, datum, hatarido, bizonylatszam, bankszamla, osszeg, fizetesi_mod."""
            },
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
        ]
    }],
    response_format={ "type": "json_object" }
)
                        )
                        
                        adat = json.loads(response.choices[0].message.content)
                        
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
                    except Exception as e:
                        st.error(f"Hiba a(z) {uploaded_file.name} feldolgozásakor: {e}")

            st.success("Kész!")

with tab2:
    if st.session_state.db.empty:
        st.write("Nincs rögzített adat.")
    else:
        st.dataframe(st.session_state.db, use_container_width=True, hide_index=True)
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            st.session_state.db.to_excel(writer, index=False, sheet_name='Szamlak')
        
        st.download_button(
            label="📊 Excel letöltése",
            data=output.getvalue(),
            file_name="szamlak_export.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

with tab3:
    st.subheader("OTP Kivonat összehasonlítás")
    st.write("Töltsd fel a CSV-t az egyeztetéshez.")
    otp_file = st.file_uploader("OTP CSV fájl", type="csv")
    if st.button("Párosítás") and otp_file:
        st.warning("Ez a funkció fejlesztés alatt áll a felhős verzióban.")


