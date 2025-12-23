import streamlit as st
import google.generativeai as genai
import pandas as pd
import json
import re
from PIL import Image 

# 1. Setup AI 
genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
model = genai.GenerativeModel('gemini-2.5-flash')

st.title("Pediatric Oncology Protocol Budgeter")

# --- SECTION 1: EXTRACTION ---
st.header("1. Protocol AI Extraction & Enrollment Modeling")

col_in1, col_in2 = st.columns(2)
with col_in1:
    disease_state = st.text_input("Disease of Interest", value="Rhabdomyosarcoma")
with col_in2:
    total_n = st.number_input("Expected Total Enrollment", value=135)

uploaded_file = st.file_uploader("Upload Protocol Screenshot", type=["png", "jpg", "jpeg"])

if uploaded_file is not None:
    img = Image.open(uploaded_file)
    st.image(img, caption="Protocol Screenshot", width=400)

    prompt = f"""Extract every drug row from this {disease_state} protocol. 
    Estimate N for each group out of {total_n} total patients based on literature.
    Return JSON list with keys: "Risk Group", "Drug Name", "Age Group", "Est. Patients (N)", "Dose per Admin", "Units", "Calc Factor", "Total Doses"."""

    if st.button("Run AI Analysis"):
        with st.spinner("Analyzing..."):
            try:
                response = model.generate_content([prompt, img])
                json_match = re.search(r'\[\s*\{.*\}\s*\]', response.text, re.DOTALL)
                clean_json = json_match.group(0) if json_match else response.text
                
                # Store data in Session State so it persists
                st.session_state['df'] = pd.DataFrame(json.loads(clean_json))
                st.success("Extraction Complete!")
            except Exception as e:
                st.error(f"AI Error: {e}")

# --- SECTION 2: MANUAL VARIABLES & CALCS ---
# We use this 'if' to ensure Section 2 only shows up AFTER the data exists
if 'df' in st.session_state:
    df = st.session_state['df']
    
    st.markdown("---")
    st.header("2. Manual Cost & Patient Variables")
    
    col1, col2 = st.columns(2)
    with col1:
        cost_vial = st.number_input("Cost per Vial ($)", value=15.58)
        vial_size = st.number_input("Vial Size (mg)", value=1.0)
    with col2:
        weight = st.number_input("Avg Patient Weight (kg)", value=30.0)
        bsa = st.number_input("Avg Patient BSA (m2)", value=1.0)

    # --- CALCULATION ENGINE ---
    def run_calculations(row):
        factor = str(row['Calc Factor']).lower()
        # Logic to choose BSA or Weight
        multiplier = bsa if ('m' in factor or 'bsa' in factor) else weight
        dose = round(float(row['Dose per Admin']) * multiplier, 3)
        vials = int(-(-dose // vial_size)) 
        cost_admin = vials * cost_vial
        total_cohort = cost_admin * int(row['Total Doses']) * int(row['Est. Patients (N)'])
        
        # 10yr Inflation (4%)
        total_10yr = total_cohort * ((1 + 0.04)**10 - 1) / 0.04
        return pd.Series([dose, vials, cost_admin, total_cohort, total_10yr])

    # Perform the math
    df[['Calc Dose', 'Vials', 'Cost/Admin', 'Cohort Total', '10yr Total']] = df.apply(run_calculations, axis=1)

    # --- SECTION 3: OUTPUT ---
    st.markdown("---")
    st.header("3. Financial Results Summary")
    
    # Display table
    st.dataframe(df.style.format({
        'Cohort Total': '${:,.2f}',
        '10yr Total': '${:,.2f}'
    }), use_container_width=True)

    # Big Metric
    st.metric("Total 10-Year Project Budget", f"${df['10yr Total'].sum():,.2f}")

    # Export
    csv = df.to_csv(index=False).encode('utf-8')
    st.download_button("Download Budget CSV", data=csv, file_name="rms_budget.csv")
