import re
import pytest
import allure
from appium import webdriver
from appium.options.common import AppiumOptions
from appium.webdriver.common.appiumby import AppiumBy
from selenium.common.exceptions import NoSuchElementException, TimeoutException, StaleElementReferenceException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
import time
import requests
import random
import json

# --- Configuration (Constants) ---
APPIUM_SERVER_URL = "http://127.0.0.1:4723"
DEVICE_NAME = "SamsungTV"
DEVICE_HOST = "172.23.12.114"
# fiZNCxMH9Y.Hotstar,Di0N6xZMEA.disneyplushotstarIN
APP_PACKAGE = "Di0N6xZMEA.disneyplushotstarIN"
RC_TOKEN = "94065092"  # ← add your paired token
CHROMEDRIVER_DIR = "C:\\chromedriver\\chromedriver_2.29\\chromedriver.exe"

# Static Test Data
User_Cookie = None
User_Token = None
HOME_LOCATOR = (AppiumBy.XPATH, "//div[@aria-label='Home']")


def load_config():
    # --- 2. Tell Python we are modifying the global variables ---
    global User_Cookie, User_Token

    # --- 3. Read the file ---
    try:
        with open('Usercredential.json', 'r') as file:
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
        print(f"API Request Failed: {e}")
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
        print(f"Failed to reset watch time: {e}")
        return None


# --- Pytest Fixtures ---

@pytest.fixture(scope="function")
@allure.title("Initialize Appium Driver for Tizen")
def driver_setup(request):
    """Initializes and yields Appium driver with extended timeouts."""
    print(f"\nSetting up driver for test: {request.node.name}...")
    appium_options = AppiumOptions()
    # --- Tizen-specific capabilities ---
    appium_options.platform_name = "TizenTV"
    appium_options.automation_name = "TizenTV"
    appium_options.set_capability("appium:deviceName", f"{DEVICE_HOST}:26101")
    appium_options.set_capability("appium:appPackage", APP_PACKAGE)
    appium_options.set_capability("appium:noReset", False)
    appium_options.set_capability("appium:rcMode", "remote")
    appium_options.set_capability("appium:rcToken", RC_TOKEN)
    # appium_options.set_capability("appium:rcOnly", True)
    appium_options.set_capability("appium:chromedriverExecutable", CHROMEDRIVER_DIR)
    appium_options.set_capability("appium:newCommandTimeout", 300)
    appium_options.set_capability("appium:rcKeypressCooldown", 1000)
    appium_options.set_capability("appium:sendKeysStrategy", "rc")

    driver = None
    try:
        # Initialize the driver
        driver = webdriver.Remote(APPIUM_SERVER_URL, options=appium_options)
        driver.implicitly_wait(5)

        # Initialize waiters
        ignored_exceptions = [StaleElementReferenceException]
        wait_50s = WebDriverWait(driver, 50, ignored_exceptions=ignored_exceptions)
        video_90s = WebDriverWait(driver, 90, ignored_exceptions=ignored_exceptions)

        print("App launched successfully.")

        # Yield the driver and waiters to the test function
        yield driver, wait_50s, video_90s

    except Exception as e:
        print(f"Error during driver initialization: {e}")
        pytest.fail(f"Driver setup failed with error: {e}")

    finally:
        # Teardown logic runs after the test finishes
        if driver:
            try:
                for attempt in range(2):
                    try:
                        print(f"Logout attempt {attempt + 1}...")
                        _logout(driver, wait_50s, _navigate_back_to_home)
                        print("Logout successful.")
                        break
                    except Exception as e:
                        print(f"Logout attempt {attempt + 1} failed: {e}")

                        if attempt < 1:
                            print("Waiting before retry...")
                            time.sleep(3)  # ⏳ small wait before retry
                        else:
                            print("Logout failed completely. App state might be unstable.")

            except Exception as e:
                print(f"Unexpected error during logout handling: {e}")

            print(f"\nRunning teardown for test: {request.node.name}...")
            driver.quit()
            print("App closed.")

        time.sleep(10)


