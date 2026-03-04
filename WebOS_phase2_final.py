import pytest
import allure
from appium import webdriver
from appium.options.common import AppiumOptions
from appium.webdriver.common.appiumby import AppiumBy
from selenium.common.exceptions import NoSuchElementException, TimeoutException, StaleElementReferenceException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
import time
import requests
import random
import json

# --- Configuration (Constants) ---
APPIUM_SERVER_URL = "http://127.0.0.1:4723"
DEVICE_NAME = "LG_2019"
DEVICE_HOST = "172.23.4.18" # Ensure this matches your TV's current IP
APP_ID = "hotstar"
#CHROMEDRIVER_PATH = "/Users/dev.mm.con/chromedriver-2.36"

# Static Test Data
User_Cookie = None
User_Token = None
HOME_LOCATOR = (AppiumBy.XPATH, '//*[@realfocuskey="nav-menu-item-My Space"]')

def load_config():
    # --- 2. Tell Python we are modifying the global variables ---
    global User_Cookie, User_Token 
    
    # --- 3. Read the file ---
    try:
        with open('/Users/tushar.arote.con/Downloads/WEBOS_Automation/Usercredential.json', 'r') as file:
            data = json.load(file)
            
            # --- 4. Assign JSON data to variables ---
            User_Token = data.get("xsrf-token")
            User_Cookie = data.get("Cookie")
    except Exception as e:
        print(f"Failed to load config: {e}")

# --- 5. Call the method immediately ---
load_config()

# --- API Integration Functions ---

def get_test_credentials(user_type="Phone_Fresh_User"):
    """Fetches dynamic phone number and OTP from Retool API."""
    print(f"Usertoken: {User_Token}")
    print(f"User cookies: {User_Cookie}")
    url = "https://origin-hs-core-retool.sgp.hotstar-prod.com/api/pages/uuids/ff45704a-83e4-11f0-8f33-23378b6e2097/query?queryName=user_query"
    headers = {
        'accept': '*/*',
        'content-type': 'application/json',
        'x-xsrf-token': User_Token,
        'Cookie': User_Cookie
    }
    payload = {
        "userParams": {
            "queryParams": {"0": "https://origin-testdataportal.eu.hotstar-prod.com", "length": 1},
            "graphQLVariablesParams": {"0": user_type, "1": "in", "2": "prod", "length": 7}
        }
    }
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=15)
        response.raise_for_status()
        data = response.json()
        
        user_list = data.get('data', {}).get('user', [])
        if user_list:
            user_obj = user_list[0]
            phone = user_obj.get('phone')
            otp = user_obj.get('otp')
            hid = user_obj.get('hid')
            return str(phone), str(otp), str(hid)
        else:
            return None, None
    except Exception as e:
        print(f"❌ API Request Failed: {e}")
        return None, None

@allure.step("Resetting Watch Time for HID: {hid}")
def reset_user_watch_time(hid, watch_time_ms):
    """
    Calls the watch-time-processor debug API to set specific watch time.
    """
    url = f"https://origin-hs-watch-time-processor.sgp.hotstar-prod.com/debug?hid={hid}"
    headers = {
        'Content-Type': 'application/json'
    }
    payload = {
        "watchTimeMs": watch_time_ms
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        response.raise_for_status()
        print(f"Successfully updated watch time for {hid} to {watch_time_ms}ms")
        return response.json()
    except Exception as e:
        print(f"⚠️ Failed to reset watch time: {e}")
        return None

# --- Pytest Fixtures ---

@pytest.fixture(scope="function")
@allure.title("Initialize Appium Driver for webOS")
def driver_setup(request):
    """Initializes and yields Appium driver with extended timeouts."""
    print(f"\nSetting up driver for test: {request.node.name}...")
    appium_options = AppiumOptions()
    appium_options.platform_name = "LGTV"
    appium_options.automation_name = "webOS"
    appium_options.set_capability("appium:deviceName", DEVICE_NAME)
    appium_options.set_capability("appium:deviceHost", DEVICE_HOST)
    appium_options.set_capability("appium:appId", APP_ID)
    appium_options.set_capability("appium:noReset", True)
    appium_options.set_capability("appium:rcMode", "rc")
#    appium_options.set_capability("appium:chromedriverExecutable", CHROMEDRIVER_PATH)
    appium_options.set_capability("appium:newCommandTimeout", 300) # Prevents Session Death during sleeps

    driver = None
    try:
        # Initialize the driver
        driver = webdriver.Remote(APPIUM_SERVER_URL, options=appium_options)
        driver.implicitly_wait(5)

        # Initialize waiters
        ignored_exceptions = [StaleElementReferenceException]
        wait_50s = WebDriverWait(driver,50, ignored_exceptions=ignored_exceptions)
        video_90s = WebDriverWait(driver, 90, ignored_exceptions=ignored_exceptions)

        print("App launched successfully.")

        # Yield the driver and waiters to the test function
        yield driver, wait_50s, video_90s

    except Exception as e:
        print(f"Error during driver initialization: {e}")
        pytest.fail(f"Driver setup failed with error: {e}")

    finally:
        # Teardown logic runs after the test finishes
        # Logout is called here to ensure clean state if noReset=True
        if driver:
            try:
                _logout(driver, wait_50s, _navigate_back_to_home)
            except Exception as e:
                
                print(f"Warning: Logout failed during tearDown. App state might be unstable: {e}")
            print(f"\nRunning teardown for test: {request.node.name}...")
            driver.quit()
            print("App closed.")
        time.sleep(10)



# --- Reusable Utility Helpers ---

@allure.step("Perform Login with Phone Number {phone_number}")
def _login(driver, wait, phone_number, otp):
    print("Login Initiated")
    time.sleep(3)

    # 1. Handle 'Continue' or 'Log In' prompt
    try:
        continue_btn = driver.find_element(AppiumBy.XPATH, '//*[text()="Continue"]')
        continue_btn.click()
    except NoSuchElementException:
        print("Continue button not found, proceeding...")

    # 2. Enter Phone Number
    with allure.step("Entering phone number digits"):
        for digit in phone_number:
            driver.find_element(AppiumBy.XPATH, f'//span[text()="{digit}"]').click()

    # 3. Click Get OTP
    get_otp_btn = wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, '//span[text()="Get OTP"]')))
    get_otp_btn.click()
    time.sleep(3)

    # 4. Enter OTP
    with allure.step("Entering OTP digits"):
        for digit in otp:
            driver.find_element(AppiumBy.XPATH, f'//span[text()="{digit}"]').click()
    
