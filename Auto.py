import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service
import time

# ==========================================
# 🔧 CONFIGURATION
# ==========================================
START_URL = "https://ginger.bitmappro.com/annotator/sign-up"

# --- GOOGLE SHEETS CREDENTIALS ---
CREDENTIALS_JSON = r"C:\Users\Admin\Documents\Py\auto-register-485609-78daa317a6cb.json"

# --- STRICT DEFAULT VALUES ---
DEFAULT_PASS = "123456"
DEFAULT_REF_EMAIL = "iru.xfnite@gmail.com"
DEFAULT_INVITE_CODE = "MJRS0F" 

SELECTORS = {
    # --- STEP 1: BASIC INFO ---
    "email": "email",                   
    "username": "name",                 
    "password": "password",             
    "confirm_password": "confirm_password", 
    "referral_email": "referral_email",     
    "invite_code": "invitation_code",       
    "step1_next_btn": "//button[contains(., 'Next Step')]",
    
    # --- STEP 2: DETAILS ---
    "facebook": "social_network",   
    "grad_school": "graduate_school", 
    "grad_year": "graduate_year",     
    "step2_signup_btn": "//button[@type='submit']",
    
    # --- STEP 3: CANCEL ---
    "cancel_btn": "//button[contains(@class, 'cancel-button')]",
    
    # --- TOAST ERRORS (Partial matching text) ---
    "toast_email_error": "22026",      # Key part of "(22026) Email already exists."
    "toast_user_error": "37049"        # Key part of "(37049) User name has been registered"
}

# ==========================================
# 📊 GOOGLE SHEETS HELPER FUNCTIONS
# ==========================================
def connect_to_sheet(sheet_url):
    """Authenticates and returns the first worksheet of the Google Sheet."""
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_JSON, scope)
        client = gspread.authorize(creds)
        sheet = client.open_by_url(sheet_url).sheet1
        return sheet
    except Exception as e:
        st.error(f"Failed to connect to Google Sheet: {e}")
        return None

def update_gsheet_status(sheet, row_index, col_index, status_message):
    """Updates a specific cell in Google Sheets."""
    try:
        # row_index + 2: +1 for 0-index, +1 for header row
        sheet.update_cell(row_index + 2, col_index, status_message)
    except Exception as e:
        print(f"Failed to update GSheet: {e}")

def make_headers_unique(headers):
    """
    Takes a list of headers and renames duplicates/empties to ensure uniqueness.
    """
    seen_counts = {}
    unique_headers = []
    
    for col in headers:
        if not col or col.strip() == "":
            col = "Unknown_Col"
            
        original_col = col
        if col in seen_counts:
            seen_counts[col] += 1
            new_name = f"{col}_{seen_counts[col]}"
        else:
            seen_counts[col] = 0
            new_name = col
            
        unique_headers.append(new_name)
        
    return unique_headers

def find_email_column(df):
    """Smartly guesses the email column name."""
    possible_names = ['user email', 'Email:', 'Email Address', 'email', 'Email']
    for name in possible_names:
        if name in df.columns:
            return name
    return None

