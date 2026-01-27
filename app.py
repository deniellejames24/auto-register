import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import time

# --- GOOGLE SHEETS SETUP ---
def connect_to_sheet(sheet_url, credentials_json):
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name(credentials_json, scope)
    client = gspread.authorize(creds)
    sheet = client.open_by_url(sheet_url).sheet1
    return sheet

# --- REGISTRATION LOGIC ---
def register_user(driver, user_data):
    wait = WebDriverWait(driver, 15)
    
    # 1. Open Site and Maximize (important for finding buttons)
    driver.get("https://ginger.bitmappro.com/login")
    driver.maximize_window()
    st.write(f"🌐 Loading site for: {user_data['email']}")

    # 2. Hard-target the Sign Up link
    try:
        # This looks for any link containing the word "Sign Up" or "Register"
        signup_btn = wait.until(EC.element_to_be_clickable((By.XPATH, "//a[contains(text(), 'Sign Up')] | //button[contains(text(), 'Sign Up')]")))
        driver.execute_script("arguments[0].click();", signup_btn) # Using JS click for reliability
        st.write("✅ Clicked Sign Up")
    except Exception as e:
        st.error("Could not find the 'Sign Up' button. Please check if the page is loaded correctly.")
        return "Fail: Nav"

    # 3. Fill Basic Info
    try:
        # Wait for the email field to ensure we are on the new page
        email_input = wait.until(EC.presence_of_element_located((By.XPATH, "//input[contains(@placeholder, 'Email')]")))
        email_input.send_keys(user_data['email'])
        
        driver.find_element(By.XPATH, "//input[contains(@placeholder, 'User Name')]").send_keys(user_data['username'])
        driver.find_element(By.XPATH, "//input[contains(@placeholder, 'New Password')]").send_keys("123456")
        driver.find_element(By.XPATH, "//input[contains(@placeholder, 'Confirm Password')]").send_keys("123456")
        driver.find_element(By.XPATH, "//input[contains(@placeholder, 'Referral Email')]").send_keys("iru.xfnite@gmail.com")
        driver.find_element(By.XPATH, "//input[contains(@placeholder, 'Invitation Code')]").send_keys("MJRS0F")
        
        st.write("📝 Basic Info filled.")
        
        # Click Next
        next_btn = driver.find_element(By.XPATH, "//button[contains(text(), 'Next')]")
        next_btn.click()
        time.sleep(2)
    except Exception as e:
        return f"Fail: Form Input ({str(e)[:30]})"

    # 4. Error Check
    source = driver.page_source
    if "(22026)" in source:
        return "DUP"
    if "(37049)" in source:
        st.write("🔄 Username exists, retrying with '2'...")
        user_in = driver.find_element(By.XPATH, "//input[contains(@placeholder, 'User Name')]")
        user_in.clear()
        user_in.send_keys(user_data['username'] + "2")
        driver.find_element(By.XPATH, "//button[contains(text(), 'Next')]").click()
        time.sleep(2)

    # 5. Details Skip (Space)
    try:
        fb = wait.until(EC.presence_of_element_located((By.XPATH, "//input[contains(@placeholder, 'Facebook')]")))
        fb.send_keys(" ")
        driver.find_element(By.XPATH, "//input[contains(@placeholder, 'Graduate School')]").send_keys(" ")
        driver.find_element(By.XPATH, "//input[contains(@placeholder, 'Graduate Year')]").send_keys(" ")
        
        driver.find_element(By.XPATH, "//button[contains(text(), 'Next')]").click()
        st.write("⏩ Details bypassed.")
    except:
        return "Fail: Details page"

    # 6. Group Select (Cancel)
    try:
        cancel_btn = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Cancel')]")))
        cancel_btn.click()
        st.write("🚫 Group Selection cancelled.")
        return "OK"
    except:
        # If the cancel button isn't there, it might have finished already
        return "OK (Completed)"

# --- STREAMLIT UI ---
st.set_page_config(page_title="Registration Automator", layout="wide")
st.title("🤖 BitmapPro Auto-Reg")

with st.sidebar:
    st.header("1. Credentials")
    sheet_url = st.text_input("Google Sheet URL")
    creds_file = st.file_uploader("Upload JSON Key", type="json")
    st.header("2. Settings")
    headless = st.checkbox("Run in background (Headless)", value=False)

if st.button("🚀 Start Registration Process"):
    if not sheet_url or not creds_file:
        st.error("Missing configuration!")
    else:
        with open("temp_creds.json", "wb") as f:
            f.write(creds_file.getbuffer())
        
        try:
            sheet = connect_to_sheet(sheet_url, "temp_creds.json")
            all_values = sheet.get_all_values()
            headers = all_values[0]
            data = [dict(zip(headers, row)) for row in all_values[1:] if any(row)]
            
            st.success(f"Connected! Processing {len(data)} users...")
            progress_bar = st.progress(0)
            
            options = Options()
            if headless: options.add_argument("--headless")
            driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

            for i, row in enumerate(data):
                user_info = {'email': row.get('Code: Email'), 'username': row.get('Username')}
                
                # Update Status column (Assumed Column 8)
                try:
                    status = register_user(driver, user_info)
                    sheet.update_cell(i + 2, 8, status)
                    st.write(f"✅ Row {i+2}: {user_info['email']} -> {status}")
                except Exception as e:
                    st.error(f"❌ Row {i+2}: Error - {str(e)}")
                
                progress_bar.progress((i + 1) / len(data))
            
            driver.quit()
            st.balloons()
            
        except Exception as e:
            st.error(f"Fatal Error: {e}")