@allure.step("switching to kids profile")
def _switching_to_kids(driver, wait):
    wait.until(EC.element_to_be_clickable(HOME_LOCATOR)).click()
    time.sleep(5)
    profiles = driver.find_elements(AppiumBy.XPATH, "//*[@class='_29_lsSDSbC8ghg3WojTDfZ _1nSi2JQsirqcJgMi2iWYyd']")
    step_count = len(profiles)
    for x in range(1, step_count):
        driver.execute_script("webos: pressKey", {"key": "RIGHT"})
        time.sleep(1)
        
    driver.execute_script("webos: pressKey", {"key": "ENTER"})    #switching to kids
    time.sleep(3)

@allure.step("Switching to main profile from kids profile")
def _Switching_back_to_main_profile(driver,wait):
    wait.until(EC.element_to_be_clickable(HOME_LOCATOR)).click() #Navigate to Myspace 
    time.sleep(3)
    profiles = driver.find_elements(AppiumBy.XPATH, "//*[@class='_29_lsSDSbC8ghg3WojTDfZ _1nSi2JQsirqcJgMi2iWYyd']")
    assert len(profiles) > 0, "No elements found to hover over!"
    for Y in range(1, len(profiles)):
                driver.execute_script("webos: pressKey", {"key": "left"})
                time.sleep(1)
                # 4. Press ENTER and wait
    driver.execute_script("webos: pressKey", {"key": "enter"})
    time.sleep(1)
    try : 
                 # 2. Enter PIN
                pin_string = "1234"
                for digit in pin_string:
                    driver.find_element(AppiumBy.XPATH, f'//span[text()="{digit}"]').click()
                    time.sleep(2)
    except Exception as e:
                print(f"Error occurred while entering PIN: {e}")
                # Append logout code
    wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, "//*[@focuskey='nav-menu-item-Movies']"))).click()

@allure.step("Select Profile and Enter PIN")
def _profile_onboarding(driver, wait):
    print("Profile selection started")

    # 1. Select the main profile
    profile_img = wait.until(
        EC.element_to_be_clickable((AppiumBy.XPATH, '//*[@data-testid="hs-image"]')) 
    )
    profile_img.click()

    # 2. Enter PIN
    try:
        # We search for the element; if it's not there within 5 seconds, we skip the PIN block
        pin_button_1 = wait.until(
            EC.visibility_of_element_located((AppiumBy.XPATH, '//span[text()="1"]'))
        )
        
        # If the element is found, pin_button_1 will not be None
        if pin_button_1:
            pin_string = "1234"
            print(f"PIN entry visible. Entering PIN: {pin_string}")
            with allure.step("Entering profile PIN"):
                for digit in pin_string:
                    # It's safer to use wait here too in case the numpad is slow to react
                    driver.find_element(AppiumBy.XPATH, f'//span[text()="{digit}"]').click()
    
    except Exception:
        # If the element "//span[text()='1']" is not found, it throws a TimeoutException
        print("Parental lock is not available for this user. Proceeding...")