# --- Tizen Key Press Helper ---

TIZEN_KEYS = {
    "ArrowLeft":  "KEY_LEFT",
    "ArrowRight": "KEY_RIGHT",
    "ArrowUp":    "KEY_UP",
    "ArrowDown":  "KEY_DOWN",
    "Enter":      "KEY_ENTER",
    "Home":       "KEY_HOME",
    "Back":       "KEY_BACK",
    "Return":     "KEY_RETURN",
}


def _press_key(driver, key):
    """
    Sends a remote control key press on Tizen TV.
    Accepts friendly names (e.g. 'ArrowLeft') or raw KEY_ codes directly.
    """
    tizen_key = TIZEN_KEYS.get(key, key)
    driver.execute_script("tizen: pressKey", {"key": tizen_key})


def  _tizen_js_click(driver, element):
    """
    Fires a click event directly on a DOM element via JavaScript, bypassing
    chromedriver's coordinate-based tap. Use this for any element that may
    shift position during a page transition or animation on Tizen TV.
    """
    driver.execute_script("arguments[0].click();", element)


def _nav_click(driver, wait, xpath, label="nav item"):
    """
    Tizen-safe side-nav click. Always use this instead of bare .click()
    when interacting with the side navigation bar.

    Steps:
      1. Sleep 2s  — lets CSS transition/slide animation fully settle so the
                     nav bar is at its final resting position before we resolve
                     the element's coordinates.
      2. scrollIntoView — ensures the element is in the visible viewport.
      3. Sleep 0.5s — tiny buffer after scroll before firing the event.
      4. JS click  — dispatches the click event on the DOM node directly,
                     sidestepping chromedriver's coordinate lookup entirely.
    """
    print(f"[_nav_click] Waiting for nav to settle before clicking: {label}")
    time.sleep(2)  # wait for any page transition / animation to finish

    element = wait.until(EC.presence_of_element_located((AppiumBy.XPATH, xpath)))
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", element)
    time.sleep(0.5)  # small buffer after scrollIntoView before firing click

    _tizen_js_click(driver, element)
    print(f"[_nav_click] Clicked: {label}")


# --- Reusable Utility Helpers ---

@allure.step("Perform Login with Phone Number {phone_number}")
def _login(driver, wait, phone_number, otp):
    print("Login Initiated")
    time.sleep(3)

    # # 1. Handle 'Continue' or 'Log In' prompt
    # try:
    #     continue_btn = driver.find_element(AppiumBy.XPATH, '//*[text()="Continue"]')
    #     continue_btn.click()
    # except NoSuchElementException:
    #     print("Continue button not found, proceeding...")

    # 2. Enter Phone Number
    wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, "//div[@role='textbox']")))
    with allure.step("Entering phone number digits"):
        for digit in phone_number:
            driver.find_element(AppiumBy.XPATH, f'//span[text()="{digit}"]').click()

    # 3. Click Get OTP
    get_otp_btn = wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, '//span[text()="Get OTP"]')))
    get_otp_btn.click()

    # 4. Enter OTP
    with allure.step("Entering OTP digits"):
        for digit in otp:
            wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, "//div[@data-testid='otp-login-lr']")))
            driver.find_element(AppiumBy.XPATH, f'//span[text()="{digit}"]').click()

    login_pending_elements = driver.find_elements(
        AppiumBy.XPATH, '//*[contains(text(),"Login Pending")]'
    )

    if login_pending_elements:
        try:
            logout_btn = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((AppiumBy.XPATH, "(//span[@title='Log Out'])[1]"))
            )
            logout_btn.click()
            print("Logout successful.")
        except TimeoutException:
            print("Login Pending present, but Logout button not found.")
    else:
        print("Login Pending not found, skipping logout...")


@allure.step("switching to kids profile")
def _switching_to_kids(driver, wait):
    _open_side_nav(driver)
    wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, "//div[@aria-label='My Space']"))).click()

    time.sleep(5)
    wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, "//p[text()='Kids']/ancestor::div[@data-testid='action']"))).click()

    time.sleep(3)


