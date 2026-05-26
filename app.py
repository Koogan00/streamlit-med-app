import streamlit as st
import json
import os
from datetime import datetime
import pandas as pd
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

# ====================== CONFIGURATION ======================
BASE_DIR = os.path.dirname(__file__)

DATA_FILE = os.path.join(BASE_DIR, "meds.json")
CACHE_FILE = os.path.join(BASE_DIR, "audit_cache.json")
HISTORY_FILE = os.path.join(BASE_DIR, "app_history.json")

# ====================== PAGE CONFIG & STYLING ======================
st.set_page_config(
    page_title="🩺 Vimalan MedAssist",
    page_icon="🩺",
    layout="wide",
    initial_sidebar_state="expanded"
)
st.markdown("""
    <style>
        .main {padding-top: 2rem;}
        h1 {font-size: 2.5rem; margin-bottom: 0.5rem;}

        /* ✅ Sidebar width + background color */
        section[data-testid="stSidebar"] {
            width: 250px !important;
            background-color: #0f172a !important;  /* 👈 change this */
        }
        div.stButton > button:first-child {
        background-color: #008080; /* Teal background */
        color: white;             /* White text */
        border: 1px solid #008080;
        }
        div.stButton > button:hover {
            background-color: #005f5f; /* Darker shade on hover */
            color: white;
        }
        section[data-testid="stSidebar"] > div {
            overflow: hidden !important
            padding-top: 1rem;
        }
    </style>
""", unsafe_allow_html=True)

# ====================== DATA LOADING ======================
@st.cache_data
def load_medicine_data():
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

medicines = load_medicine_data()
medicine_names = sorted(list(set(item["Medicine Name"] for item in medicines)))

# ====================== PERSISTENT HISTORY ======================
def load_persistent_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {"calculations": [], "recent_medicines": []}
    return {"calculations": [], "recent_medicines": []}

def save_persistent_history(data):
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

# Load history into session state
history_data = load_persistent_history()

if 'calculations' not in st.session_state:
    st.session_state.calculations = history_data.get("calculations", [])
if 'recent_medicines' not in st.session_state:
    st.session_state.recent_medicines = history_data.get("recent_medicines", [])

# ====================== MAIN APP ======================
st.markdown("# 🩺 Vimalan MedAssist")

tab1, tab2, tab3 = st.tabs(["💊 Dosage Calculator", "📊 History", "ℹ️ About"])
if "audit_result" not in st.session_state:
    st.session_state.audit_result = None

