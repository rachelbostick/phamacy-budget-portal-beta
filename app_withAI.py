import streamlit as st
import google.generativeai as genai
import pandas as pd
import json
from PIL import Image 

# 1. Setup AI 
# Ensure your Streamlit Secret is set to GEMINI_API_KEY
genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
model = genai.GenerativeModel('gemini-2.5-flash')

st.title("Pediatric Oncology Protocol Budgeter")

# --- INPUT SECTION 1: AI EXTRACTION ---
st.header("1. Protocol AI Extraction")
uploaded_file = st.file_uploader("Upload Protocol Screenshot", type=["png", "jpg", "jpeg"])

if uploaded_file is not None:
    img = Image.open(uploaded_file)
    st.image(img, caption="Protocol Screenshot", width=400)

    prompt = """
    You are a Pharmacy Budget Specialist. Look at the attached protocol table. 
    Extract every drug row and return a JSON list where each object has these keys exactly:
    "Risk Group", "Drug Name", "Age Group", "Dose per Admin", "Units", "Calc Factor", "Total Doses".
    
    Strict Rules:
    - 'Dose per Admin' must be a numeric value only.
    - 'Units' must be 'mg/kg' or 'mg/m2'.
    - 'Calc Factor' must be 'Weight' or 'BSA'.
    - 'Total Doses' must be the total count of administrations for the entire trial.
    """

    with st.spinner("AI is reading the protocol..."):
        try:
            response = model.generate_content([prompt, img])
            clean_json = response.text.replace('```json', '').replace('```', '').strip()
            raw_data = json.loads(clean_json)
            df = pd.DataFrame(raw_data)
            
            st.subheader("Extracted Protocol Details (Columns B-H)")
            st.dataframe(df)
            
            # --- INPUT SECTION 2: MANUAL VARIABLES ---
            st.header("2. Manual Cost & Patient Variables")
            col1, col2 = st.columns(2)
            with col1:
                cost_vial = st.number_input("Cost per Vial ($) (Col J)", value=15.58)
                vial_size = st.number_input("Vial Size (mg) (Col K)", value=1.0)
            with col2:
                weight = st.number_input("Avg Patient Weight (kg) (Col L)", value=30.0)
                bsa = st.number_input("Avg Patient BSA (m2) (Col M)", value=1.0)

            # --- CALCULATION ENGINE (Columns N-V) ---
            def run_calculations(row):
                # Col N: Calculated Dose (rounded to 3 decimals)
                dose = round(row['Dose per Admin'] * (weight if row['Calc Factor'] == "Weight" else bsa), 3)
                # Col O: Vials Required (Ceiling Math)
                vials = int(-(-dose // vial_size)) 
                # Col P: Cost per Admin
                cost_admin = vials * cost_vial
                # Col Q: Total Cost per Patient
                total_pt = cost_admin * row['Total Doses']
                
                # Inflation Math (Col T & V) - 4% annual inflation over 10 years
                inflation = 0.04 
                total_10yr = total_pt * ((1 + inflation)**10 - 1) / inflation
                
                return pd.Series([dose, vials, cost_admin, total_pt, total_10yr])

            # Apply math and create the new columns
            df[['Calculated Dose (N)', 'Vials Required (O)', 'Cost per Administration (P)', 'Total Cost per Patient (Q)', '10 Adjusted Year Total (V)']] = df.apply(run_calculations, axis=1)

            # --- OUTPUT SECTION ---
            st.header("3. Results Summary")
            
            # Displaying the specific columns you requested: N, O, P, Q, and V
            output_columns = ['Drug Name', 'Calculated Dose (N)', 'Vials Required (O)', 'Cost per Administration (P)', 'Total Cost per Patient (Q)', '10 Adjusted Year Total (V)']
            st.dataframe(df[output_columns].style.format({
                'Cost per Administration (P)': '${:,.2f}',
                'Total Cost per Patient (Q)': '${:,.2f}',
                '10 Adjusted Year Total (V)': '${:,.2f}'
            }))

            # Export to CSV
            csv = df.to_csv(index=False).encode('utf-8')
            st.download_button("Export Full Budget to Spreadsheet", data=csv, file_name="protocol_budget.csv", mime="text/csv")

        except Exception as e:
            st.error(f"Error processing protocol: {e}")