@allure.step("Switching to main profile from kids profile")
def _Switching_back_to_main_profile(driver, wait):
    wait.until(EC.element_to_be_clickable(HOME_LOCATOR)).click()  # Navigate to Myspace
    _open_side_nav(driver)
    wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, "//div[@aria-label='My Space']"))).click()

    # wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, "//p[text()='ADULT']/ancestor::div[@data-testid='action']"))).click()
    wait.until(
        EC.element_to_be_clickable((
            AppiumBy.XPATH,
            "//p[text()='ADULT' or text()='Adult' or text()='Nava' or text()='Prof']/ancestor::div[@data-testid='action']"
        ))
    ).click()
    time.sleep(1)
    try:
        # 2. Enter PIN
        pin_string = "1234"
        for digit in pin_string:
            driver.find_element(AppiumBy.XPATH, f'//span[text()="{digit}"]').click()
            time.sleep(2)
    except Exception as e:
        print(f"Error occurred while entering PIN: {e}")


@allure.step("Verify Home page elements are scrollable vertically and horizontally (Tizen)")
def _verify_home_scroll_tizen(driver, wait):
    """Scroll down x2, up x2, right x2, left x2 on Home and verify content loads (Tizen)."""

    wait.until(EC.visibility_of_element_located(HOME_LOCATOR))

    with allure.step("Scroll Down x2"):
        for i in range(2):
            _press_key(driver, "ArrowDown")
            time.sleep(1)

    with allure.step("Scroll Up x2"):
        for i in range(2):
            _press_key(driver, "ArrowUp")
            time.sleep(1)

    with allure.step("Scroll Right x2"):
        for i in range(2):
            _press_key(driver, "ArrowRight")
            time.sleep(1)

    with allure.step("Scroll Left x2"):
        for i in range(2):
            _press_key(driver, "ArrowLeft")
            time.sleep(1)

    print("Home page scroll verification complete (Tizen).")


@allure.step("Select Profile and Enter PIN")
def _profile_onboarding(driver, wait):
    print("Profile selection started")

    try:
        # 1. Select the main profile
        profile_img = wait.until(
            EC.element_to_be_clickable((AppiumBy.XPATH, "//p[text()='ADULT']/ancestor::div[@role='button']"))
        )
        profile_img.click()

        # 2. Enter PIN
        pin_button_1 = wait.until(
            EC.visibility_of_element_located((AppiumBy.XPATH, '//span[text()="1"]'))
        )

        if pin_button_1:
            pin_string = "1234"
            print(f"PIN entry visible. Entering PIN: {pin_string}")
            with allure.step("Entering profile PIN"):
                for digit in pin_string:
                    driver.find_element(AppiumBy.XPATH, f'//span[text()="{digit}"]').click()

    except Exception:
        print("Parental lock is not available for this user. Proceeding...")


@allure.step("Navigate to Nav Bar")
def _open_side_nav(driver, max_attempts=10):
    home_xpath = "//div[@aria-label='Home']"
    time.sleep(3)
    # driver.execute_script("tizen: pressKey", {"key": "KEY_ENTER"})
    time.sleep(2)
    for _ in range(max_attempts):
        elements = driver.find_elements("xpath", home_xpath)
        if elements:
            return elements[0]

        _press_key(driver, "ArrowLeft")
        time.sleep(1)

    raise Exception("Home side-nav not visible after navigating left")


@allure.step("Send app to background using HOME and relaunch the app")
def _background_and_reopen_validate(driver):

    wait = WebDriverWait(driver, 20)

    # --- Tizen: Press HOME key to background the app ---
    _press_key(driver, "Home")
    time.sleep(3)

    # --- Tizen: Relaunch the app using tizen:launchApp ---
    driver.execute_script("tizen:launchApp", {"appId": APP_PACKAGE})

    print("Application sent to background and relaunched successfully")


