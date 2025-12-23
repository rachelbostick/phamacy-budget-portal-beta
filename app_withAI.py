import streamlit as st
import google.generativeai as genai
import pandas as pd
import json
from PIL import Image 

# 1. Setup AI & 2025 Inflation Benchmarks
genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
model = genai.GenerativeModel('gemini-2.5-flash')

# 2025 PPI & Medical Cost Trends (Weighted Estimates)
PPI_ONCOLOGY_2025 = 0.085  # Specialty drugs trending at 8.5%
MED_CPI_2025 = 0.050       # General medical services at 5.0%

st.title("RMS Protocol Budgeter: 2025 Advanced Edition")

# --- NEW: PATIENT ENROLLMENT MODELER ---
st.header("1. Literature-Informed Enrollment")
col_p1, col_p2 = st.columns(2)
with col_p1:
    disease = st.text_input("Disease State", "Pediatric Rhabdomyosarcoma")
with col_p2:
    total_enrollment = st.number_input("Total Expected Enrollment (X)", value=100)

if st.button("Estimate Age Distribution via AI"):
    dist_prompt = f"""
    Based on oncology literature for {disease}, estimate the percentage of patients 
    falling into these age groups: 
    - Less than 1 year
    - 1 to 9 years (Peak incidence)
    - 10 to 19 years
    Return ONLY a JSON: {{"<1yr": 0.10, "1-9yr": 0.50, "10-19yr": 0.40}}
    """
    response = model.generate_content(dist_prompt)
    age_dist = json.loads(response.text.strip())
    
    # Calculate N based on AI Literature percentages
    st.session_state['age_counts'] = {k: int(v * total_enrollment) for k, v in age_dist.items()}
    st.success(f"Literature-based distribution: {st.session_state['age_counts']}")

# --- INPUT SECTION 2: AI PROTOCOL EXTRACTION ---
st.header("2. Protocol AI Extraction")
uploaded_file = st.file_uploader("Upload Protocol Screenshot", type=["png", "jpg", "jpeg"])

if uploaded_file is not None:
    img = Image.open(uploaded_file)
    
    # Prompt now includes "Drug Category" for inflation weighting
    prompt = """
    Extract drug data into JSON:
    "Drug Name", "Dose per Admin", "Units", "Calc Factor", "Total Doses", "Category" (Specialty/Traditional).
    """

    with st.spinner("AI is reading protocol and applying 2025 PPI trends..."):
        response = model.generate_content([prompt, img])
        clean_json = response.text.replace('```json', '').replace('```', '').strip()
        df = pd.DataFrame(json.loads(clean_json))

        # --- UPDATED CALCULATION ENGINE (2025 PPI WEIGHTED) ---
        def run_calculations(row):
            # 1. Get N from our AI enrollment model
            # (Mapping extracted rows to our estimated age groups)
            n_patients = total_enrollment # Placeholder if AI distribution isn't run
            
            # 2. 2025 Weighted Inflation Calculation
            # Specialty drugs use 8.5%, Traditional use 5%
            inf_rate = PPI_ONCOLOGY_2025 if row['Category'] == 'Specialty' else MED_CPI_2025
            
            # 3. Standard Math
            dose = row['Dose per Admin'] * 1.0 # (Simplified for this example)
            annual_cost = (dose * 15.00) * n_patients # $15 is placeholder cost
            
            # 5 & 10 Year Adjusted Totals
            total_5yr = annual_cost * ((1 + inf_rate)**5 - 1) / inf_rate
            total_10yr = annual_cost * ((1 + inf_rate)**10 - 1) / inf_rate
            
            return pd.Series([inf_rate, total_5yr, total_10yr])

        df[['Rate', '5-Year Total', '10-Year Total']] = df.apply(run_calculations, axis=1)

        # --- FINAL OUTPUT ---
        st.header("3. Financial Results (2025 Adjusted)")
        st.dataframe(df[['Drug Name', 'Rate', '5-Year Total', '10-Year Total']].style.format({'Rate': '{:.1%}', '5-Year Total': '${:,.2f}', '10-Year Total': '${:,.2f}'}))
