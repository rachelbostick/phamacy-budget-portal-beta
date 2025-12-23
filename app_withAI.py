import streamlit as st
import google.generativeai as genai
import pandas as pd
import json
import re
from PIL import Image 

# 1. Setup AI 
# Make sure your Streamlit Secret is set to GEMINI_API_KEY
genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
model = genai.GenerativeModel('gemini-2.5-flash')

st.title("Pediatric Oncology Protocol Budgeter")

# --- INPUT SECTION 1: AI EXTRACTION & ENROLLMENT MODELING ---
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

    prompt = f"""
    You are a Pediatric Oncology Research Specialist. Analyze the attached protocol for {disease_state}.
    
    TASK:
    1. Extract every drug row into a JSON list.
    2. For each age group found in the protocol, estimate the number of patients (N) that will fall into that group 
       out of a total enrollment of {total_n}, based on prior clinical literature and SEER incidence data for {disease_state}.
    
    Return ONLY a JSON list with these keys:
    "Risk Group", "Drug Name", "Age Group", "Est. Patients (N)", "Dose per Admin", "Units", "Calc Factor", "Total Doses"
    
    Rules:
    - 'Est. Patients (N)' must be a whole number. 
    - The sum of 'Est. Patients (N)' across unique age groups should equal {total_n}.
    - 'Dose per Admin' must be numeric.
    """

    with st.spinner(f"Consulting {disease_state} literature and extracting data..."):
        try:
            response = model.generate_content([prompt, img])
            raw_text = response.text

            # --- ROBUST JSON EXTRACTION ---
            # This finds the [...] block even if the AI added conversational text
            json_match = re.search(r'\[\s*\{.*\}\s*\]', raw_text, re.DOTALL)
            
            if json_match:
                clean_json = json_match.group(0)
            else:
                clean_json = raw_text.replace('```json', '').replace('```', '').strip()
            
            raw_data = json.loads(clean_json)
            df = pd.DataFrame(raw_data)
            
            st.session_state['extracted_df'] = df

            st.subheader("Extracted Protocol Details (with AI Enrollment Estimates)")
            st.dataframe(df, use_container_width=True)

            # --- INPUT SECTION 2: MANUAL VARIABLES ---
            st.header("2. Manual Cost & Patient Variables")
            col1, col2 = st.columns(2)
            with col1:
                cost_vial = st.number_input("Cost per Vial ($) (Col J)", value=15.58)
                vial_size = st.number_input("Vial Size (mg) (Col K)", value=1.0)
            with col2:
                weight = st.number_input("Avg Patient Weight (kg) (Col L)", value=30.0)
                bsa = st.number_input("Avg Patient BSA (m2) (Col M)", value=1.0)

            # --- CALCULATION ENGINE ---
            def run_calculations(row):
                factor = str(row['Calc Factor']).lower()
                
                # Logic to choose between BSA or Weight
                if 'm' in factor or 'bsa' in factor:
                    dose = round(row['Dose per Admin'] * bsa, 3)
                else:
                    dose = round(row['Dose per Admin'] * weight, 3)
                
                vials = int(-(-dose // vial_size)) 
                cost_admin = vials * cost_vial
                
                # Cohort Math: Cost * Doses * Number of Patients in that age group
                total_pt_cohort = cost_admin * row['Total Doses'] * row['Est. Patients (N)']
                
                # 10-Year Inflation (4%)
                inflation = 0.04 
                total_10yr = total_pt_cohort * ((1 + inflation)**10 - 1) / inflation
                
                return pd.Series([dose, vials, cost_admin, total_pt_cohort, total_10yr])

            # Applying math
            df[['Calc Dose (N)', 'Vials (O)', 'Cost/Admin (P)', 'Cohort Total (Q)', '10yr Adjusted (V)']] = df.apply(run_calculations, axis=1)

            # --- OUTPUT SECTION ---
            st.header("3. Results Summary")
            output_cols = ['Drug Name', 'Age Group', 'Est. Patients (N)', 'Calc Dose (N)', 'Cohort Total (Q)', '10yr Adjusted (V)']
            
            st.dataframe(df[output_cols].style.format({
                'Cohort Total (Q)': '${:,.2f}',
                '10yr Adjusted (V)': '${:,.2f}'
            }))

            # Grand Total Calculation
            grand_total = df['10yr Adjusted (V)'].sum()
            st.metric("Total 10-Year Protocol Budget", f"${grand_total:,.2f}")

            csv = df.to_csv(index=False).encode('utf-8')
            st.download_button("Export Full Budget to CSV", data=csv, file_name="protocol_budget.csv", mime="text/csv")

        except Exception as e:
            st.error(f"Error: {e}")
            with st.expander("Show Raw AI Response"):
                st.text(raw_text if 'raw_text' in locals() else "No response received.")