@allure.step("Validate Side Nav is displayed")
def _validate_side_nav(wait):
    with allure.step("Validate Side Nav is displayed"):
        nav_items = {
            "My Space": "//div[@aria-label='My Space']",
            "Home": "//div[@aria-label='Home']",
            "Search": "//div[@aria-label='Search']",
            "TV": "//div[@aria-label='TV']",
            "Movies": "//div[@aria-label='Movies']",
            "Sports": "//div[@aria-label='Sports']",
            "Categories": "//div[@aria-label='Categories']"
        }

        for name, xpath in nav_items.items():
            btn = wait.until(EC.presence_of_element_located((By.XPATH, xpath)))
            assert btn is not None, f"{name} side-nav is not available"
            print(f"{name} side-nav is available")


@allure.step("Navigate back to Home Screen gracefully")
def _navigate_back_to_home(driver, max_attempts=5, timeout_per_attempt=5):
    """
    Repeatedly calls driver.back() until the target home element is found.
    """
    print(f"Attempting to navigate back to Home Screen (max {max_attempts} attempts)...")

    for attempt in range(max_attempts):
        # quick check
        if driver.find_elements(*HOME_LOCATOR):
            return True

        try:
            WebDriverWait(driver, 2).until(
                EC.presence_of_element_located(HOME_LOCATOR)
            )
            return True
        except:
            driver.back()


@allure.step("Perform Logout")
def _logout(driver, wait, navigate_back_func):
    print("Logout initiated")
    try:
        # Ensure we are on the home screen before attempting to navigate the menu
        _navigate_back_to_home(driver)

        _open_side_nav(driver)

        wait.until(
            EC.element_to_be_clickable((AppiumBy.XPATH, "//div[@aria-label='My Space']"))
        ).click()
        try:
            help_settings = wait.until(
                EC.element_to_be_clickable((AppiumBy.XPATH, '//span[text()="Help & Settings"]'))
            )
        except TimeoutException:
            print("Help & Settings not found — likely kids profile. Switching to adult.")

            _Switching_back_to_main_profile(driver,wait)

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
        print(f"⚠️ Error during logout: {e}")
        if 'test_' in pytest.current_test:
            raise e


@allure.step("Search for term: {search_term}")
def _search(driver, search_term):
    time.sleep(5)
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
def _create_profile(driver, wait):
    profile_input = wait.until(
        EC.visibility_of_element_located((AppiumBy.XPATH, '//*[contains(text(),"Your Name")]'))
    )
    profile_input.click()

    _search(driver, "TEST")
    wait.until(
        EC.element_to_be_clickable((AppiumBy.XPATH, '//button[.//span[text()="Create Your Profile"]]'))
    ).click()
    time.sleep(2)
    lang_kannada = wait.until(
        EC.element_to_be_clickable(
            (AppiumBy.XPATH, '//div[./div[text()="Kannada"]]/ancestor::div[@data-testid="action"]'))
    )
    lang_kannada.click()

    wait.until(
        EC.element_to_be_clickable((AppiumBy.XPATH, '//*[@title="Continue"]'))
    ).click()


# --- Test Cases ---

@allure.story(
    "[Fresh User] Verify a Fresh User is able to Login and browse the app, verify Click on Subscribe CTA in Home Page & myspace ")
@allure.title("RL-T1487")
def test_case_RLT1487(driver_setup):
    driver, wait, _ = driver_setup
    fresh_phone, fresh_otp, fresh_hid = get_test_credentials("Phone_Fresh_User")

    if not fresh_phone:
        pytest.fail("Failed to fetch Phone_Fresh credentials from API")

    _login(driver, wait, fresh_phone, fresh_otp)

    _create_profile(driver, wait)
    time.sleep(2)
    _open_side_nav(driver)
    _validate_side_nav(wait)

    with allure.step("Tap on subscribe in my space"):
        myspace_btn = wait.until(
            EC.element_to_be_clickable((AppiumBy.XPATH, "//div[@aria-label='My Space']"))
        )
        myspace_btn.click()

        wait.until(
            EC.element_to_be_clickable((AppiumBy.XPATH, "//span[@title='Subscribe']"))
        ).click()

        validate_psp_page_visible(wait)

        driver.back()

    with allure.step("Try to play any content"):
        _open_side_nav(driver)
        _press_key(driver, "ArrowLeft")
        time.sleep(5)
        # search_btn = wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, "//div[@role='menuitem'][.//span[text()='Search']]")))
        # driver.execute_script("arguments[0].focus();", search_btn)
        # time.sleep(1)
        _nav_click(driver,wait,"//div[@role='menuitem'][.//span[text()='Search']]","Search")

        _search(driver, "King and Conqueror")
        wait.until(
            EC.element_to_be_clickable((AppiumBy.XPATH, '//*[text()="King & Conqueror"]'))
        ).click()

        wait.until(
            EC.element_to_be_clickable((AppiumBy.XPATH, '//*[text()="Subscribe to Watch"]'))
        ).click()

        validate_psp_page_visible(wait)

        driver.back()
        _navigate_back_to_home(driver)