@allure.step("Navigate back to Home Screen gracefully")
def _navigate_back_to_home(driver, max_attempts=5, timeout_per_attempt=5):
    """
    Repeatedly calls driver.back() until the target home element is found.
    """
    print(f"Attempting to navigate back to Home Screen (max {max_attempts} attempts)...")

    for attempt in range(1, max_attempts + 1):
        try:
            # 1. Wait briefly for the element to appear
            home_check = WebDriverWait(driver, timeout_per_attempt).until(
                EC.presence_of_element_located(HOME_LOCATOR)
            )
            print(f"Successfully reached Home Screen on attempt {attempt}.")
            return home_check  # Success!

        except TimeoutException:
            print(f"Attempt {attempt}/{max_attempts}: Home element not found. Calling driver.back().")
            # 2. If not found, hit the back button
            driver.back()
            time.sleep(1)

            # If the loop finishes without finding the element
    raise TimeoutException("Failed to navigate back to the Home Screen after maximum attempts.")


@allure.step("Perform Logout")
def _logout(driver, wait, navigate_back_func):
    print("Logout initiated")
    try:
        # Ensure we are on the home screen before attempting to navigate the menu
        navigate_back_func(driver)

        wait.until(
            EC.element_to_be_clickable(HOME_LOCATOR)
        ).click()
        wait.until(
            EC.element_to_be_clickable((AppiumBy.XPATH, '//span[text()="Help & Settings"]'))
        ).click()
        wait.until(
            EC.element_to_be_clickable((AppiumBy.XPATH, '//span[text()="Log Out"]'))
        ).click()
        wait.until(
            EC.element_to_be_clickable((AppiumBy.XPATH, '//*[@data-testid="dialog-lr-primary-button"]'))
        ).click()

        # Assert login screen visible
        login_check = wait.until(
            EC.element_to_be_clickable((AppiumBy.XPATH, '//span[text()="1"]'))
        )
        assert login_check is not None, "Logout failed, login screen not displayed"
        print("Logout successful and verified.")

    except Exception as e:
        # Log the error but allow teardown to continue if possible
        print(f"⚠️ Error during logout: {e}")
        # Re-raise the exception only if in a test body, not in teardown cleanup
        if 'test_' in pytest.current_test:
            raise e


@allure.step("Search for term: {search_term}")
def _search(driver, search_term):
    
    for char in search_term:
        key_to_press = "Space" if char == ' ' else char.upper()
        xpath_expression = f'//button[.//span[text()="{key_to_press}"]]'
        try:
            driver.find_element(AppiumBy.XPATH, xpath_expression).click()
        except Exception as e:
            print(f"Error clicking key '{key_to_press}': {e}")
            raise

@allure.step("Validate that the PSP page is displayed")
def validate_psp_page_visible(wait, timeout_msg="PSP page not found"):
    """
    Common function to verify the user has reached the Subscription/PSP screen.
    """
    try:
        psp_premium = wait.until(
            EC.element_to_be_clickable((AppiumBy.XPATH, '//*[text()="Premium"]'))
        )
        assert psp_premium is not None, timeout_msg
        print("Verification Successful: PSP page is available.")
        return True
    except TimeoutException:
        print(f"Verification Failed: {timeout_msg}")
        pytest.fail(timeout_msg)

@allure.step("Create profile for fresh user")
def _create_profile(driver,wait):
    profile_input = wait.until(
        EC.visibility_of_element_located((AppiumBy.XPATH, '//*[contains(text(),"Your Name")]')) 
    )
    profile_input.click() 
    # //*[@data-testid="phone-number-input"]

    _search(driver, "TEST")
    wait.until(
            EC.element_to_be_clickable((AppiumBy.XPATH, '//button[.//span[text()="Create Your Profile"]]'))
        ).click()
    time.sleep(2)
    lang_kannada = wait.until(
            EC.element_to_be_clickable((AppiumBy.XPATH, '//div[./div[text()="Kannada"]]/ancestor::div[@data-testid="action"]'))
        )
    lang_kannada.click()

    wait.until(
            EC.element_to_be_clickable((AppiumBy.XPATH, '//*[@title="Continue"]'))
        ).click()


# --- Test Cases ---

@allure.story("[Fresh User] Verify a Fresh User is able to Login and browse the app, verify Click on Subscribe CTA in Home Page & myspace ")
@allure.title("RL-T1487")
@pytest.mark.testcase4
def test_case_RLT1487(driver_setup):
    driver, wait, _ = driver_setup
    fresh_phone, fresh_otp, fresh_hid = get_test_credentials("Phone_Fresh_User")

    if not fresh_phone:
        pytest.fail("Failed to fetch Phone_Fresh credentials from API")

    # 2. Login using API credentials
    _login(driver, wait, fresh_phone, fresh_otp)

