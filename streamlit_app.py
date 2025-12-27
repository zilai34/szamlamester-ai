import streamlit as st
import pandas as pd
from openai import OpenAI
import base64
import json
import fitz  # PyMuPDF
import io

# --- 1. ALAPBEÁLLÍTÁSOK ---
st.set_page_config(page_title="SzámlaMester AI v1.3", layout="wide")

# Design - sötét gombok, tiszta felület
st.markdown("""
    <style>
    .stButton>button { width: 100%; border-radius: 10px; background-color: #2c3e50; color: white; height: 3em; }
    .stDataFrame { border: 1px solid #e6e9ef; border-radius: 10px; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. JELSZÓVÉDELEM ---
if "password_correct" not in st.session_state:
    st.session_state["password_correct"] = False

def check_password():
    if not st.session_state["password_correct"]:
        pw = st.text_input("Kérlek, add meg a jelszót:", type="password")
        if pw == "Tornyos2025":
            st.session_state["password_correct"] = True
            st.rerun()
        elif pw != "":
            st.error("Hibás jelszó!")
        return False
    return True

if not check_password():
    st.stop()

# --- 3. API ÉS ADATOK ---
if "OPENAI_API_KEY" in st.secrets:
    client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
else:
    st.error("HIBA: Az OpenAI kulcs hiányzik a Secrets-ből!")
    st.stop()

if 'db' not in st.session_state:
    st.session_state.db = pd.DataFrame(columns=[
        'Saját Cég', 'Partner', 'Dátum', 'Határidő', 'Bizonylatszám', 'Bankszámla', 'Összeg', 'Fizetési mód', 'Státusz'
    ])

# --- 4. SEGÉDFÜGGVÉNYEK ---
def pdf_to_image(file_bytes):
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    page = doc.load_page(0)
    pix = page.get_pixmap(dpi=300)
    return pix.tobytes("jpg")

def encode_image(image_bytes):
    return base64.b64encode(image_bytes).decode('utf-8')

# --- 5. FELHASZNÁLÓI FELÜLET ---
st.title("🚀 SzámlaMester AI v1.3")

tab1, tab2, tab3 = st.tabs(["📤 Beolvasás", "📋 Napló & Excel", "🏦 OTP Egyeztetés"])

with tab1:
    col1, col2 = st.columns([1, 2])
    with col1:
        # Itt választod ki, ki VAGY TE (Vevő)
        sajat_ceg_nev = st.selectbox("Melyik céged nevére rögzítsünk?", ["Tornyos Pékség Kft.", "DJ & K BT."])
        files = st.file_uploader("Számlák (Kép vagy PDF)", accept_multiple_files=True)
        
        if st.button("Feldolgozás indítása") and files:
            for f in files:
                with st.spinner(f"Feldolgozás: {f.name}..."):
                    # Kép előkészítése
                    f_bytes = f.read()
                    img_data = pdf_to_image(f_bytes) if f.name.lower().endswith('.pdf') else f_bytes
                    b64_img = encode_image(img_data)

                    # A tiltólista: nevek, amiket az AI nem írhat a Partner mezőbe
                    tiltolista = "Tornyos Pékség Kft., DJ & K BT., Tornyos Pekseg, DJ és K Bt"

                    # AZ AI UTASÍTÁSA - Nagyon szigorúan
                    prompt = f"""Elemezd a számlát. 
                    A 'partner' mezőbe CSAK a számla KIÁLLÍTÓJÁT (eladó) írd! 
                    TILOS a partnerhez a vevőt írni. 
                    A vevő neve ezen a számlán ez: {sajat_ceg_nev}. Ezt SOHA ne írd a partner mezőbe!
                    JSON mezők: partner, datum, hatarido, bizonylatszam, bankszamla, osszeg, fizetesi_mod."""

                    response = client.chat.completions.create(
                        model="gpt-4o",
                        messages=[{"role": "user", "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_img}"}}
                        ]}],
                        response_format={ "type": "json_object" }
                    )
                    
                    res = json.loads(response.choices[0].message.content)
                    
                    # Utólagos szoftveres javítás (Ha az AI mégis hibázna)
                    partner_neve = res.get('partner', 'Ismeretlen')
                    if any(x.lower() in partner_neve.lower() for x in ["Tornyos", "DJ & K", "DJ és K"]):
                        partner_neve = "ELLENŐRIZNI: AI hiba"

                    # Számok rendbetétele
                    try:
                        osszeg_tisztitott = int(round(float(str(res.get('osszeg', 0)).replace(' ', '').replace('Ft', '').replace(',', '.'))))
                    except:
                        osszeg_tisztitott = 0

                    uj_sor = {
                        'Saját Cég': sajat_ceg_nev,
                        'Partner': partner_neve,
                        'Dátum': res.get('datum', ''),
                        'Határidő': res.get('hatarido', ''),
                        'Bizonylatszám': res.get('bizonylatszam', '-'),
                        'Bankszámla': res.get('bankszamla', '-'),
                        'Összeg': osszeg_tisztitott,
                        'Fizetési mód': res.get('fizetesi_mod', 'Átutalás'),
                        'Státusz': 'Nyitott' if 'utal' in str(res.get('fizetesi_mod','')).lower() else 'Kifizetve'
                    }
                    st.session_state.db = pd.concat([st.session_state.db, pd.DataFrame([uj_sor])], ignore_index=True)
            st.success("Kész!")

with tab2:
    if not st.session_state.db.empty:
        st.subheader("Rögzített számlák")
        
        # Törlési lehetőség
        with st.expander("🗑️ Hibás sor törlése"):
            idx = st.number_input("Sor sorszáma:", min_value=0, max_value=len(st.session_state.db)-1, step=1)
            if st.button("Sor végleges törlése"):
                st.session_state.db = st.session_state.db.drop(st.session_state.db.index[idx]).reset_index(drop=True)
                st.rerun()

        st.dataframe(st.session_state.db, use_container_width=True)
        
        # Excel letöltés
        towrite = io.BytesIO()
        st.session_state.db.to_excel(towrite, index=False, engine='xlsxwriter')
        st.download_button(label="📥 Excel Letöltése", data=towrite.getvalue(), file_name="szamlak.xlsx")
    else:
        st.info("Még nincs beolvasott számla.")

with tab3:
    st.subheader("OTP Banki egyeztetés")
    st.write("Hamarosan...")