@allure.story(
    "[Free User]As a Free user, I go to Sports Sub menu and I see PSP upon playing non-free live content, I am allowed to play free live contents for 4hrs and i see PSP page after completing 4hrs of free timer")
@allure.title("RL-T356")
@pytest.mark.testcase1
def test_case_RLT356(driver_setup):
    driver, wait, video_wait = driver_setup
    free_phone, otp, hid = get_test_credentials("Free_Timer_Eligible_users_two")
    if not free_phone:
        pytest.fail("Failed to fetch Phone_Fresh credentials from API")
    reset_user_watch_time(hid, watch_time_ms=7134000)

    _login(driver, wait, free_phone, otp)
    _profile_onboarding(driver, wait)
    time.sleep(5)
    _open_side_nav(driver)
    _nav_click(driver, wait, "//div[@role='menuitem'][.//span[text()='Search']]", "Search")
    time.sleep(5)

    _search(driver, "Thaai Kizhavi")
    wait.until(
        EC.element_to_be_clickable((AppiumBy.XPATH, '//*[text()="Thaai Kizhavi"]'))
    ).click()

    # _nav_click(driver, wait, "//div[@aria-label='Movies']", "Movies")
    #
    # time.sleep(5)
    # movie_tray = wait.until(
    #     EC.element_to_be_clickable(
    #         (AppiumBy.XPATH, "(//div[@data-testid='hs-image']//img/ancestor::div[@role='button'])[1]"))
    # )
    # movie_tray.click()
    with allure.step("Start Playback"):
        watch_btn = wait.until(EC.element_to_be_clickable((AppiumBy.XPATH,
                                                           '//*[text()="Watch from Beginning" or text()="Watch Now" or text()="Watch Latest Season"or text()="Watch First Episode"]')))
        watch_btn.click()
        assert watch_btn is not None, "Watch button not available"
        print("Playback started")
        time.sleep(5)
    timer_locator = (AppiumBy.XPATH, "//span[contains(@class, 'BUTTON2_MEDIUM') and contains(text(), ':')]")
    time.sleep(20)
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

    # --- Tizen: use ArrowDown instead of webOS "down" ---
    _press_key(driver, "ArrowDown")

    hp_banner = wait.until(
        EC.visibility_of_element_located((AppiumBy.XPATH, '//*[contains(text(), "Your free access is over") or contains(text(), "Plans starting at")]'))
    )
    assert hp_banner is not None, "Honeypot banner is not displayed"
    print("Honeypot banner is displayed")
    time.sleep(1)

    # _tizen_js_click(driver,'//button[.//*[text()="Subscribe"]]')
    # driver.find_element(AppiumBy.XPATH, '//button[.//*[text()="Subscribe"]]').click()
    # --- Tizen: use Enter key instead of webOS "enter" ---
    _press_key(driver, "Enter")

    validate_psp_page_visible(wait)

    driver.back()


@allure.story(
    "[Premium User]As a Premium user, I am playing a series from TV Submenu and seeing Binge Controls, Watch Next/MLT trays and able to play Series more than 10mins without any interruption")