# ==========================================
# ⚙️ AUTOMATION LOGIC
# ==========================================
def run_bot(df, sheet_object, start_row_num, max_limit):
    """
    start_row_num: The visual row number in Excel (Header is 1, First data is 2)
    max_limit: How many rows to process
    """
    options = webdriver.ChromeOptions()
    # options.add_argument("--headless") 
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    wait = WebDriverWait(driver, 30)
    
    status_log = st.empty()
    
    # 1. IDENTIFY EMAIL COLUMN
    email_col = find_email_column(df)
    if not email_col:
        st.error("Could not find an 'Email' column. Please check headers.")
        return df

    # 2. CALCULATE DUPLICATES ON THE FULL DATASET
    # keep='first' means the first occurrence is False (Not Dup), all subsequent are True (Dup)
    # This runs on the WHOLE dataframe so the Limiter doesn't break logic.
    duplicate_mask = df.duplicated(subset=[email_col], keep='first')

    # 3. CALCULATE SLICE INDICES
    # DataFrame index 0 corresponds to Sheet Row 2.
    # So, df_start_index = sheet_row_num - 2
    start_idx = max(0, start_row_num - 2)
    end_idx = start_idx + max_limit
    
    # Slice the dataframe to only process the requested range
    df_subset = df.iloc[start_idx:end_idx]
    
    total_in_batch = len(df_subset)
    current_count = 0
    progress = st.progress(0)

    # Find Status Column Index for Google Sheets
    status_col_idx = None
    if sheet_object:
        try:
            headers = sheet_object.row_values(1)
            status_col_idx = headers.index("Status:") + 1
        except ValueError:
            st.warning("Column 'Status:' not found in Google Sheet headers.")

    try:
        # We iterate over the subset, but we need the original index for GSheet updates
        for index, row in df_subset.iterrows():
            current_count += 1
            progress.progress(current_count / total_in_batch)

            # Setup Data
            email = row.get(email_col)
            status_val = str(row.get('Status:', '')).strip()
            
            # --- CHECK 1: INTERNAL FILE DUPLICATE ---
            # If this row is a duplicate of a PREVIOUS row in the file
            if duplicate_mask[index]:
                # Only mark as DUP if it isn't already marked
                if status_val != "DUP":
                    status_log.info(f"Row {index+2}: Duplicate email found in file. Marking DUP.")
                    if 'Status:' in df.columns:
                        df.at[index, 'Status:'] = "DUP"
                    if sheet_object and status_col_idx:
                        update_gsheet_status(sheet_object, index, status_col_idx, "DUP")
                continue # Skip processing

            # --- CHECK 2: ALREADY DONE ---
            # Skip if Status is OK/DUP or Email is missing
            if pd.isna(email) or status_val in ['OK', 'DUP']:
                status_log.info(f"Skipping Row {index+2} ({status_val})")
                continue

            # Load Data
            user_name = row.get('Username: (Please create a Username with this format: FirstnameLastname Example: cedricksabrine)')
            
            # --- STRICT DEFAULTS ---
            ref_email = DEFAULT_REF_EMAIL
            inv_code = DEFAULT_INVITE_CODE
            password_to_use = DEFAULT_PASS

            status_log.info(f"Processing Sheet Row {index+2}: {email}")
            
            # Helper to update status
            def update_status(msg):
                if 'Status:' in df.columns:
                    df.at[index, 'Status:'] = msg
                if sheet_object and status_col_idx:
                    update_gsheet_status(sheet_object, index, status_col_idx, msg)

            try:
                driver.get(START_URL)

                # --- STEP 1: FILL FORM ---
                current_username = user_name
                step1_success = False
                
                # Retry loop for Username conflicts
                for attempt in range(5):
                    wait.until(EC.presence_of_element_located((By.ID, SELECTORS["email"])))
                    
                    safe_fill(driver, SELECTORS["email"], email)
                    safe_fill(driver, SELECTORS["username"], current_username)
                    safe_fill(driver, SELECTORS["password"], password_to_use)
                    safe_fill(driver, SELECTORS["confirm_password"], password_to_use)
                    safe_fill(driver, SELECTORS["referral_email"], ref_email)
                    safe_fill(driver, SELECTORS["invite_code"], inv_code)
                    
                    try:
                        driver.find_element(By.XPATH, SELECTORS["step1_next_btn"]).click()
                    except:
                        driver.find_element(By.CSS_SELECTOR, "button.ant-btn-primary").click()
                    
                    time.sleep(1.5)
                    page_source = driver.page_source.lower()
                    
                    # --- SCENARIO 1: EMAIL EXISTS (WEB CHECK) ---
                    # Logic: If website says email exists, it's valid for work (OK)
                    if SELECTORS["toast_email_error"] in page_source or "email already exists" in page_source:
                        update_status("OK") 
                        step1_success = False
                        break 
                        
                    # --- SCENARIO 2: USERNAME TAKEN ---
                    elif SELECTORS["toast_user_error"] in page_source or "user name has been registered" in page_source:
                        status_log.warning(f"Username '{current_username}' taken. Adding '_2' and retrying...")
                        current_username = f"{current_username}_2"
                        continue 
                        
                    else:
                        step1_success = True
                        break 
                
                if not step1_success:
                    continue

                # --- STEP 2: DETAILS ---
                try:
                    wait.until(EC.presence_of_element_located((By.ID, SELECTORS["facebook"])))
                    safe_fill(driver, SELECTORS["facebook"], " ")
                    safe_fill(driver, SELECTORS["grad_school"], " ")
                    safe_fill(driver, SELECTORS["grad_year"], " ")
                    driver.find_element(By.XPATH, SELECTORS["step2_signup_btn"]).click()
                except Exception as e:
                    if "email already exists" in driver.page_source.lower():
                        update_status("OK")
                        continue
                    raise e

                # --- STEP 3: CANCEL ---
                try:
                    cancel = wait.until(EC.element_to_be_clickable((By.XPATH, SELECTORS["cancel_btn"])))
                    cancel.click()
                    wait.until(EC.url_contains("login"))
                    update_status("OK")
                except:
                    update_status("OK (Manual Check)")

            except Exception as e:
                update_status("FAILED")
                print(f"Error Row {index}: {e}")
            
    finally:
        driver.quit()
        st.success("Automation Batch Complete!")
        
    return df

