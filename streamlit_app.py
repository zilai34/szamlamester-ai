import streamlit as st
import pandas as pd
from openai import OpenAI
import base64
import json
import fitz  # PyMuPDF
import io

# --- 1. OLDAL BEÁLLÍTÁSA ---
st.set_page_config(page_title="SzámlaMester AI v1.3", layout="wide")

# --- 2. JELSZÓVÉDELEM ---
if "password_correct" not in st.session_state:
    st.session_state["password_correct"] = False

def check_password():
    if not st.session_state["password_correct"]:
        pw = st.text_input("Jelszó:", type="password")
        if pw == "Tornyos2025":
            st.session_state["password_correct"] = True
            st.rerun()
        return False
    return True

if not check_password():
    st.stop()

# --- 3. API ÉS ADATBÁZIS ---
client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

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

# --- 5. FELÜLET ---
st.title("🚀 SzámlaMester AI v1.3")
tab1, tab2, tab3 = st.tabs(["📤 Beolvasás", "📋 Napló & Excel", "🏦 OTP Egyeztetés"])

with tab1:
    # Itt mondod meg, ki VAGY TE (a Vevő)
    sajat_ceg_nev = st.selectbox("Válaszd ki a saját céged (Vevő):", ["Tornyos Pékség Kft.", "DJ & K BT."])
    files = st.file_uploader("Számlák feltöltése", accept_multiple_files=True)
    
    if st.button("Feldolgozás indítása") and files:
        for f in files:
            with st.spinner(f"Feldolgozás: {f.name}..."):
                f_bytes = f.read()
                img_data = pdf_to_image(f_bytes) if f.name.lower().endswith('.pdf') else f_bytes
                b64_img = base64.b64encode(img_data).decode('utf-8')

                # SZIGORÍTOTT UTASÍTÁS: Megadjuk ki a vevő, és tiltjuk a használatát partnerként
                prompt = f"""Elemezd a számlát és adj JSON választ. 
                FONTOS: A 'partner' mezőbe CSAK az ELADÓ (szolgáltató) nevét írd! 
                TILOS a '{sajat_ceg_nev}' nevet beírni a partner mezőbe, mert ő a VEVŐ.
                Keresd meg a másik céget a számlán, aki a pénzt kéri.
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
                
                # --- AUTOMATIKUS JAVÍTÓ LOGIKA ---
                nyers_partner = res.get('partner', 'Ismeretlen')
                
                # Ha az AI mégis a te nevedet írta be (vagy annak egy részét)
                tiltott_szavak = ["tornyos", "pékség", "dj & k", "dj és k"]
                if any(szo in nyers_partner.lower() for szo in tiltott_szavak):
                    # Kényszerített hiba jelzés, hogy tudd: itt az AI elnézte
                    partner_final = "⚠️ ELLENŐRIZNI: AI hiba (Vevőt írt be)"
                else:
                    partner_final = nyers_partner
                # ---------------------------------

                uj_sor = {
                    'Saját Cég': sajat_ceg_nev,
                    'Partner': partner_final,
                    'Dátum': res.get('datum', ''),
                    'Határidő': res.get('hatarido', ''),
                    'Bizonylatszám': res.get('bizonylatszam', '-'),
                    'Bankszámla': res.get('bankszamla', '-'),
                    'Összeg': res.get('osszeg', 0),
                    'Fizetési mód': res.get('fizetesi_mod', 'Átutalás'),
                    'Státusz': 'Nyitott'
                }
                st.session_state.db = pd.concat([st.session_state.db, pd.DataFrame([uj_sor])], ignore_index=True)
        st.success("Feldolgozás kész!")

with tab2:
    st.subheader("Rögzített számlák")
    if not st.session_state.db.empty:
        # Sor törlése sorszám alapján
        with st.expander("🗑️ Hibás sor törlése"):
            del_idx = st.number_input("Törlendő sor száma:", min_value=0, max_value=len(st.session_state.db)-1, step=1)
            if st.button("Kiválasztott sor törlése"):
                st.session_state.db = st.session_state.db.drop(st.session_state.db.index[del_idx]).reset_index(drop=True)
                st.rerun()

        st.dataframe(st.session_state.db, use_container_width=True)
        
        # Excel letöltés
        output = io.BytesIO()
        st.session_state.db.to_excel(output, index=False, engine='xlsxwriter')
        st.download_button(label="📥 Excel Letöltése", data=output.getvalue(), file_name="szamlak.xlsx")
    else:
        st.info("Nincs adat.")