@allure.title("RL-T375")
@pytest.mark.testcase3
def test_case_T375_4K_Seasons(driver_setup):
    """Validates 4K logos and season navigation."""
    driver, wait, video_wait = driver_setup
    premium_phone, otp, hid = get_test_credentials("Phone_Smppremium")
    if not premium_phone:
        pytest.fail("Failed to fetch Phone_Fresh credentials from API")

    _login(driver, wait, premium_phone, otp)
    _profile_onboarding(driver, wait)
    _open_side_nav(driver)
    _validate_side_nav(wait)

    # --- Tizen: use ArrowLeft instead of webOS "left" ---
    _nav_click(driver, wait, "//div[@role='menuitem'][.//span[text()='Search']]", "Search")
    _search(driver, "Resort")
    wait.until(
        EC.element_to_be_clickable((AppiumBy.XPATH, "//p[text()='Resort']"))
    ).click()

    time.sleep(3)

    watch_xpath = '//*[text()="Watch from Beginning" or text()="Watch Now" or text()="Watch Latest Season"or text()="Watch First Episode"]'
    driver.find_element(AppiumBy.XPATH, watch_xpath).click()
    time.sleep(3)
    try:
        SPINNER_XPATH = '//*[@data-testid="loader"]'
        video_wait.until(EC.invisibility_of_element_located((AppiumBy.XPATH, SPINNER_XPATH)))
        video_player = wait.until(
            EC.visibility_of_element_located((AppiumBy.XPATH, '//div[@data-testid="skin-container"]')))
        time.sleep(3)
    except Exception as e:
        print(f"Video Play failed & T375 failed: {e}")
    try:
        # --- Tizen: use ArrowUp instead of webOS "UP" ---
        _press_key(driver, "ArrowUp")
        skip_recap = driver.find_element(AppiumBy.XPATH, "//*[@title='Skip Recap']")
        assert skip_recap.is_displayed(), "Skip Recap button was not visible on screen"
        skip_recap.click()
    except Exception as e:
        print(f"Recap is not available {e}")

    try:
        _press_key(driver, "ArrowUp")
        quality_btn = wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, "//*[@title='Quality']")))
        quality_btn.click()
        asli_4k_option = wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, "//span[text()='Asli 4K']")))
        asli_4k_option.click()
        time.sleep(5)
        asli_4k_logo = driver.find_element(AppiumBy.XPATH, "//*[@class='ASLI_4K_LOGO_WRAPPER']")
        assert asli_4k_logo.is_displayed(), "Asli 4K logo is not displayed after selection"
        _press_key(driver, "ArrowUp")
        quality_btn.click()
        fhd_option = wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, "//span[text()='Full HD']")))
        fhd_option.click()
        time.sleep(5)
        logos = driver.find_elements(AppiumBy.XPATH, "//*[@class='ASLI_4K_LOGO_WRAPPER']")
        assert len(logos) == 0
    except Exception as e:
        print(f"T375 Quality change failed, seems a Non 4K device: {e}")

    # 1. Get the current episode name
    _press_key(driver, "ArrowUp")
    ep_name_xpath = "//div[@class='pgYQn-YxdROBlrWtyE7dG']/p[2]"

    element = WebDriverWait(driver, 10).until(
        EC.visibility_of_element_located((AppiumBy.XPATH, ep_name_xpath))
    )

    current_episode_name = element.text
    print(f"Detected Episode: {current_episode_name}")

    # 2. Click on 'Next Episode'
    try:
        next_btn_xpath = "//*[text()='Next Episode']"
        wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, next_btn_xpath))).click()

        # 3. Wait for the UI to update
        time.sleep(15)

        # 4. Get the new episode name and Assert they are different
        # --- Tizen: use ArrowDown instead of webOS "down" ---
        _press_key(driver, "ArrowDown")
        wait.until(EC.presence_of_element_located((AppiumBy.XPATH, ep_name_xpath)))
        next_episode_name = driver.find_element(AppiumBy.XPATH, ep_name_xpath).text
        assert current_episode_name != next_episode_name, f"Episode name did not change! Still: {current_episode_name}"
    except Exception as e:
        print("Seems its last episode.")

    # 5. Assert Episodes Tray visibility
    episodes_tray = driver.find_element(AppiumBy.XPATH, "//*[text()='Episodes']")
    assert episodes_tray.is_displayed(), "Episodes tray is not visible after navigation"
    driver.back()  # Back from watchPage
    time.sleep(3)
    driver.back()  # Back from details page
    _switching_to_kids(driver, wait)
    # Switched to Kids Profile
    _open_side_nav(driver)
    time.sleep(5)
    _nav_click(driver, wait, "//div[@role='menuitem'][.//span[text()='Search']]", "Search")
    time.sleep(5)
    _search(driver, "How To Train Your Dragon")

    time.sleep(3)
    search_result = wait.until(
        EC.element_to_be_clickable((AppiumBy.XPATH, '//p[contains(text(), "How To Train Your Dragon")]')))
    search_result.click()
    assert search_result is not None, "Search result not found"
    wait.until(EC.element_to_be_clickable(
        (AppiumBy.XPATH, "//*[@title='Watch from Beginning' or @title='Watch Now']"))).click()
    time.sleep(15)
    _press_key(driver, "ArrowUp")
    _press_key(driver, "ArrowUp")
    time.sleep(2)
    wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, '//span[text()="Quality"]'))).click()
    time.sleep(3)
    asli_4k_option = wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, "//span[text()='Asli 4K']")))
    asli_4k_option.click()

    time.sleep(5)
    asli_4k_logo = driver.find_element(AppiumBy.XPATH, "//*[@class='ASLI_4K_LOGO_WRAPPER']")
    assert asli_4k_logo.is_displayed(), "Asli 4K logo is not displayed after selection"

    driver.back()  # Back to details page
    time.sleep(2)
    driver.back()  # Back to Search page
    _Switching_back_to_main_profile(driver, wait)


