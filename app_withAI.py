import streamlit as st
import google.generativeai as genai
import pandas as pd
import json
import re
from PIL import Image

# 1. Setup AI 
genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
model = genai.GenerativeModel('gemini-2.0-flash')

st.title("Pediatric Oncology Protocol Budgeter")

# --- INPUT SECTION 1: GATED BY FORM ---
st.header("1. Protocol AI Extraction & Enrollment Modeling")

with st.form("ai_extraction_form"):
    col_in1, col_in2 = st.columns(2)
    with col_in1:
        disease_state = st.text_input("Disease of Interest", value="Rhabdomyosarcoma")
    with col_in2:
        total_n = st.number_input("Expected Total Enrollment", value=135)

    uploaded_file = st.file_uploader("Upload Protocol Screenshot", type=["png", "jpg", "jpeg"])
    
    # The form submit button
    submit_button = st.form_submit_button("Run AI Extraction")

if uploaded_file is not None and submit_button:
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
    - The sum of 'Est. Patients (N)' across unique age groups should equal {total_n}.
    - 'Dose per Admin' must be numeric.
    - 'Units' must be 'mg/kg' or 'mg/m2'.
    - 'Calc Factor' must be 'Weight' or 'BSA'.
    - 'Total Doses' must be the total count of administrations for the entire trial.
    """

    with st.spinner(f"AI is consulting {disease_state} literature..."):
        try:
            response = model.generate_content([prompt, img])
            raw_text = response.text

            json_match = re.search(r'\[\s*\{.*\}\s*\]', raw_text, re.DOTALL)
            clean_json = json_match.group(0) if json_match else raw_text.strip()
            
            raw_data = json.loads(clean_json)
            df = pd.DataFrame(raw_data)
            
            # Store in session state so it persists when we edit costs later
            st.session_state['extracted_df'] = df
            
        except Exception as e:
            st.error(f"Error: {e}")

# --- SECTION 2 & 3: RUN ONLY IF WE HAVE DATA ---
if 'extracted_df' in st.session_state:
    df = st.session_state['extracted_df']
    
    st.subheader("Extracted Protocol Details")
    st.dataframe(df, use_container_width=True)

    st.header("2. Drug-Specific Cost & Timeline Inputs")
    
    unique_drugs = df['Drug Name'].unique()
    cost_ref_df = pd.DataFrame({
        'Drug Name': unique_drugs,
        'Cost per Vial ($)': [15.58] * len(unique_drugs),
        'Vial Size (mg)': [1.0] * len(unique_drugs)
    })
    
    st.subheader("Edit Vial Costs and Sizes")
    edited_costs = st.data_editor(cost_ref_df, use_container_width=True, hide_index=True)
    
    trial_years = st.number_input("Target Trial Run Time (Years)", value=5, min_value=1)

    # ADDED: Button to trigger calculations so the app doesn't refresh constantly
    if st.button("Calculate Final Budget"):
        
        def run_calculations(row):
            factor = str(row['Calc Factor']).lower()
            drug_meta = edited_costs[edited_costs['Drug Name'] == row['Drug Name']].iloc[0]
            c_vial = drug_meta['Cost per Vial ($)']
            v_size = drug_meta['Vial Size (mg)']
            
            row_weight = row.get('Est. Weight (kg)', 30.0)
            row_bsa = row.get('Est. BSA (m2)', 1.0)
            
            if 'm' in factor or 'bsa' in factor:
                dose = round(float(row['Dose per Admin']) * float(row_bsa), 3)
            else:
                dose = round(float(row['Dose per Admin']) * float(row_weight), 3)
            
            vials = int(-(-dose // v_size)) 
            cost_admin = vials * c_vial
            total_pt = cost_admin * int(row['Total Doses']) * int(row['Est. Patients (N)'])
            
            i = 0.04 
            total_10yr = total_pt * ((1 + i)**10 - 1) / i
            total_custom = total_pt * ((1 + i)**trial_years - 1) / i
            
            return pd.Series([dose, vials, cost_admin, total_pt, total_10yr, total_custom])

        calc_cols = ['Calculated Dose', 'Vials Required', 'Cost/Admin', 'Cohort Total', '10yr Total', f'{trial_years}yr Adjusted Total']
        df[calc_cols] = df.apply(run_calculations, axis=1)

        st.header("3. Results Summary")
        output_columns = [
            'Drug Name', 'Age Group', 'Est. Patients (N)', 
            'Calculated Dose', 'Cost/Admin', 'Cohort Total', 
            '10yr Total', f'{trial_years}yr Adjusted Total'
        ]
        
        st.dataframe(df[output_columns].style.format({
            'Cost/Admin': '${:,.2f}',
            'Cohort Total': '${:,.2f}',
            '10yr Total': '${:,.2f}',
            f'{trial_years}yr Adjusted Total': '${:,.2f}'
        }))

        csv = df.to_csv(index=False).encode('utf-8')
        st.download_button("Export Results", data=csv, file_name="budget.csv", mime="text/csv")
