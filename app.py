import streamlit as st
import pandas as pd

def page_1_wbs():
    st.header("1. High Level Work Breakdown Structure")
    st.write("Define your primary project areas.")
    
    # 1. The Data Entry Form
    # clear_on_submit=True automatically wipes the text boxes after a successful entry
    with st.form("add_wbs_form", clear_on_submit=True):
        st.subheader("Add New WBS Item")
        
        # Using columns to make the layout look cleaner
        col1, col2 = st.columns([1, 3])
        
        with col1:
            new_code = st.text_input("WBS Code", placeholder="e.g., 001")
        with col2:
            new_name = st.text_input("WBS Description", placeholder="e.g., Substructure")
            
        # The submit button that triggers the action
        submit_button = st.form_submit_button("Add item to WBS")
        
        # 2. The Logic to Append Data
        if submit_button:
            # Basic validation to ensure they didn't submit a blank form
            if new_code.strip() == "" or new_name.strip() == "":
                st.error("⚠️ Please fill in both the WBS Code and Description.")
            
            # Check for duplicate WBS codes to prevent relational issues later
            elif new_code in st.session_state.wbs_df['WBS_Code'].values:
                st.error(f"⚠️ WBS Code '{new_code}' already exists. Please use a unique code.")
            
            else:
                # Create a temporary dataframe for the new row
                new_row = pd.DataFrame([{'WBS_Code': new_code, 'WBS_Name': new_name}])
                
                # Concatenate the new row to the existing session state dataframe
                # Note: We do not use .append() as it is deprecated in newer Pandas versions
                st.session_state.wbs_df = pd.concat([st.session_state.wbs_df, new_row], ignore_index=True)
                
                st.success(f"✅ Successfully added: {new_code} - {new_name}")

    st.divider() # Visual separator

    # 3. Displaying the Updated Table
    st.subheader("Current WBS")
    
    # We can still use data_editor here so the user can edit typos or delete rows
    # after they have been added via the form.
    if not st.session_state.wbs_df.empty:
        edited_df = st.data_editor(
            st.session_state.wbs_df, 
            use_container_width=True,
            num_rows="dynamic", # Still allows row deletion
            key="wbs_table_editor"
        )
        # Update the session state if they make manual edits in the table
        st.session_state.wbs_df = edited_df
    else:
        st.info("No WBS items added yet.")