@allure.story(
    "[Free User] As a Free user, I see trailer auto-play based on LPV, check static paywall on KIDS profile after no free timer and check phonepe QR and scan scan the QR, Check amount is loaded correctly")
@allure.title("RL-T357")
@pytest.mark.testcase2
def test_case_T357_Kids_Restrictions(driver_setup):
    """Validates restrictions and trailers in Kids profile."""
    driver, wait, _ = driver_setup
    phone_free, otp, hid = get_test_credentials("Free_Timer_Eligible_users_two")
    if not phone_free:
        pytest.fail("Failed to fetch Phone_Fresh credentials from API")

    reset_user_watch_time(hid, watch_time_ms=74440000)

    _login(driver, wait, phone_free, otp)
    _profile_onboarding(driver, wait)
    wait.until(EC.visibility_of_element_located(HOME_LOCATOR))
    _open_side_nav(driver)
    _nav_click(driver, wait, "//div[@aria-label='Search']", "Search")
    time.sleep(5)
    _search(driver, "Sarvam Maya")

    time.sleep(3)
    search_result = wait.until(
        EC.element_to_be_clickable((AppiumBy.XPATH, '//p[contains(text(), "Sarvam Maya")]')))
    search_result.click()

    # _nav_click(driver, wait, "//div[@aria-label='Movies']", "Movies")
    #
    # time.sleep(5)
    # _press_key(driver, "ArrowDown")
    # time.sleep(2)
    # for i in range(10):
    #     count = 0
    #
    #     languages = driver.find_elements(AppiumBy.XPATH, "//*[contains(text(),'Languages')]")
    #
    #     if languages:
    #         language_text = languages[0].text
    #         print("Found text:", language_text)
    #
    #         match = re.search(r'\d+', language_text)
    #         if match:
    #             count = int(match.group())
    #
    #     print("Extracted count:", count)
    #
    #     if count >= 4:
    #         print("Condition met. Pressing ENTER")
    #         # --- Tizen: use Enter instead of webOS "ENTER" ---
    #         _press_key(driver, "Enter")
    #         break
    #     else:
    #         print("Condition not met. Moving RIGHT")
    #         _press_key(driver, "ArrowRight")
    #         time.sleep(2)
    #
    # time.sleep(5)  # outside loop

    try:
        # 3. Verify Trailer Autoplay
        trailer_Element = "//div[@id='autoplay-container']//div//video"
        wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, trailer_Element)))

        time.sleep(3)
        error_Msg = driver.find_elements(AppiumBy.XPATH, "//*[contains(text(),'Trailer is unavailable')]")
        if len(error_Msg) > 0:
            assert error_Msg[0].is_displayed()
        else:
            # 5. Verify Autoplay is still happening
            wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, trailer_Element)))
    except Exception as e:
        print(f"trailer not available: {e}")

    languages = wait.until(
        EC.presence_of_all_elements_located(
            (By.XPATH, "//button[contains(@data-testid,'pill-')]")
        )
    )

    print("Total languages found:", len(languages))

    # Step 2: Pick random language
    random_language = random.choice(languages)

    print("Selected language:", random_language.text)

    # Step 3: Click it
    driver.execute_script("arguments[0].click();", random_language)
    time.sleep(5)

    # 9. Go back
    time.sleep(3)
    driver.back()

    _switching_to_kids(driver, wait)
    _open_side_nav(driver)
    _nav_click(driver, wait, "//div[@role='menuitem'][.//span[text()='Search']]", "Search")
    time.sleep(3)
    _search(driver, "How To Train Your Dragon")

    time.sleep(3)
    search_result = wait.until(
        EC.element_to_be_clickable((AppiumBy.XPATH, '//p[contains(text(), "How To Train Your Dragon")]')))
    search_result.click()

    wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, "//span[@title='Subscribe to Watch' or @title='Upgrade to Watch']"))).click()
    validate_psp_page_visible(wait)
    time.sleep(2)
    driver.back()  # to PSP
    time.sleep(2)
    driver.back()  # to details Page
    _Switching_back_to_main_profile(driver, wait)