#    wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, '//button[.//span[text()="Create Your Profile"]]')))
    _create_profile(driver,wait)
    time.sleep(2)


    with allure.step("Validate Side Nav is displayed"):
        myspace_btn = wait.until(
        EC.element_to_be_clickable((AppiumBy.XPATH, '//*[@realfocuskey="nav-menu-item-My Space"]'))
        )
        assert myspace_btn is not None, "Myspace side-nav is not available"
        print("My space side-nav is available")

        home_btn = wait.until(
        EC.element_to_be_clickable((AppiumBy.XPATH, '//*[@realfocuskey="nav-menu-item-Home"]'))
        )
        assert home_btn is not None, "Home side-nav is not available"
        print("Home side-nav is available")

        search_btn = wait.until(
        EC.element_to_be_clickable((AppiumBy.XPATH, '//*[@realfocuskey="nav-menu-item-Search"]'))
        )
        assert search_btn is not None, "Search side-nav is not available"
        print("Search side-nav is available")

        tv_btn = wait.until(
        EC.element_to_be_clickable((AppiumBy.XPATH, '//*[@realfocuskey="nav-menu-item-TV"]'))
        )
        assert tv_btn is not None, "TV side-nav is not available"
        print("TV side-nav is available")

        movies_btn = wait.until(
        EC.element_to_be_clickable((AppiumBy.XPATH, '//*[@realfocuskey="nav-menu-item-Movies"]'))
        )
        assert movies_btn is not None, "Movies side-nav is not available"
        print("Movies side-nav is available")

        Sports_btn = wait.until(
        EC.element_to_be_clickable((AppiumBy.XPATH, '//*[@realfocuskey="nav-menu-item-Sports"]'))
        )
        assert Sports_btn is not None, "Sports side-nav is not available"
        print("Sports side-nav is available")

        Sparks_btn = wait.until(
        EC.element_to_be_clickable((AppiumBy.XPATH, '//*[@realfocuskey="nav-menu-item-Sparks"]'))
        )
        assert Sparks_btn is not None, "Sparks side-nav is not available"
        print("Sparks side-nav is available")

        Categories_btn = wait.until(
        EC.element_to_be_clickable((AppiumBy.XPATH, '//*[@realfocuskey="nav-menu-item-Categories"]'))
        )
        assert Categories_btn is not None, "Categories side-nav is not available"
        print("Categories side-nav is available")

    with allure.step("Tap on subscribe in my space"):
        myspace_btn = wait.until(
        EC.element_to_be_clickable((AppiumBy.XPATH, '//*[@realfocuskey="nav-menu-item-My Space"]'))
        )
        myspace_btn.click()

        wait.until(
            EC.element_to_be_clickable((AppiumBy.XPATH, '//*[@title="Subscribe"]'))
        ).click()

        validate_psp_page_visible(wait)

        driver.back()  

    with allure.step("Try to play any content"):
        wait.until(
            EC.element_to_be_clickable(HOME_LOCATOR)
        ).click()
        wait.until(
            EC.element_to_be_clickable((AppiumBy.XPATH,'//*[@realfocuskey="nav-menu-item-Search"]'))
        ).click()

        time.sleep(2)
        _search(driver,"King and Conqueror")
        wait.until(
            EC.element_to_be_clickable((AppiumBy.XPATH, '//*[text()="King & Conqueror"]'))
        ).click()

        wait.until(
            EC.element_to_be_clickable((AppiumBy.XPATH, '//*[text()="Subscribe to Watch"]'))
        ).click()

        validate_psp_page_visible(wait)

        driver.back()
        _navigate_back_to_home(driver)