# ====================== TAB 1: DOSAGE CALCULATOR ======================
with tab1:
    col1, col2 = st.columns([2, 1])

    with col1:
        search_term = st.text_input("🔍 Search Medicine", placeholder="Type medicine name...")
        
        if search_term:
            filtered_medicines = [
                m for m in medicine_names if search_term.lower() in m.lower()
            ]
        else:
            filtered_medicines = (
                st.session_state.recent_medicines[:10] +
                [m for m in medicine_names if m not in st.session_state.recent_medicines]
            )

        selected_medicine = st.selectbox(
            "Select Medicine",
            options=filtered_medicines
        )

        # Update recent medicines
        if selected_medicine and selected_medicine not in st.session_state.recent_medicines:
            st.session_state.recent_medicines.insert(0, selected_medicine)
            if len(st.session_state.recent_medicines) > 20:
                st.session_state.recent_medicines.pop()

    with col2:
        patient_weight = st.number_input(
            "Patient Weight (kg)",
            min_value=0.5,
            max_value=150.0,
            value=10.0,
            step=0.1
        )

        num_doses = st.number_input(
            "Doses Per Day",
            min_value=1,
            max_value=12,
            value=1,
            step=1
        )

    # ====================== MEDICINE DATA & CALCULATIONS ======================
    med_data = next(
        (item for item in medicines if item["Medicine Name"] == selected_medicine),
        None
    )

    if med_data:
        dose_min = med_data.get("dose_min", 0)
        dose_max = med_data.get("dose_max", dose_min)
        dose_unit = med_data.get("dose_unit", "mg/kg")
        dose_type = med_data.get("dose_type", "per_dose")

        concentration_mg = med_data.get("concentration_mg", 0)
        concentration_ml = med_data.get("concentration_ml", 1)

        form = med_data.get("form", "N/A")
        frequency = med_data.get("usual_frequency", "N/A")

        # Concentration per mL
        default_conc = (concentration_mg / concentration_ml) if concentration_ml > 0 else None

        st.info(
            f"**Standard Dosage:** `{dose_min}-{dose_max} {dose_unit}` | "
            f"**Type:** `{dose_type}` | "
            f"**Form:** `{form}` | "
            f"**Usual Frequency:** `{frequency}`"
        )

        # Calculations
        base_dosage = dose_max

        if dose_type == "per_day":
            daily_dose = patient_weight * base_dosage
            single_dose = daily_dose / num_doses
        else:
            single_dose = patient_weight * base_dosage
            daily_dose = single_dose * num_doses

        # Volume calculation
        dose_volume = single_dose / default_conc if default_conc and default_conc > 0 else 0
        volume_display = f"{dose_volume:,.2f} mL" if dose_volume > 0 else "Tablet / Not Required"

        # ====================== RESULTS ======================
        st.markdown("### 📊 Calculation Results")
        c1, c2, c3, c4 = st.columns(4)

        with c1:
            st.metric("Daily Dose", f"{daily_dose:,.1f} mg")
        with c2:
            st.metric("Single Dose", f"{single_dose:,.1f} mg")
        with c3:
            st.metric("Volume per Dose", volume_display)
        with c4:
            st.metric(
                "Total Daily Volume",
                f"{dose_volume * num_doses:,.2f} mL" if dose_volume > 0 else "N/A"
            )

        recommendation = f"Give **{single_dose:.1f} mg** ({volume_display}) {num_doses} time(s) daily"
        if frequency != "N/A":
            recommendation += f" | Typical frequency: **{frequency}**"

        st.success(recommendation)

        # ====================== AI SAFETY AUDIT ======================
        st.markdown("### 🤖 AI Safety Verification")
        if st.button("🚀 Tekan aku kalau nak double-check", type="primary", use_container_width=False):
            with st.spinner("Engkauu sabar aku loading japp . . .", show_time=True):
                try:
                    client = OpenAI(
                        base_url="https://openrouter.ai/api/v1",
                        api_key=os.environ.get("OPENROUTER_API_KEY")
                    )

                    prompt = f"""
                    You are a senior pediatric clinical pharmacist.

                    Verify this pediatric dosage.

                    Patient weight: {patient_weight} kg
                    Medicine: {selected_medicine}

                    Calculated single dose: {single_dose:.1f} mg
                    Calculated daily dose: {daily_dose:.1f} mg
                    Volume per dose: {volume_display}
                    Doses per day: {num_doses}

                    Medicine database information:
                    - Recommended dose range: {dose_min}-{dose_max} {dose_unit}
                    - Dose type: {dose_type}
                    - Usual frequency: {frequency}

                    Tasks:
                    1. State whether the calculation is clinically appropriate.
                    2. Compare with standard pediatric dosing.
                    3. Mention if dosing frequency is unusual.
                    4. Start response with: ✅ MATCH or ⚠️ DISCREPANCY
                    5. Suggest the proper dose if there is a discrepancy based on {patient_weight} and {selected_medicine}.

                    Keep response concise and clinically accurate.
                    """

                    response = client.chat.completions.create(
                        model="nvidia/nemotron-3-super-120b-a12b:free",
                        messages=[{"role": "user", "content": prompt}],
                        max_tokens=1500,
                        temperature=0.3
                    )

                    st.session_state.audit_result = response.choices[0].message.content
                    st.info(st.session_state.audit_result)

                except Exception as e:
                    st.error(f"Audit failed: {str(e)}")
                    
                # Save to History
        if st.session_state.audit_result is not None:
            if st.button("💾 Save Result", type="primary"):
                entry = {
                    "Timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "Medicine": selected_medicine,
                    "Weight_kg": patient_weight,
                    "Single_dose_mg": round(single_dose, 1),
                    "Daily_dose_mg": round(daily_dose, 1),
                    "Volume": volume_display,
                    "Audit_Result": st.session_state.audit_result,
                }

                st.session_state.calculations.insert(0, entry)

                save_persistent_history({
                    "calculations": st.session_state.calculations,
                    "recent_medicines": st.session_state.recent_medicines
                })

                st.success("✅ Done bosskurrr!")
        else:
            st.button("💾 Save Result", disabled=True)
            st.warning("⚠️ Run AI Safety Audit before saving")

# ====================== TAB 2: HISTORY ======================
with tab2:
    if st.session_state.calculations:
        df = pd.DataFrame(st.session_state.calculations)
        st.dataframe(df, use_container_width=True)

        csv = df.to_csv(index=False)
        st.download_button(
            "📥 Download Full History",
            csv,
            "pedidose_history.csv",
            "text/csv"
        )
    else:
        st.info("No calculations saved yet.")
        
    if st.button("🗑️ Clear History", use_container_width=False):
        st.session_state.calculations = []
        save_persistent_history({
            "calculations": [],
            "recent_medicines": st.session_state.recent_medicines
        })
        st.success("History cleared!")

# ====================== TAB 3: ABOUT ======================
with tab3:
    st.markdown("""
    ### Advanced Pediatric Medication Dosage Calculator & Safety System

    The **Advanced Pediatric Medication Dosage Calculator & Safety System** is a smart clinical tool designed to accurately calculate safe and effective medication doses for children based on body weight, standard dosing guidelines, and evidence-based medical formulas.

    This application simplifies pediatric dose calculations by instantly determining the correct single dose, total daily dose, and recommended administration schedule. It also performs automatic conversions for liquid medications, ensuring clear and practical results for real-world use.

    Built with a strong focus on patient safety, the system includes validation checks against standard pediatric dosing ranges and frequency recommendations. This helps reduce medication errors and ensures that every calculated dose remains within safe clinical limits.

    Designed for healthcare professionals, pharmacists, medical students, and caregivers, the application provides fast, reliable, and easy-to-understand dosing support. Its clean interface and accurate calculations improve efficiency while prioritizing child safety in every decision.
    """)

st.caption("💙 Built for safer pediatric care | Evidence-based dosing | Precision you can trust")