@allure.story(
    "[Premium User] Verify a Premium User is able to login, search a content & playbck. User is able to logout of the app")
@allure.title("RL-T1488")
@pytest.mark.testcase5
def test_case_T1488_watch_movie(driver_setup):
    driver, wait, video_wait = driver_setup

    phone_premium, otp, hid = get_test_credentials("Phone_Smppremium")
    if not phone_premium:
        pytest.fail("Failed to fetch Phone_Fresh credentials from API")

    _login(driver, wait, phone_premium, otp)
    _profile_onboarding(driver, wait)
    _open_side_nav(driver)
    _validate_side_nav(wait)
    # --- Tizen: use ArrowLeft instead of webOS "left" ---
    # _press_key(driver, "ArrowLeft")
    _nav_click(driver, wait, "//div[@role='menuitem'][.//span[text()='Search']]", "Search")
    time.sleep(3)
    _search(driver, "How To Train Your Dragon")

    time.sleep(3)
    search_result = wait.until(
        EC.element_to_be_clickable((AppiumBy.XPATH, '//p[contains(text(), "How To Train Your Dragon")]')))
    search_result.click()
    assert search_result is not None, "Search result not found"

    with allure.step("Start Playback"):
        watch_btn = wait.until(
            EC.element_to_be_clickable((AppiumBy.XPATH,
                                        '//*[text()="Watch from Beginning" or text()="Watch Now" or text()="Watch Latest Season"or text()="Watch First Episode"]'))
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
        video_player.click()  # Open controls
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
        # --- Tizen: use ArrowUp instead of webOS "UP" ---
        _press_key(driver, "ArrowUp")
        wait.until(
            EC.element_to_be_clickable((AppiumBy.XPATH, '//span[text()="Audio & Subtitles"]'))
        ).click()
        wait.until(
            EC.element_to_be_clickable((AppiumBy.XPATH, "//span[contains(text(), 'English [CC]')]"))
        ).click()
        video_player.click()  # Close controls

    with allure.step("Play for 10 seconds and Exit"):
        print("Playing with new settings for 10 seconds...")
        time.sleep(10)
        driver.back()  # Exit player
        driver.back()  # Exit Details page