@allure.story("[Free User]As a Free user, I go to Sports Sub menu and I see PSP upon playing non-free live content, I am allowed to play free live contents for 4hrs and i see PSP page after completing 4hrs of free timer")
@allure.title("RL-T356")
@pytest.mark.testcase1
def test_case_RLT356(driver_setup):
    
    driver, wait, video_wait = driver_setup
    free_phone, otp, hid = get_test_credentials("Free_Timer_Eligible_users_two")
    if not free_phone:
        pytest.fail("Failed to fetch Phone_Fresh credentials from API")
    reset_user_watch_time(hid,watch_time_ms=7134000)
    
    _login(driver, wait, free_phone, otp)
    _profile_onboarding(driver, wait)

    wait.until(
            EC.element_to_be_clickable((AppiumBy.XPATH,'//*[@realfocuskey="nav-menu-item-Movies"]'))
        ).click()
    
    time.sleep(2)
    
    # wait.until(
    #         EC.element_to_be_clickable((AppiumBy.XPATH,'//*[@data-testid="slider-slide-0 slide-selected" or @data-testid="slider-slide-0"]'))
    #     ).click()
    
    wait.until(
            EC.element_to_be_clickable((AppiumBy.XPATH,'//*[@data-testid="slider-slide-1 slide-selected" or @data-testid="slider-slide-1"]'))
        ).click()
    
    with allure.step("Start Playback"):
        watch_btn = wait.until(EC.element_to_be_clickable((AppiumBy.XPATH,'//*[text()="Watch from Beginning" or text()="Watch Now" or text()="Watch Latest Season"or text()="Watch First Episode"]')))
        watch_btn.click()
        assert watch_btn is not None, "Watch button not available"
        print("Playback started")
        time.sleep(5)
    timer_locator = (AppiumBy.XPATH, "//span[contains(@class, 'BUTTON2_MEDIUM') and contains(text(), ':')]")

    timer = wait.until(
    EC.element_to_be_clickable(timer_locator)
        )
    assert timer is not None, "Timer is not available"
    print("Timer is available")
    
    # 1. Capture initial time
    time_1 = wait.until(EC.visibility_of_element_located(timer_locator)).text
    print(f"Initial time: {time_1}")
    
    # 2. Wait for playback to progress
    time.sleep(5)
    
    # 3. Capture second time
    time_2 = driver.find_element(*timer_locator).text
    print(f"Time after 5s: {time_2}")
    
    # 4. Compare (Time 2 should be different/greater than Time 1)
    assert time_1 != time_2, f"Timer is stuck at {time_1}. Video might not be playing."
    print("Validation Successful: Timer is running.")
    time.sleep(50)

    sub_now = video_wait.until(
        EC.element_to_be_clickable((AppiumBy.XPATH, '//*[text()="Subscribe Now"]'))
        )
    assert sub_now is not None, "Subscribe now CTA is not available"
    print("Subscribe now CTA is available")
    time.sleep(2)

    validate_psp_page_visible(wait)
    
    _navigate_back_to_home(driver)

    time.sleep(2)

    wait.until(
            EC.element_to_be_clickable((AppiumBy.XPATH,'//*[@realfocuskey="nav-menu-item-Home"]'))
        ).click()

    time.sleep(2)

    hp_banner = wait.until(
        EC.visibility_of_element_located((AppiumBy.XPATH, '//*[text()="Your free access is over"]'))
        )
    assert hp_banner is not None, "Honeypot banner is not displayed"
    print("Honeypot banner is displayed")
    time.sleep(1)
    # driver.execute_script("webos: pressKey", {"key": "down"})

    # driver.execute_script("webos: pressKey", {"key": "enter"})

    # # driver.find_element(AppiumBy.XPATH,'//button[.//*[text()="Subscribe"]]').click()

    # validate_psp_page_visible(wait)

    # driver.back()

