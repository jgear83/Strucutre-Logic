import streamlit as st
import pandas as pd

# --- 1. SESSION STATE INITIALIZATION ---
# This ensures our variables exist in memory before the pages try to load them.
if 'master_rates' not in st.session_state:
    st.session_state.master_rates = None

if 'wbs_df' not in st.session_state:
    st.session_state.wbs_df = pd.DataFrame(columns=['WBS_Code', 'WBS_Name'])


# --- 2. PAGE FUNCTIONS ---
def page_0_setup():
    st.header("Project Setup: Master Schedule of Rates")
    st.write("Upload your current rates schedule to begin estimating.")
    
    # Expected columns for validation
    expected_columns = ['Item Code', 'Description', 'Category', 'Unit', 'Rate']
    
    uploaded_file = st.file_uploader("Upload Master Rates (CSV or Excel)", type=['csv', 'xlsx'])
    
    if uploaded_file is not None:
        try:
            if uploaded_file.name.endswith('.csv'):
                df = pd.read_csv(uploaded_file)
            else:
                df = pd.read_excel(uploaded_file)
                
            missing_cols = [col for col in expected_columns if col not in df.columns]
            
            if not missing_cols:
                st.session_state.master_rates = df
                st.success("✅ Master rates uploaded and verified successfully!")
                with st.expander("Preview Uploaded Rates"):
                    st.dataframe(df, use_container_width=True)
            else:
                st.error(f"⚠️ Upload failed. Missing columns: {missing_cols}")
                st.info(f"Please ensure your headers match: {', '.join(expected_columns)}")
        except Exception as e:
            st.error(f"An error occurred reading the file: {e}")

def page_1_wbs():
    st.header("1. High Level Work Breakdown Structure")
    
    # The Data Entry Form
    with st.form("add_wbs_form", clear_on_submit=True):
        st.subheader("Add New WBS Item")
        col1, col2 = st.columns([1, 3])
        
        with col1:
            new_code = st.text_input("WBS Code", placeholder="e.g., 001")
        with col2:
            new_name = st.text_input("WBS Description", placeholder="e.g., Substructure")
            
        submit_button = st.form_submit_button("Add item to WBS")
        
        if submit_button:
            if new_code.strip() == "" or new_name.strip() == "":
                st.error("⚠️ Please fill in both the WBS Code and Description.")
            elif new_code in st.session_state.wbs_df['WBS_Code'].values:
                st.error(f"⚠️ WBS Code '{new_code}' already exists. Use a unique code.")
            else:
                new_row = pd.DataFrame([{'WBS_Code': new_code, 'WBS_Name': new_name}])
                st.session_state.wbs_df = pd.concat([st.session_state.wbs_df, new_row], ignore_index=True)
                st.success(f"✅ Successfully added: {new_code} - {new_name}")

    st.divider()
    
    # Display the editable table
    st.subheader("Current WBS")
    if not st.session_state.wbs_df.empty:
        edited_df = st.data_editor(
            st.session_state.wbs_df, 
            use_container_width=True,
            num_rows="dynamic",
            key="wbs_table_editor"
        )
        st.session_state.wbs_df = edited_df
    else:
        st.info("No WBS items added yet. Use the form above to start building your structure.")


# --- 3. NAVIGATION ROUTING ---
# This block is what actually executes the functions and renders them to the screen!
pg = st.navigation([
    st.Page(page_0_setup, title="Step 0: Setup Rates", icon="⚙️"),
    st.Page(page_1_wbs, title="1. High Level WBS", icon="🏗️")
])

pg.run()
