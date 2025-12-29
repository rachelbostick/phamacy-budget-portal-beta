import streamlit as st
from openai import OpenAI  # Switched from google.generativeai
import pandas as pd
import json
import re
from PIL import Image
import base64
import io

# 1. Setup OpenAI (The "Copilot" Brain)
client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

st.title("Pediatric Oncology Protocol Budgeter (ChatGPT Edition)")

# Helper function to encode the image for ChatGPT
def encode_image(image):
    buffered = io.BytesIO()
    image.save(buffered, format="PNG")
    return base64.b64encode(buffered.getvalue()).decode('utf-8')

# --- INPUT SECTION 1: GATED BY FORM ---
st.header("1. Protocol AI Extraction & Enrollment Modeling")

with st.form("ai_extraction_form"):
    col_in1, col_in2 = st.columns(2)
    with col_in1:
        disease_state = st.text_input("Disease of Interest", value="Rhabdomyosarcoma")
    with col_in2:
        total_n = st.number_input("Expected Total Enrollment", value=135)

    uploaded_file = st.file_uploader("Upload Protocol Screenshot", type=["png", "jpg", "jpeg"])
    submit_button = st.form_submit_button("Run ChatGPT Extraction")

if uploaded_file is not None and submit_button:
    img = Image.open(uploaded_file)
    st.image(img, caption="Protocol Screenshot", width=400)
    base64_image = encode_image(img)

    prompt = f"""
    You are a Pediatric Oncology Research Specialist. Analyze the attached protocol for {disease_state}.
    
    TASK:
    1. Extract every drug row into a JSON list.
    2. For each age group, estimate the number of patients (N) out of {total_n} based on SEER incidence data.
    3. For EACH age group, estimate literature-informed Average Height (cm), Average Weight (kg), and Average BSA (m2).
    
    Return ONLY a JSON list with these keys:
    "Risk Group", "Drug Name", "Age Group", "Est. Patients (N)", "Est. Height (cm)", "Est. Weight (kg)", "Est. BSA (m2)", "Dose per Admin", "Units", "Calc Factor", "Total Doses"

    Rules:
    - Return valid JSON only.
    - 'Est. Patients (N)' must be a whole number. 
    - The sum of 'Est. Patients (N)' must equal {total_n}.
    - 'Calc Factor' must be 'Weight' or 'BSA'.
    """

    with st.spinner(f"ChatGPT is analyzing {disease_state} protocols..."):
        try:
            # OpenAI specific call structure
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/png;base64,{base64_image}"}
                            },
                        ],
                    }
                ],
                max_tokens=2000,
            )
            
            raw_text = response.choices[0].message.content

            # JSON extraction
            json_match = re.search(r'\[\s*\{.*\}\s*\]', raw_text, re.DOTALL)
            clean_json = json_match.group(0) if json_match else raw_text.strip()
            
            df = pd.DataFrame(json.loads(clean_json))
            st.session_state['extracted_df'] = df
            
        except Exception as e:
            st.error(f"Error: {e}")

# --- SECTION 2 & 3 (Logic remains identical to previous version) ---
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
    
    edited_costs = st.data_editor(cost_ref_df, use_container_width=True, hide_index=True)
    trial_years = st.number_input("Target Trial Run Time (Years)", value=5, min_value=1)

    if st.button("Calculate Final Budget"):
        def run_calculations(row):
            factor = str(row['Calc Factor']).lower()
            drug_meta = edited_costs[edited_costs['Drug Name'] == row['Drug Name']].iloc[0]
            
            row_weight = row.get('Est. Weight (kg)', 30.0)
            row_bsa = row.get('Est. BSA (m2)', 1.0)
            
            if 'm' in factor or 'bsa' in factor:
                dose = round(float(row['Dose per Admin']) * float(row_bsa), 3)
            else:
                dose = round(float(row['Dose per Admin']) * float(row_weight), 3)
            
            vials = int(-(-dose // drug_meta['Vial Size (mg)'])) 
            cost_admin = vials * drug_meta['Cost per Vial ($)']
            total_pt = cost_admin * int(row['Total Doses']) * int(row['Est. Patients (N)'])
            
            i = 0.04 
            total_10yr = total_pt * ((1 + i)**10 - 1) / i
            total_custom = total_pt * ((1 + i)**trial_years - 1) / i
            
            return pd.Series([dose, vials, cost_admin, total_pt, total_10yr, total_custom])

        calc_cols = ['Calculated Dose', 'Vials Required', 'Cost/Admin', 'Cohort Total', '10yr Total', f'{trial_years}yr Adjusted Total']
        df[calc_cols] = df.apply(run_calculations, axis=1)

        st.header("3. Results Summary")
        st.dataframe(df.style.format({
            'Cost/Admin': '${:,.2f}', 'Cohort Total': '${:,.2f}', 
            '10yr Total': '${:,.2f}', f'{trial_years}yr Adjusted Total': '${:,.2f}'
        }))
