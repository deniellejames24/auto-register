import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service
import time
from datetime import datetime
import re
import json
import os

# 1️⃣ PAGE CONFIG MUST BE FIRST
st.set_page_config(page_title="Auto Admin Bot", page_icon="🤖", layout="wide")

# ==========================================
# 🎨 CUSTOM CSS FOR STYLING
# ==========================================
st.markdown("""
<style>
    .stButton>button {
        width: 100%;
        border-radius: 5px;
        height: 3em;
    }
    .reportview-container .main .block-container {
        padding-top: 2rem;
    }
    div[data-testid="stMetricValue"] {
        font-size: 24px;
    }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 🔧 CONFIGURATION & SELECTORS (SAME AS BEFORE)
# ==========================================
# ... [Keep your existing SELECTORS dictionary here] ...
SELECTORS = {
    "login_url": "https://ginger.bitmappro.com/login",
    "email_input": "email",
    "password_input": "password",
    "login_btn": "//button[contains(@class, 'login-btn')]",
    "avatar_btn": "avatar_in_header",
    "username_display": "//span[contains(@class, 'user-title')]",
    "training_url": "https://ginger.bitmappro.com/annotation/training",
    "training_row": "//tr[.//td[contains(., 'Standard Building')]]",
    "training_status_badge": ".//td[4]//span[contains(@class, 'ant-badge-status-text')]",
    "profile_url": "https://ginger.bitmappro.com/account/profile",
    "edit_pass_icon": "//label[contains(text(), 'Password')]/following-sibling::div//span[contains(@class, 'anticon-form')]",
    "input_current": "change-password_current_password",
    "input_new": "change-password_password",
    "input_confirm": "change-password_confirm_new_password",
    "modal_submit": "//div[contains(@class, 'modal-footer')]//button[contains(., 'Submit')]",
    "modal_cancel": "//div[contains(@class, 'modal-footer')]//button[contains(., 'Cancel')]",
    "toast_success": "//div[contains(@class, 'ant-message-success')]//span[contains(., 'Password updated')]",
    "toast_invalid_pass": "//div[contains(@class, 'ant-message-error')]//span[contains(., 'Invalid password')]",
    "inline_error": "//div[contains(@class, 'ant-form-item-explain-error')]",
    "logout_url": "https://ginger.bitmappro.com/logout"
}

# ==========================================
# 📊 HELPER FUNCTIONS (SAME AS BEFORE)
# ==========================================
FALLBACK_FILE = "fallback_passwords.json"

def load_fallback_passwords():
    if os.path.exists(FALLBACK_FILE):
        try:
            with open(FALLBACK_FILE, "r") as f:
                return json.load(f)
        except:
            return ["123Qwe"] 
    return ["123Qwe"] 

def save_fallback_passwords(pass_list):
    with open(FALLBACK_FILE, "w") as f:
        json.dump(pass_list, f)

def connect_to_sheet(json_key_path, sheet_url):
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name(json_key_path, scope)
        client = gspread.authorize(creds)
        sheet = client.open_by_url(sheet_url).sheet1
        return sheet
    except Exception as e:
        st.sidebar.error(f"❌ Connection Error: {e}")
        return None

def clean_headers(headers):
    seen = {}
    cleaned = []
    for i, col in enumerate(headers):
        col = str(col).strip()
        if col == "":
            col = f"Unknown_Col_{i}"
        if col in seen:
            seen[col] += 1
            new_col = f"{col}_{seen[col]}"
        else:
            seen[col] = 0
            new_col = col
        cleaned.append(new_col)
    return cleaned

def find_column_by_keyword(headers, keyword):
    for i, col in enumerate(headers):
        if keyword.lower() in str(col).lower():
            return i + 1, col 
    return None, None

def validate_password_strength(password):
    if len(password) < 6: return False
    if not re.search(r"[a-z]", password): return False
    if not re.search(r"[A-Z]", password): return False
    if not re.search(r"\d", password): return False
    return True

# ==========================================
# ⚙️ AUTOMATION LOGIC (SAME AS BEFORE)
# ==========================================
def run_bot(selected_rows, do_username, do_password, new_password, fallback_passwords, json_path, sheet_url, 
            user_col_idx, user_col_name, pass_col_idx, pass_col_name, fullname_col_name, 
            status_col_idx, status_col_name):
    
    options = webdriver.ChromeOptions()
    options.add_argument("--start-maximized")
    prefs = {"credentials_enable_service": False, "profile.password_manager_enabled": False}
    options.add_experimental_option("prefs", prefs)
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)

    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    wait = WebDriverWait(driver, 15)
    
    sheet_obj = connect_to_sheet(json_path, sheet_url)
    if not sheet_obj: return

    # --- 🆕 UI: STATUS CONTAINER ---
    status_container = st.status("🚀 Starting Automation...", expanded=True)
    progress_bar = status_container.progress(0)
    
    if 'logs' not in st.session_state: st.session_state['logs'] = []
    
    def log_result(full_name, email, action, old_val, new_val, status):
        entry = {
            "Time": datetime.now().strftime("%H:%M:%S"),
            "Full Name": full_name,
            "Email": email,
            "Action": action,
            "Before": str(old_val), 
            "After": str(new_val),
            "Status": status
        }
        st.session_state['logs'].append(entry)
        # Updates the message in the status container
        status_container.write(f"**{full_name}:** {action} -> {status}")

    # --- MAIN LOOP ---
    total_users = len(selected_rows)
    for i, (index, row) in enumerate(selected_rows.iterrows()):
        progress_bar.progress((i + 1) / total_users)
        
        email = str(row['bitmappro Email login:']).strip()
        current_pass = str(row['bitmappro Password: (Default is 123456)']).strip()
        full_name = str(row.get(fullname_col_name, "Unknown")).strip()
        sheet_username = str(row.get(user_col_name, "")).strip()
        current_status = str(row.get(status_col_name, "")).strip()
        sheet_row_num = row['original_index'] + 2 
        active_login_pass = current_pass 

        status_container.update(label=f"Processing {i+1}/{total_users}: {full_name}", state="running")

        try:
            # 1. LOGIN
            driver.get(SELECTORS["login_url"])
            wait.until(EC.presence_of_element_located((By.ID, SELECTORS["email_input"])))
            
            passwords_to_try = list(dict.fromkeys([current_pass] + fallback_passwords))
            login_success = False
            
            for attempt_pass in passwords_to_try:
                driver.find_element(By.ID, SELECTORS["email_input"]).clear()
                driver.find_element(By.ID, SELECTORS["email_input"]).send_keys(email)
                driver.find_element(By.ID, SELECTORS["password_input"]).clear()
                driver.find_element(By.ID, SELECTORS["password_input"]).send_keys(attempt_pass)
                wait.until(EC.element_to_be_clickable((By.XPATH, SELECTORS["login_btn"]))).click()
                try:
                    WebDriverWait(driver, 4).until(lambda d: "/login" not in d.current_url)
                    login_success = True
                    active_login_pass = attempt_pass
                    if active_login_pass != current_pass:
                        sheet_obj.update_cell(sheet_row_num, pass_col_idx, active_login_pass)
                        st.session_state['df'].at[index, pass_col_name] = active_login_pass
                        log_result(full_name, email, "Fix Password", current_pass, active_login_pass, "Updated ✅")
                    break 
                except TimeoutException:
                    continue
            
            if not login_success:
                log_result(full_name, email, "Login Failed", "All Fallbacks", "-", "Skipped Row ❌")
                continue 

            # Status Update
            if current_status == "" and status_col_idx:
                try:
                    sheet_obj.update_cell(sheet_row_num, status_col_idx, "OK")
                    st.session_state['df'].at[index, status_col_name] = "OK"
                    log_result(full_name, email, "Status Update", "Blank", "OK", "Saved ✅")
                except Exception as e:
                    log_result(full_name, email, "Status Update", "Blank", "Error", str(e)[:10])

            # 2. USERNAME
            if do_username:
                try:
                    avatar = wait.until(EC.element_to_be_clickable((By.ID, SELECTORS["avatar_btn"])))
                    avatar.click()
                    site_user_elem = wait.until(EC.visibility_of_element_located((By.XPATH, SELECTORS["username_display"])))
                    site_username = site_user_elem.text.strip()
                    if site_username != sheet_username:
                        sheet_obj.update_cell(sheet_row_num, user_col_idx, site_username)
                        st.session_state['df'].at[index, user_col_name] = site_username
                        log_result(full_name, email, "Fix Username", sheet_username, site_username, "Updated ✅")
                    else:
                        log_result(full_name, email, "Check Username", sheet_username, site_username, "Match (No Change)")
                except Exception as e:
                    log_result(full_name, email, "Username Check", "-", "-", f"Error: {str(e)[:10]}")

            # 3. CHANGE PASSWORD
            if do_password:
                try:
                    if "/annotation/training" not in driver.current_url: driver.get(SELECTORS["training_url"])
                    try:
                        wait.until(EC.presence_of_element_located((By.XPATH, SELECTORS["training_row"])))
                        row_elem = driver.find_element(By.XPATH, SELECTORS["training_row"])
                        status_elem = row_elem.find_element(By.XPATH, SELECTORS["training_status_badge"])
                        training_status = status_elem.text.strip()
                        if training_status.lower() != "passed":
                            log_result(full_name, email, "Check Training", "Standard Building", training_status, "Skipped (Not Passed) ⚠️")
                            driver.get(SELECTORS["logout_url"])
                            time.sleep(1.5)
                            continue 
                        log_result(full_name, email, "Check Training", "Standard Building", training_status, "Passed ✅")
                    except TimeoutException:
                        log_result(full_name, email, "Check Training", "Standard Building", "Not Found", "Timeout/Missing ⚠️")
                        driver.get(SELECTORS["logout_url"])
                        time.sleep(1.5)
                        continue
                except Exception as e:
                     log_result(full_name, email, "Nav Training", "-", "-", f"Nav Error: {str(e)[:20]}")
                     driver.get(SELECTORS["logout_url"])
                     continue

                if active_login_pass == new_password:
                     log_result(full_name, email, "Change Password", active_login_pass, new_password, "Skipped: Same as Current")
                else:
                    driver.get(SELECTORS["profile_url"])
                    wait.until(EC.element_to_be_clickable((By.XPATH, SELECTORS["edit_pass_icon"]))).click()
                    wait.until(EC.presence_of_element_located((By.ID, SELECTORS["input_current"])))
                    driver.find_element(By.ID, SELECTORS["input_current"]).send_keys(active_login_pass)
                    driver.find_element(By.ID, SELECTORS["input_new"]).send_keys(new_password)
                    driver.find_element(By.ID, SELECTORS["input_confirm"]).send_keys(new_password)
                    time.sleep(1)
                    try:
                        inline_err = driver.find_element(By.XPATH, SELECTORS["inline_error"])
                        if inline_err.is_displayed():
                            log_result(full_name, email, "Change Password", active_login_pass, new_password, f"Format Error: {inline_err.text[:10]}")
                            driver.find_element(By.XPATH, SELECTORS["modal_cancel"]).click()
                            driver.get(SELECTORS["logout_url"])
                            continue
                    except NoSuchElementException: pass 
                    driver.find_element(By.XPATH, SELECTORS["modal_submit"]).click()
                    try:
                        WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.XPATH, f"{SELECTORS['toast_success']} | {SELECTORS['toast_invalid_pass']}")))
                        page_source = driver.page_source
                        if "Password updated" in page_source:
                            sheet_obj.update_cell(sheet_row_num, pass_col_idx, new_password)
                            st.session_state['df'].at[index, pass_col_name] = new_password
                            log_result(full_name, email, "Change Password", active_login_pass, new_password, "Success ✅")
                        elif "Invalid password" in page_source:
                            log_result(full_name, email, "Change Password", active_login_pass, new_password, "Wrong Current Pass ❌")
                        else:
                            log_result(full_name, email, "Change Password", "-", "-", "Unknown Error ❌")
                    except TimeoutException:
                          log_result(full_name, email, "Change Password", "-", "-", "Validation Timeout ❌")

            driver.get(SELECTORS["logout_url"])
            time.sleep(1.5)

        except Exception as e:
            log_result(full_name, email, "CRITICAL ERROR", "-", "-", str(e)[:20])
            try: driver.delete_all_cookies()
            except: pass

    status_container.update(label="✨ Batch Completed!", state="complete", expanded=False)
    driver.quit()
    st.success("All tasks finished.")
    st.rerun()

# ==========================================
# 🖥️ STREAMLIT UI
# ==========================================
# 🆕 SIDEBAR FOR SETUP
with st.sidebar:
    st.title("⚙️ Setup")
    json_path = st.text_input("JSON Key Path", value="auto-sign-up-485610-b81d49b78d37.json", help="Path to your Google Service Account JSON file.")
    sheet_url = st.text_input("Google Sheet URL", value="https://docs.google.com/spreadsheets/d/11WRdoGWaWSivHVbxWKF66tpbbTGk5kM-3JrLKSu7bqs/edit?usp=sharing", help="URL of the Google Sheet containing user data.")
    
    if st.button("📂 Load Sheet Data", type="primary"):
        if json_path and sheet_url:
            sheet = connect_to_sheet(json_path, sheet_url)
            if sheet:
                raw_data = sheet.get_all_values()
                if len(raw_data) > 1:
                    headers = raw_data[0]
                    rows = raw_data[1:]
                    unique_headers = clean_headers(headers)
                    df = pd.DataFrame(rows, columns=unique_headers)
                    df['original_index'] = df.index 
                    st.session_state['df'] = df
                    st.session_state['logs'] = [] 
                    st.success("Loaded!")
                else:
                    st.warning("Sheet empty.")

st.title("🤖 Auto Admin Bot")

# MAIN UI
if 'df' in st.session_state:
    df = st.session_state['df']
    
    # Identify Columns
    pass_col_name = "bitmappro Password: (Default is 123456)" 
    email_col_name = "bitmappro Email login:"
    fullname_col_name = "Full Name(First and Last Name ONLY!):"
    timestamp_col_name = "Timestamp"
    status_col_name = "Status:" 
    user_col_idx, user_col_name = find_column_by_keyword(df.columns, "enter your SITE USERNAME")
    try: pass_col_idx = list(df.columns).index(pass_col_name) + 1 
    except: st.error("Password Column not found!")
    try: status_col_idx = list(df.columns).index(status_col_name) + 1
    except: status_col_idx = None

    # 🆕 METRICS DASHBOARD
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Users", len(df))
    
    # 🆕 AUTOMATION CONFIG (EXPANDER)
    with st.expander("🛠️ Automation Configuration", expanded=True):
        c1, c2 = st.columns(2)
        with c1: do_username = st.checkbox("Correct Username", value=True)
        with c2: do_password = st.checkbox("Change Password", value=True)
        
        new_admin_pass = None
        pass_valid_format = False
        pass_redundant = False
        redundant_users = []

        if do_password:
            st.info("ℹ️ **Requirement:** 6+ chars, 1 uppercase, 1 lowercase, 1 number.")
            new_admin_pass = st.text_input("Enter New Password:", type="password")
            if new_admin_pass:
                if validate_password_strength(new_admin_pass):
                    pass_valid_format = True
                    st.success("✅ Strong password.")
                else:
                    st.error("❌ Weak password.")

    # 🆕 FALLBACK PASSWORDS (EXPANDER)
    with st.expander("🔐 Manage Fallback Passwords", expanded=False):
        if 'fallback_passwords' not in st.session_state: st.session_state['fallback_passwords'] = load_fallback_passwords()
        
        c_add, c_btn = st.columns([3, 1])
        with c_add: new_fallback = st.text_input("Add Password", label_visibility="collapsed", placeholder="Enter password to try...")
        with c_btn:
            if st.button("➕ Add"):
                if new_fallback and new_fallback not in st.session_state['fallback_passwords']:
                    st.session_state['fallback_passwords'].append(new_fallback)
                    save_fallback_passwords(st.session_state['fallback_passwords'])
                    st.rerun()

        if st.session_state['fallback_passwords']:
            fallback_df = pd.DataFrame(st.session_state['fallback_passwords'], columns=["Passwords"])
            edited_fallback_df = st.data_editor(fallback_df, num_rows="dynamic", key="fallback_editor", use_container_width=True)
            current_list = edited_fallback_df["Passwords"].tolist()
            cleaned_list = [str(x) for x in current_list if str(x).strip() != ""]
            if cleaned_list != st.session_state['fallback_passwords']:
                 st.session_state['fallback_passwords'] = cleaned_list
                 save_fallback_passwords(cleaned_list)
                 st.rerun()

    st.divider()

    # --- FILTERS & TABLE ---
    col_l, col_r = st.columns([1, 3])
    
    with col_l:
        st.subheader("Filter Data")
        
        # Row Limits
        total_rows = len(df)
        start_sheet_row = st.number_input("Start Row:", min_value=2, max_value=total_rows+1, value=2)
        end_sheet_row = st.number_input("End Row:", min_value=start_sheet_row, max_value=total_rows+1, value=total_rows+1)
        
        # Prepare Data Slice
        start_idx = start_sheet_row - 2
        end_idx = end_sheet_row - 1
        filtered_df = df.iloc[start_idx:end_idx].copy()
        filtered_df.insert(0, "Sheet Row", filtered_df["original_index"] + 2)

        # Status Filter
        if status_col_name in df.columns:
            df[status_col_name] = df[status_col_name].astype(str)
            raw_status_values = df[status_col_name].unique().tolist()
            all_status_options = sorted(list(set(["Blank" if (x.strip() == "" or x.lower() == "nan") else x for x in raw_status_values])))
            selected_statuses = st.multiselect("Status:", all_status_options)
            
            if selected_statuses:
                has_blank = "Blank" in selected_statuses
                normal_selections = [x for x in selected_statuses if x != "Blank"]
                if has_blank:
                    filtered_df = filtered_df[filtered_df[status_col_name].isin(normal_selections) | (filtered_df[status_col_name].str.strip() == "") | (filtered_df[status_col_name].str.lower() == "nan")]
                else:
                    filtered_df = filtered_df[filtered_df[status_col_name].isin(normal_selections)]

        # Password Filter
        if pass_col_name in df.columns:
            all_pass_options = df[pass_col_name].unique().tolist()
            selected_passwords = st.multiselect("Password:", all_pass_options)
            if selected_passwords:
                filtered_df = filtered_df[filtered_df[pass_col_name].isin(selected_passwords)]

    with col_r:
        st.subheader("Select Users")
        select_all = st.checkbox("Select All in view", value=False)
        if "Select" not in filtered_df.columns: filtered_df.insert(0, "Select", select_all)
        else: filtered_df["Select"] = select_all

        # Display Config
        column_config = {
            "Select": st.column_config.CheckboxColumn("Select", width="small"),
            "Sheet Row": st.column_config.NumberColumn("Row", width="small"),
            status_col_name: st.column_config.TextColumn("Status"),
            timestamp_col_name: st.column_config.TextColumn("Timestamp"),
            fullname_col_name: st.column_config.TextColumn("Name"),
            email_col_name: st.column_config.TextColumn("Email"),
            pass_col_name: st.column_config.TextColumn("Password"),
        }
        if user_col_name: column_config[user_col_name] = st.column_config.TextColumn("Username")

        # Show Table
        desired_cols = ["Select", "Sheet Row", status_col_name, fullname_col_name, email_col_name, pass_col_name]
        if user_col_name: desired_cols.append(user_col_name)
        final_cols = [c for c in desired_cols if c in filtered_df.columns]
        
        edited_df = st.data_editor(
            filtered_df[final_cols],
            column_config=column_config,
            disabled=[c for c in final_cols if c != "Select"], 
            hide_index=True,
            use_container_width=True,
            height=400
        )
        
        selected_rows = edited_df[edited_df["Select"] == True]
        
        # Recover full data for selected rows
        selected_indices = selected_rows["Sheet Row"].values
        full_selected_rows = df[df.index.isin(filtered_df[filtered_df["Sheet Row"].isin(selected_indices)]["original_index"])].copy()
        
        col2.metric("Selected", len(full_selected_rows))
        
        # Redundancy Check
        if do_password and new_admin_pass and not full_selected_rows.empty:
            matches = full_selected_rows[full_selected_rows[pass_col_name] == new_admin_pass]
            if not matches.empty:
                pass_redundant = True
                st.error(f"⚠️ Redundancy: {len(matches)} users already have this password.")

    # --- ACTION BUTTON ---
    st.divider()
    btn_disabled = len(full_selected_rows) == 0 or (do_password and (not new_admin_pass or not pass_valid_format or pass_redundant))
    
    if st.button("▶️ Start Automation", type="primary", disabled=btn_disabled, use_container_width=True):
        run_bot(full_selected_rows, do_username, do_password, new_admin_pass, 
                st.session_state['fallback_passwords'], json_path, sheet_url, 
                user_col_idx, user_col_name, pass_col_idx, pass_col_name, fullname_col_name,
                status_col_idx, status_col_name)

# --- LOGS ---
if 'logs' in st.session_state and st.session_state['logs']:
    with st.expander("📜 View Detailed Logs", expanded=False):
        log_df = pd.DataFrame(st.session_state['logs'])
        st.dataframe(log_df, use_container_width=True, hide_index=True)