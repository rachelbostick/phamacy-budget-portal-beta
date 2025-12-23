streamlit as st
import google.generativeai as genai
import pandas as pd
import json
from PIL import Image 

# 1. Setup AI 
# Ensure your Streamlit Secret is set to GEMINI_API_KEY
genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
model = genai.GenerativeModel('gemini-2.5-flash')

st.title("Pediatric Oncology Protocol Budgeter")

# --- INPUT SECTION 1: AI EXTRACTION & ENROLLMENT MODELING ---
import json
from PIL import Image

st.header("1. Protocol AI Extraction & Enrollment Modeling")

# New User Inputs for Literature-Based Estimation
col_in1, col_in2 = st.columns(2)
with col_in1:
    disease_state = st.text_input("Disease of Interest", value="Rhabdomyosarcoma")
with col_in2:
    total_n = st.number_input("Expected Total Enrollment", value=135)

uploaded_file = st.file_uploader("Upload Protocol Screenshot", type=["png", "jpg", "jpeg"])

if uploaded_file is not None:
    img = Image.open(uploaded_file)
    st.image(img, caption="Protocol Screenshot", width=400)

    # REFINED PROMPT: Combines Extraction + Literature Estimation
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
            
            # Clean and parse the response
            clean_json = response.text.replace('```json', '').replace('```', '').strip()
            raw_data = json.loads(clean_json)
            df = pd.DataFrame(raw_data)
            
            # Save the patient counts to session state so they can be used in the next section's math
            st.session_state['extracted_df'] = df

            # Show the "Extracted" data with the new N column
            st.subheader("Extracted Protocol Details (including AI Enrollment Estimates)")
            st.dataframe(df, use_container_width=True)
            st.info(f"Note: 'Est. Patients (N)' is calculated based on {disease_state} incidence literature.")
            
        except Exception as e:
            st.error(f"Error during AI extraction: {e}")
            if 'response' in locals():
                st.write("Raw AI Output for debugging:", response.text)
            
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