@allure.story("[Premium User]As a Premium user, I am playing a series from TV Submenu and seeing Binge Controls, Watch Next/MLT trays and able to play Series more than 10mins without any interruption")
@allure.title("RL-T375")
@pytest.mark.testcase3
def test_case_T375_4K_Seasons(driver_setup):
    """Validates 4K logos and season navigation."""
    driver, wait, video_wait = driver_setup
    # phone, otp = get_test_credentials("Phone_Premium")
    # if not phone:
    #     pytest.fail("Failed to fetch Phone_Premium credentials from API"
    premium_phone, otp, hid = get_test_credentials("Phone_Premium")
    if not premium_phone:
        pytest.fail("Failed to fetch Phone_Fresh credentials from API")

    _login(driver, wait, premium_phone, otp)
    _profile_onboarding(driver, wait)
    wait.until(EC.visibility_of_element_located((AppiumBy.XPATH,"//*[contains(@realfocuskey, 'nav-menu-item')]")))
    subnav_comp = driver.find_elements(AppiumBy.XPATH, "//*[contains(@realfocuskey, 'nav-menu-item')]")
    actual_count = len(subnav_comp)
    expected_count = 8
    assert actual_count == expected_count, f"Expected {expected_count} elements, but found {actual_count}"
    driver.find_element(AppiumBy.XPATH, "//*[@focuskey='nav-menu-item-TV']").click()
    time.sleep(3)
    for i in range(7):
                seasons = driver.find_elements(AppiumBy.XPATH, "//*[contains(text(),'Season')]")
                is_it_4K = driver.find_elements(AppiumBy.XPATH,"//*[@alt='4K']")
                if len(seasons) > 0 and len(is_it_4K) > 0:
                    driver.execute_script("webos: pressKey", {"key": "enter"})
                    break
                else:
                    driver.execute_script("webos: pressKey", {"key": "right"})
                    time.sleep(2)  # Wait for UI transition
    time.sleep(3)
    watch_xpath = '//*[text()="Watch from Beginning" or text()="Watch Now" or text()="Watch Latest Season"or text()="Watch First Episode"]'
    driver.find_element(AppiumBy.XPATH, watch_xpath).click()
    time.sleep(3)
    try:
                SPINNER_XPATH = '//*[@data-testid="loader"]'
                video_wait.until(EC.invisibility_of_element_located((AppiumBy.XPATH, SPINNER_XPATH)))
                video_player = wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//div[@data-testid="skin-container"]')))
                time.sleep(3)
    except Exception as e:
        print(f"Video Play failed & T375 failed: {e}")
    try:
                driver.execute_script("webos: pressKey", {"key": "UP"})
                skip_recap = driver.find_element(AppiumBy.XPATH, "//*[@title='Skip Recap']")
                assert skip_recap.is_displayed(), "Skip Recap button was not visible on screen"
                skip_recap.click()
    except Exception as e:
        print(f"Recap is not available {e}")
                
    try:
                driver.execute_script("webos: pressKey", {"key": "UP"})
                quality_btn = wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, "//*[@title='Quality']")))
                quality_btn.click()
                asli_4k_option = wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, "//span[text()='Asli 4K']")))
                asli_4k_option.click()
                time.sleep(5)
                asli_4k_logo = driver.find_element(AppiumBy.XPATH, "//*[@class='ASLI_4K_LOGO_WRAPPER']")
                assert asli_4k_logo.is_displayed(), "Asli 4K logo is not displayed after selection"
                driver.execute_script("webos: pressKey", {"key": "UP"})
                quality_btn = wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, "//*[@title='Quality']")))
                quality_btn.click()
                fhd_option = wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, "//span[text()='Full HD']")))
                fhd_option.click()
                time.sleep(5)
                logos = driver.find_elements(AppiumBy.XPATH, "//*[@class='ASLI_4K_LOGO_WRAPPER']")
                assert len(logos) == 0
    except Exception as e:
                print(f"T375 Quality change failed, seems a Non 4K device: {e}")

            # 1. Get the current episode name
    driver.execute_script("webos: pressKey", {"key": "up"})
    ep_name_xpath = "//*[@class='pgYQn-YxdROBlrWtyE7dG']/p[2]"
    current_episode_name = driver.find_element(AppiumBy.XPATH, ep_name_xpath).text
            # 2. Click on 'Next Episode'
    try:
                next_btn_xpath = "//*[text()='Next Episode']"
                wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, next_btn_xpath))).click()
        
                # 3. Wait for the UI to update
                time.sleep(15)
        
                # 4. Get the new episode name and Assert they are different
                driver.execute_script("webos: pressKey", {"key": "down"})
                wait.until(EC.presence_of_element_located((AppiumBy.XPATH, ep_name_xpath)))
                next_episode_name = driver.find_element(AppiumBy.XPATH, ep_name_xpath).text
                assert current_episode_name != next_episode_name, f"Episode name did not change! Still: {current_episode_name}"
    except Exception as e:
                print("Seems its last episode.")
            # 5. Assert Episodes Tray visibility
    episodes_tray = driver.find_element(AppiumBy.XPATH, "//*[text()='Episodes']")
    assert episodes_tray.is_displayed(), "Episodes tray is not visible after navigation"
    driver.back() #Back from watchPage
    time.sleep(3)
    driver.back() #Back from details page
    _switching_to_kids(driver, wait)
            # Switched to Kids Profile (its total profile -1)
    search_btn = wait.until(
    EC.element_to_be_clickable((AppiumBy.XPATH, '//*[@realfocuskey="nav-menu-item-Search"]')))
    search_btn.click()
    search_term = "How To Train Your Dragon"
    for char in search_term:
                key_to_press = "Space" if char == ' ' else char.upper()
                xpath_expression = f'//button[.//span[text()="{key_to_press}"]]'
                driver.find_element(AppiumBy.XPATH, xpath_expression).click()
                time.sleep(1)
    time.sleep(3)
    search_result = wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, '//p[contains(text(), "How To Train Your Dragon")]')))
    search_result.click()
    assert search_result is not None, "Search result not found"
    wait.until(EC.element_to_be_clickable((AppiumBy.XPATH,"//*[@title='Watch from Beginning' or @title='Watch Now']"))).click()
    time.sleep(10)
    driver.execute_script("webos: pressKey", {"key": "UP"})
    time.sleep(2)
    wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, '//span[text()="Quality"]'))).click()
    time.sleep(3)
    asli_4k_option = wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, "//span[text()='Asli 4K']")))
    asli_4k_option.click()
    
    time.sleep(5)
    asli_4k_logo = driver.find_element(AppiumBy.XPATH, "//*[@class='ASLI_4K_LOGO_WRAPPER']")
    assert asli_4k_logo.is_displayed(), "Asli 4K logo is not displayed after selection"

    driver.back() #Back to details page
    time.sleep(2)
    driver.back() #Back to Search page
    _Switching_back_to_main_profile(driver,wait)

