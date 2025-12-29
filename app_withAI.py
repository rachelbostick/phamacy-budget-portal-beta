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

# --- INPUT SECTION 1 ---
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
    2. For each age group, estimate the number of patients (N) out of {total_n} based on SEER incidence data.
    3. For EACH age group, estimate literature-informed Average Height (cm), Average Weight (kg), and Average BSA (m2).
    
    Return ONLY a JSON list with these keys:
    "Risk Group", "Drug Name", "Age Group", "Est. Patients (N)", "Est. Height (cm)", "Est. Weight (kg)", "Est. BSA (m2)", "Dose per Admin", "Units", "Calc Factor", "Total Doses"
    
    Rules:
    - 'Est. Patients (N)' must be a whole number. 
    - 'Dose per Admin' must be numeric.
    - 'Units' must be 'mg/kg' or 'mg/m2'.
    """

    with st.spinner(f"Consulting {disease_state} literature..."):
        try:
            response = model.generate_content([prompt, img])
            raw_text = response.text

            json_match = re.search(r'\[\s*\{.*\}\s*\]', raw_text, re.DOTALL)
            clean_json = json_match.group(0) if json_match else raw_text.strip()
            
            raw_data = json.loads(clean_json)
            df = pd.DataFrame(raw_data)
            st.session_state['extracted_df'] = df

            st.subheader("Extracted Protocol Details")
            st.dataframe(df, use_container_width=True)

            # --- INPUT SECTION 2: MANUAL VARIABLES ---
            st.header("2. Manual Cost Variables")
            col1, col2 = st.columns(2)
            with col1:
                cost_vial = st.number_input("Cost per Vial ($)", value=15.58)
                vial_size = st.number_input("Vial Size (mg)", value=1.0)
            with col2:
                # Global fallbacks if AI fails to estimate a specific row
                global_weight = 30.0
                global_bsa = 1.0

            # --- CALCULATION ENGINE ---
            def run_calculations(row):
                factor = str(row['Calc Factor']).lower()
                
                # Use AI-estimated metrics if available, otherwise global fallback
                row_weight = row.get('Est. Weight (kg)', global_weight)
                row_bsa = row.get('Est. BSA (m2)', global_bsa)
                
                if 'm' in factor or 'bsa' in factor:
                    dose = round(float(row['Dose per Admin']) * float(row_bsa), 3)
                else:
                    dose = round(float(row['Dose per Admin']) * float(row_weight), 3)
                
                vials = int(-(-dose // vial_size)) 
                cost_admin = vials * cost_vial
                total_pt = cost_admin * int(row['Total Doses']) * int(row['Est. Patients (N)'])
                
                inflation = 0.04 
                total_10yr = total_pt * ((1 + inflation)**10 - 1) / inflation
                
                return pd.Series([dose, vials, cost_admin, total_pt, total_10yr])

            calc_cols = ['Calculated Dose', 'Vials Required', 'Cost/Admin', 'Cohort Total', '10yr Total']
            df[calc_cols] = df.apply(run_calculations, axis=1)

            # --- OUTPUT SECTION ---
            st.header("3. Results Summary")
            
            # This is the area where your SyntaxError was occurring
            output_columns = [
                'Drug Name', 'Age Group', 'Est. Patients (N)', 
                'Est. Weight (kg)', 'Est. BSA (m2)', 'Calculated Dose', 
                'Cost/Admin', 'Cohort Total', '10yr Total'
            ]
            
            st.dataframe(df[output_columns].style.format({
                'Cost/Admin': '${:,.2f}',
                'Cohort Total': '${:,.2f}',
                '10yr Total': '${:,.2f}'
            }))

            csv = df.to_csv(index=False).encode('utf-8')
            st.download_button("Export Results", data=csv, file_name="budget.csv", mime="text/csv")

        except Exception as e:
            st.error(f"Error: {e}")