def safe_fill(driver, selector_id, text_value):
    try:
        elem = driver.find_element(By.ID, selector_id)
        elem.clear()
        elem.send_keys(str(text_value))
    except:
        try:
            elem = driver.find_element(By.NAME, selector_id)
            elem.clear()
            elem.send_keys(str(text_value))
        except:
            pass

# ==========================================
# 🖥️ UI
# ==========================================
st.set_page_config(page_title="Signup Bot", page_icon="🤖", layout="wide")
st.title("🤖 Auto Signup Bot")

# Tabs for input method
tab1, tab2 = st.tabs(["📂 Upload Excel/CSV", "☁️ Google Sheets"])

df = None
sheet_instance = None
data_source_name = ""

with tab1:
    uploaded_file = st.file_uploader("Upload Excel/CSV", type=['xlsx', 'csv'])
    if uploaded_file:
        if uploaded_file.name.endswith('.csv'):
            df = pd.read_csv(uploaded_file)
        else:
            df = pd.read_excel(uploaded_file)
        df.columns = make_headers_unique(df.columns)
        data_source_name = "Uploaded File"
        st.info("✅ File Loaded Successfully")

with tab2:
    sheet_url = st.text_input("Enter Google Sheet URL:")
    if sheet_url:
        sheet_instance = connect_to_sheet(sheet_url)
        if sheet_instance:
            try:
                all_data = sheet_instance.get_all_values()
                if all_data:
                    raw_headers = all_data.pop(0) 
                    clean_headers = make_headers_unique(raw_headers)
                    df = pd.DataFrame(all_data, columns=clean_headers)
                    data_source_name = "Google Sheet"
                    st.success("✅ Connected to Google Sheet")
                    st.info("Status updates will be written back to the sheet in real-time.")
                else:
                    st.warning("Sheet is empty!")
            except Exception as e:
                st.error(f"Error reading sheet data: {e}")

# ==========================================
# ▶️ RUN SECTION
# ==========================================
if df is not None:
    st.divider()
    st.subheader(f"Data Source: {data_source_name}")
    st.write("Preview of data:")
    st.dataframe(df.head())

    # --- LIMITER CONTROLS ---
    st.write("### ⚙️ Run Settings")
    c1, c2 = st.columns(2)
    with c1:
        start_row = st.number_input("Start from Sheet Row #", min_value=2, value=2, step=1, help="Row 1 is headers. Data starts at Row 2.")
    with c2:
        limit_rows = st.number_input("Max Rows to Process", min_value=1, value=50, step=1)

    st.divider()
    
    col1, col2 = st.columns([1, 4])
    with col1:
        start_btn = st.button("▶️ RUN AUTOMATION", type="primary", use_container_width=True)
    
    if start_btn:
        st.write(f"Starting bot from Row {start_row} (Limit: {limit_rows})...")
        updated_df = run_bot(df, sheet_instance, start_row, limit_rows)
        
        st.divider()
        st.write("### Final Results")
        st.dataframe(updated_df)
        csv = updated_df.to_csv(index=False).encode('utf-8')
        st.download_button("📥 Download Results CSV", csv, "results.csv", "text/csv")