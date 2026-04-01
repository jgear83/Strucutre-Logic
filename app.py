import streamlit as st
import pandas as pd

# --- 1. SESSION STATE INITIALIZATION ---
# Initialize all necessary dataframes in memory
if 'mat_rates' not in st.session_state:
    st.session_state.mat_rates = pd.DataFrame()
if 'lab_rates' not in st.session_state:
    st.session_state.lab_rates = pd.DataFrame()
if 'plant_rates' not in st.session_state:
    st.session_state.plant_rates = pd.DataFrame()
if 'wbs_df' not in st.session_state:
    st.session_state.wbs_df = pd.DataFrame(columns=['WBS_Code', 'WBS_Name'])


# --- 2. UPLOAD HELPER FUNCTION ---
def process_upload(uploaded_file, expected_columns, state_key, success_name):
    """Reads the file, validates columns, and saves to session state."""
    try:
        if uploaded_file.name.endswith('.csv'):
            df = pd.read_csv(uploaded_file)
        else:
            df = pd.read_excel(uploaded_file)
            
        missing_cols = [col for col in expected_columns if col not in df.columns]
        
        if not missing_cols:
            df = df.dropna(subset=expected_columns)
            st.session_state[state_key] = df
            st.success(f"✅ {success_name} uploaded successfully! ({len(df)} items loaded)")
            # Hide the data table inside an expander to keep the page clean
            with st.expander(f"Preview {success_name} Data"):
                st.dataframe(df, use_container_width=True)
        else:
            st.error(f"⚠️ Upload failed. Missing columns: {missing_cols}")
            st.info(f"Required headers exactly as written: {', '.join(expected_columns)}")
            
    except Exception as e:
        st.error(f"An error occurred reading the file: {e}")


# --- 3. PAGE DEFINITIONS ---

def section_1_setup():
    st.header("Section 1: Project Setup")
    st.write("Upload your master rates and project structure to begin.")
    
    # 1. Materials Upload
    st.subheader("1. Upload Material Rates")
    mat_file = st.file_uploader("Upload Materials (CSV/Excel)", type=['csv', 'xlsx'], key="mat_up")
    if mat_file:
        process_upload(mat_file, ['Material_Code', 'Description', 'Unit', 'Unit_Rate'], 'mat_rates', "Material Rates")
    st.divider()

    # 2. Labour Upload
    st.subheader("2. Upload Labour Rates")
    lab_file = st.file_uploader("Upload Labour (CSV/Excel)", type=['csv', 'xlsx'], key="lab_up")
    if lab_file:
        process_upload(lab_file, ['Trade_Code', 'Role_Description', 'Hourly_Rate'], 'lab_rates', "Labour Rates")
    st.divider()

    # 3. Plant Upload
    st.subheader("3. Upload Plant Hire Rates")
    plant_file = st.file_uploader("Upload Plant (CSV/Excel)", type=['csv', 'xlsx'], key="plant_up")
    if plant_file:
        process_upload(plant_file, ['Plant_Code', 'Equipment_Description', 'Hourly_Rate'], 'plant_rates', "Plant Rates")
    st.divider()

    # 4. WBS Upload
    st.subheader("4. Upload Work Breakdown Structure")
    wbs_file = st.file_uploader("Upload WBS (CSV/Excel)", type=['csv', 'xlsx'], key="wbs_up")
    if wbs_file:
        process_upload(wbs_file, ['WBS_Code', 'WBS_Name'], 'wbs_df', "WBS Structure")


def section_2_wbs():
    st.header("Section 2: Work Breakdown Structure (WBS)")
    st.write("Review, edit, or manually add your high-level work areas.")
    
    # Manual WBS Entry Form
    with st.form("manual_wbs_form", clear_on_submit=True):
        st.subheader("Add WBS Item Manually")
        col1, col2 = st.columns([1, 3])
        with col1:
            w_code = st.text_input("WBS Code (e.g., 001)")
        with col2:
            w_name = st.text_input("WBS Description (e.g., Substructure)")
            
        if st.form_submit_button("Add Item") and w_code and w_name:
            if w_code in st.session_state.wbs_df['WBS_Code'].values:
                st.error(f"Code '{w_code}' already exists.")
            else:
                new_row = pd.DataFrame([{'WBS_Code': w_code, 'WBS_Name': w_name}])
                st.session_state.wbs_df = pd.concat([st.session_state.wbs_df, new_row], ignore_index=True)
                st.success(f"Added {w_code} - {w_name}")
                
    st.divider()
    
    # Editable WBS Viewer
    st.subheader("Current WBS")
    if not st.session_state.wbs_df.empty:
        st.session_state.wbs_df = st.data_editor(
            st.session_state.wbs_df, 
            use_container_width=True, 
            num_rows="dynamic",
            key="wbs_editor"
        )
    else:
        st.info("No WBS items found. Please upload via Section 1 or add manually above.")


def section_3_detail_quantities():
    st.header("Section 3: Detail Quantities")
    st.info("Logic for detailing sub-items and quantifying materials will go here.")


def section_4_rate_quantities():
    st.header("Section 4: Rate Quantities")
    st.info("Logic for applying material rates to the detailed quantities will go here.")


def section_5_apply_labour_plant():
    st.header("Section 5: Apply Labour and Plant")
    st.info("Logic for allocating hours and machinery to WBS items will go here.")


def section_6_analysis():
    st.header("Section 6: Analysis")
    st.info("Dashboard, total BOQ, and productivity metrics will go here.")


# --- 4. NAVIGATION ROUTING ---
# This automatically generates the sidebar menu
pg = st.navigation([
    st.Page(section_1_setup, title="Section 1. Project Setup", icon="⚙️"),
    st.Page(section_2_wbs, title="Section 2. WBS", icon="🏗️"),
    st.Page(section_3_detail_quantities, title="Section 3. Detail Quantities", icon="📏"),
    st.Page(section_4_rate_quantities, title="Section 4. Rate Quantities", icon="💲"),
    st.Page(section_5_apply_labour_plant, title="Section 5. Apply Labour and Plant", icon="👷"),
    st.Page(section_6_analysis, title="Section 6. Analysis", icon="📊")
])

pg.run()