@allure.story("[Free User] As a Free user, I see trailer auto-play based on LPV, check static paywall on KIDS profile after no free timer and check phonepe QR and scan scan the QR, Check amount is loaded correctly")
@allure.title("RL-T357")
@pytest.mark.testcase2
def test_case_T357_Kids_Restrictions(driver_setup):
    """Validates restrictions and trailers in Kids profile."""
    driver, wait, _ = driver_setup
    phone_free, otp,hid = get_test_credentials("Free_Timer_Eligible_users_two")
    if not phone_free:
        pytest.fail("Failed to fetch Phone_Fresh credentials from API")

    reset_user_watch_time(hid,watch_time_ms=74440000)

    _login(driver, wait, phone_free, otp)
    _profile_onboarding(driver, wait)
    
    driver.find_element(AppiumBy.XPATH, "//*[@focuskey='nav-menu-item-Movies']").click()
    time.sleep(7)
    
    # 2. Scroll down and search for Languages
    driver.execute_script("webos: pressKey", {"key": "DOWN"})
    time.sleep(2)
    
    for i in range(8):
    # 1. Initialize count with a default value at the start of each loop iteration 
        count = 0
        languages = driver.find_elements(AppiumBy.XPATH, "//*[contains(text(),'Languages')]")
        if len(languages) > 0:
            language_text = languages[0].text
            digit_as_str = language_text.split()[0]
            count = int(digit_as_str)

    # 2. Now count is guaranteed to exist (it will be 0 or the actual count)
        if count >= 4:  
            driver.execute_script("webos: pressKey", {"key": "ENTER"})
            break
        else:
            # Optional: Navigation logic to find the element if it's not there yet
            driver.execute_script("webos: pressKey", {"key": "RIGHT"})
            time.sleep(2)
            
    time.sleep(7)  # outside loop
    try:
        # 3. Verify Trailer Autoplay
        trailer_Element = "//div[@id='autoplay-container']//div//video"
        wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, trailer_Element)))
        random_index = random.randint(1, 4)
        # 4. Click specific element and wait for long playback (4s)
        language_switch = f"//*[contains(@class,'iqrCZFeGbJeBdWaI4fMAS')][{random_index}]"
        wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, language_switch))).click()
        time.sleep(3)
        error_Msg = driver.find_elements(AppiumBy.XPATH,"//*[contains(text(),'Trailer is unavailable')]")
        if len(error_Msg)>0:
            assert error_Msg[0].is_displayed()
        else:
        # 5. Verify Autoplay is still happening
            wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, trailer_Element)))
    except Exception as e:
        print(f"trailer not available: {e}")
    # 9. Go back
    time.sleep(3)
    driver.back()
    #start
    _switching_to_kids(driver, wait)
    #end
    search_btn = wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, '//*[@realfocuskey="nav-menu-item-Search"]')))
    search_btn.click()
    search_term = "How To Train Your Dragon"
    _search(driver,search_term)
    time.sleep(3)
    search_result = wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, f'//p[contains(text(), "{search_term}")]')))
    search_result.click()
    wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, "//*[@title='Subscribe to Watch']"))).click()
    plan_id = "HotstarPremium.IN.3Month.699"
    wait.until(EC.element_to_be_clickable((AppiumBy.ID, plan_id))).click()
    plan_Name = driver.find_element(AppiumBy.XPATH, "//*[@class=' ON_IMAGE H6 ']")
    payment_Method = driver.find_element(AppiumBy.XPATH, "//*[contains(text(),'Scan via')]")
    assert plan_Name.is_displayed(), "Plan title not displayed"
    assert payment_Method.is_displayed(), "UPI payment method is not available"
    time.sleep(2) 
    driver.back()   #to PSP
    time.sleep(2)  
    driver.back() # to details Page
    time.sleep(2)
    driver.back() #to Home Page
    _Switching_back_to_main_profile(driver,wait)

