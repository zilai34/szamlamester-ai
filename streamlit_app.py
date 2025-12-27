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
st.set_page_config(page_title="SzámlaMester AI v1.3", layout="wide")

# --- DESIGN ---
st.markdown("""
    <style>
    .main { background-color: #f4f7f6; }
    .stButton>button { width: 100%; border-radius: 10px; height: 3em; background-color: #2c3e50; color: white; }
    .stDataFrame { border-radius: 10px; overflow: hidden; }
    </style>
    """, unsafe_allow_html=True)

# --- JELSZÓ VÉDELEM ---
def check_password():
    def password_entered():
        if st.session_state["password"] == "Tornyos2025":
            st.session_state["password_correct"] = True
            del st.session_state["password"]
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        st.text_input("Jelszó a belépéshez", type="password", on_change=password_entered, key="password")
        if "password_correct" in st.session_state and not st.session_state["password_correct"]:
            st.error("Helytelen jelszó! Próbáld újra.")
        return False
    return st.session_state["password_correct"]

if not check_password():
    st.stop()

# --- API KULCS ---
if "OPENAI_API_KEY" in st.secrets:
    client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
else:
    st.error("HIBA: Az OPENAI_API_KEY nincs beállítva a Streamlit Secrets-ben!")
    st.stop()

# --- ADATBÁZIS (SESSION) ---
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
st.caption("Használd a mobilodról is a számlák gyors beolvasásához!")

tab1, tab2, tab3 = st.tabs(["📤 Beolvasás", "📋 Napló & Excel", "🏦 OTP Egyeztetés"])

with tab1:
    col1, col2 = st.columns([1, 2])
    with col1:
        sajat_ceg = st.selectbox("Melyik cég nevére rögzítsünk?", ["Tornyos Pékség Kft.", "DJ & K BT."])
        uploaded_files = st.file_uploader("Számlák feltöltése", accept_multiple_files=True, type=['png', 'jpg', 'jpeg', 'pdf'])
        
        if st.button("Feldolgozás indítása") and uploaded_files:
            for uploaded_file in uploaded_files:
                with st.spinner(f"Elemzés: {uploaded_file.name}..."):
                    try:
                        file_data = uploaded_file.read()
                        if uploaded_file.name.lower().endswith('.pdf'):
                            img_payload = process_pdf_to_image(file_data)
                        else:
                            img_payload = file_data
                        
                        b64_img = encode_image(img_payload)

                        # PONTOSÍTOTT AI UTASÍTÁS
                        response = client.chat.completions.create(
                            model="gpt-4o",
                            messages=[{
                                "role": "user",
                                "content": [
                                    {
                                        "type": "text", 
                                        "text": """Elemezd a számlát. 
                                        FONTOS: A 'partner' mezőbe a SZÁMLA KIÁLLÍTÓJÁT (eladó/szolgáltató) írd! 
                                        JSON mezők: partner, datum, hatarido, bizonylatszam, bankszamla, osszeg, fizetesi_mod."""
                                    },
                                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_img}"}}
                                ]
                            }],
                            response_format={ "type": "json_object" }
                        )
                        
                        res_json = json.loads(response.choices[0].message.content)
                        
                        # Összeg tisztítása
                        raw_val = str(res_json.get('osszeg', 0)).replace(' ', '').replace('Ft', '').replace(',', '.')
                        try:
                            final_amt = int(round(float(raw_val)))
                        except:
                            final_amt = 0

                        uj_adat = {
                            'Saját Cég': sajat_ceg,
                            'Partner': res_json.get('partner', 'Ismeretlen'),
                            'Dátum': res_json.get('datum', ''),
                            'Határidő': res_json.get('hatarido', res_json.get('datum', '')),
                            'Bizonylatszám': res_json.get('bizonylatszam', '-'),
                            'Bankszámla': res_json.get('bankszamla', '-'),
                            'Összeg': final_amt,
                            'Fizetési mód': res_json.get('fizetesi_mod', 'Átutalás'),
                            'Státusz': 'Nyitott' if 'átutalás' in str(res_json.get('fizetesi_mod','')).lower() else 'Kifizetve'
                        }
                        
                        st.session_state.db = pd.concat([st.session_state.db, pd.DataFrame([uj_adat])], ignore_index=True)
                    except Exception as e:
                        st.error(f"Hiba a fájlnál: {uploaded_file.name} -> {e}")
            st.success("Feldolgozás kész!")

with tab2:
    if st.session_state.db.empty:
        st.info("A napló még üres. Tölts fel számlákat a 'Beolvasás' fülön!")
    else:
        # TÖRLÉS FUNKCIÓ
        with st.expander("🗑️ Sor törlése"):
            row_to_delete = st.number_input("Törlendő sor sorszáma (bal oldali szám):", min_value=0, max_value=len(st.session_state.db)-1, step=1)
            if st.button("Kiválasztott sor végleges törlése"):
                st.session_state.db = st.session_state.db.drop(st.session_state.db.index[row_to_delete]).reset_index(drop=True)
                st.rerun()

        st.subheader("Rögzített tételek")
        # Oszlopszélesség javítva
        st.dataframe(st.session_state.db, use_container_width=True, hide_index=False)
        
        # EXCEL EXPORT
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            st.session_state.db.to_excel(writer, index=False, sheet_name='Szamlak')
        
        st.download_button(
            label="📊 Összesítő Excel letöltése",
            data=output.getvalue(),
            file_name="szamlamester_export.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

with tab3:
    st.subheader("Banki egyeztetés")
    st.write("Ez a funkció összeveti a banki CSV-t a fenti listával.")
    otp_csv = st.file_uploader("OTP Banki CSV feltöltése", type="csv")
    if st.button("Párosítás indítása") and otp_csv:
        st.warning("A funkció élesítése folyamatban...")