@allure.story("[Premium User] Verify a Premium User is able to login, search a content & playbck. User is able to logout of the app")
@allure.title("RL-T1488")
@pytest.mark.testcase5
def test_case_T1488_watch_movie(driver_setup):
    driver, wait, video_wait = driver_setup

    phone_premium, otp,hid = get_test_credentials("Phone_Premium")
    if not phone_premium:
        pytest.fail("Failed to fetch Phone_Fresh credentials from API")
    # phone, otp = get_test_credentials("Phone_Premium")
    # if not phone:
    #     pytest.fail("Failed to fetch Phone_Premium credentials from API")
    
    _login(driver, wait, phone_premium, otp)
    _profile_onboarding(driver, wait)

    with allure.step("Validate Side Nav is displayed"):
        myspace_btn = wait.until(
        EC.element_to_be_clickable((AppiumBy.XPATH, '//*[@realfocuskey="nav-menu-item-My Space"]'))
        )
        assert myspace_btn is not None, "Myspace side-nav is not available"
        print("My space side-nav is available")

        home_btn = wait.until(
        EC.element_to_be_clickable((AppiumBy.XPATH, '//*[@realfocuskey="nav-menu-item-Home"]'))
        )
        assert home_btn is not None, "Home side-nav is not available"
        print("Home side-nav is available")

        search_btn = wait.until(
        EC.element_to_be_clickable((AppiumBy.XPATH, '//*[@realfocuskey="nav-menu-item-Search"]'))
        )
        assert search_btn is not None, "Search side-nav is not available"
        print("Search side-nav is available")

        tv_btn = wait.until(
        EC.element_to_be_clickable((AppiumBy.XPATH, '//*[@realfocuskey="nav-menu-item-TV"]'))
        )
        assert tv_btn is not None, "TV side-nav is not available"
        print("TV side-nav is available")

        movies_btn = wait.until(
        EC.element_to_be_clickable((AppiumBy.XPATH, '//*[@realfocuskey="nav-menu-item-Movies"]'))
        )
        assert movies_btn is not None, "Movies side-nav is not available"
        print("Movies side-nav is available")

        Sports_btn = wait.until(
        EC.element_to_be_clickable((AppiumBy.XPATH, '//*[@realfocuskey="nav-menu-item-Sports"]'))
        )
        assert Sports_btn is not None, "Sports side-nav is not available"
        print("Sports side-nav is available")

        Sparks_btn = wait.until(
        EC.element_to_be_clickable((AppiumBy.XPATH, '//*[@realfocuskey="nav-menu-item-Sparks"]'))
        )
        assert Sparks_btn is not None, "Sparks side-nav is not available"
        print("Sparks side-nav is available")

        Categories_btn = wait.until(
        EC.element_to_be_clickable((AppiumBy.XPATH, '//*[@realfocuskey="nav-menu-item-Categories"]'))
        )
        assert Categories_btn is not None, "Categories side-nav is not available"
        print("Categories side-nav is available")

    with allure.step("Navigate to Search"):
        search_btn = wait.until(
            EC.element_to_be_clickable((AppiumBy.XPATH, '//*[@realfocuskey="nav-menu-item-Search"]'))
        )
        search_btn.click()
        time.sleep(2)
        print("Opened search page")

    _search(driver,"How To Train Your Dragon")

    with allure.step("Select Search Result"):
        search_result = wait.until(
            EC.element_to_be_clickable((AppiumBy.XPATH, '//p[contains(text(), "How To Train Your Dragon")]'))
        )
        search_result.click()
        assert search_result is not None, "Search result not found"

    with allure.step("Start Playback"):
        watch_btn = wait.until(
            EC.element_to_be_clickable((AppiumBy.XPATH,'//*[text()="Watch from Beginning" or text()="Watch Now" or text()="Watch Latest Season"or text()="Watch First Episode"]'))
        )
        watch_btn.click()
        assert watch_btn is not None, "Watch button not available"

    with allure.step("Wait for Video Playback to Start (Spinner Invisibility)"):
        SPINNER_XPATH = '//*[@data-testid="loader"]'
        video_wait.until(
            EC.invisibility_of_element_located((AppiumBy.XPATH, SPINNER_XPATH))
        )
        video_player = wait.until(
            EC.visibility_of_element_located((AppiumBy.XPATH, '//div[@data-testid="skin-container"]'))
        )
        assert video_player is not None, "Video player not displayed"

    with allure.step("Modify Video Quality and Audio/Subtitles"):

        video_player.click() # Open controls
        video_wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//span[text()="Quality"]')))

        wait.until(
            EC.element_to_be_clickable((AppiumBy.XPATH, '//span[text()="Quality"]'))
        ).click()
        wait.until(
            EC.element_to_be_clickable((AppiumBy.XPATH, '//span[text()="Full HD"]'))
        ).click()

        wait.until(
            EC.element_to_be_clickable((AppiumBy.XPATH, '//span[text()="Audio & Subtitles"]'))
        ).click()
        wait.until(
            EC.element_to_be_clickable((AppiumBy.XPATH, '//span[text()="Tamil"]'))
        ).click()
        time.sleep(5)
        driver.execute_script("webos: pressKey", {"key": "UP"})
        wait.until(
            EC.element_to_be_clickable((AppiumBy.XPATH, '//span[text()="Audio & Subtitles"]'))
        ).click()
        wait.until(
            EC.element_to_be_clickable((AppiumBy.XPATH, '//span[text()="English [CC]"or text()="English"]'))
        ).click()
        video_player.click()  # Close controls

    with allure.step("Play for 10 seconds and Exit"):
        print("Playing with new settings for 10 seconds...")
        time.sleep(10)
        driver.back()  # Exit player
        driver.back()  # Exit Details page

        _navigate_back_to_home(driver)


