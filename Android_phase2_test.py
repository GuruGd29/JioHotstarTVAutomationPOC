import pytest
import allure
from appium import webdriver
from appium.options.common import AppiumOptions
from appium.webdriver.common.appiumby import AppiumBy
from appium.webdriver.extensions.android.nativekey import AndroidKey
from selenium.common.exceptions import NoSuchElementException, TimeoutException, StaleElementReferenceException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import tv_actions
import time
import requests
import random
import json

# --- Configuration (Constants) ---
APPIUM_SERVER_URL = "http://127.0.0.1:4723"
DEVICE_NAME = "172.23.14.67"                    # Update with your device name (adb devices)
PLATFORM_VERSION = "11"                    # Update with your Android version
APP_PACKAGE = "in.startv.hotstar"        # Hotstar Android package name
APP_ACTIVITY = "com.hotstar.MainActivity"  # Update if different

# Static Test Data
User_Cookie = None
User_Token = None

# Android KeyCodes
KEYCODE_BACK = 4
KEYCODE_DPAD_UP = 19
KEYCODE_DPAD_DOWN = 20
KEYCODE_DPAD_LEFT = 21
KEYCODE_DPAD_RIGHT = 22
KEYCODE_DPAD_CENTER = 23
KEYCODE_ENTER = 66

HOME_LOCATOR = (AppiumBy.XPATH, '(//android.widget.TextView[@resource-id="in.startv.hotstar:id/tv_title" and @text="Home"] | //androidx.recyclerview.widget.RecyclerView[@resource-id="in.startv.hotstar:id/container_list"])')


def load_config():
    global User_Cookie, User_Token
    try:
        with open('Usercredential.json', 'r') as file:
            data = json.load(file)
            User_Token = data.get("xsrf-token")
            User_Cookie = data.get("Cookie")
    except Exception as e:
        print(f"Failed to load config: {e}")

load_config()


# --- API Integration Functions ---
# (Reused exactly from webOS version)

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
            print(phone)
            print(otp)
            return str(phone), str(otp), str(hid)
        else:
            return None, None, None
    except Exception as e:
        print(f"API Request Failed: {e}")
        return None, None, None


@allure.step("Resetting Watch Time for HID: {hid}")
def reset_user_watch_time(hid, watch_time_ms):
    """Calls the watch-time-processor debug API to set specific watch time."""
    url = f"https://origin-hs-watch-time-processor.sgp.hotstar-prod.com/debug?hid={hid}"
    headers = {'Content-Type': 'application/json'}
    payload = {"watchTimeMs": watch_time_ms}
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
@allure.title("Initialize Appium Driver for Android")
def driver_setup(request):
    """Initializes and yields Appium driver for Android."""
    print(f"\nSetting up driver for test: {request.node.name}...")
    appium_options = AppiumOptions()
    appium_options.platform_name = "Android"
    appium_options.automation_name = "UiAutomator2"
    appium_options.set_capability("appium:deviceName", DEVICE_NAME)
    appium_options.set_capability("appium:platformVersion", PLATFORM_VERSION)
    appium_options.set_capability("appium:appPackage", APP_PACKAGE)
    appium_options.set_capability("appium:appActivity", APP_ACTIVITY)
    appium_options.set_capability("appium:noReset", False)
    appium_options.set_capability("appium:forceAppLaunch", True)
    appium_options.set_capability("appium:autoGrantPermissions", True)
    appium_options.set_capability("appium:newCommandTimeout", 300)
    appium_options.set_capability("appium:appWaitActivity", "*")
    appium_options.set_capability("appium:uiautomator2ServerLaunchTimeout", 60000)
    appium_options.set_capability("appium:adbExecTimeout", 60000)

    driver = None
    try:
        driver = webdriver.Remote(APPIUM_SERVER_URL, options=appium_options)
        driver.implicitly_wait(5)

        ignored_exceptions = [StaleElementReferenceException]
        wait_50s = WebDriverWait(driver, 50, ignored_exceptions=ignored_exceptions)
        video_90s = WebDriverWait(driver, 90, ignored_exceptions=ignored_exceptions)

        print("App launched successfully.")
        time.sleep(10)
        yield driver, wait_50s, video_90s

    except Exception as e:
        print(f"Error during driver initialization: {e}")
        pytest.fail(f"Driver setup failed with error: {e}")

    finally:
        if driver:
            try:
                _logout(driver, wait_50s, _navigate_back_to_home)
            except Exception as e:
                print(f"Warning: Logout failed during tearDown: {e}")
            print(f"\nRunning teardown for test: {request.node.name}...")
            driver.quit()
            print("App closed.")
        time.sleep(2)


# --- Reusable Utility Helpers ---

@allure.step("Perform Login with Phone Number {phone_number}")
def _login(driver, wait, phone_number, otp):
    """Login using phone number keypad on Android."""
    print("Login Initiated")
    # 1. Handle 'Continue' or 'Log In' prompt
    try:
        continue_btn = WebDriverWait(driver, 20).until(
            EC.element_to_be_clickable((
                AppiumBy.ID,'in.startv.hotstar:id/btn_continue')))
        continue_btn.focusandclick()
    except NoSuchElementException:
        print("Continue button not found, proceeding...")

    # 2. Enter Phone Number
    with allure.step("Entering phone number digits"):
        wait.until(EC.visibility_of_element_located((AppiumBy.ID, 'in.startv.hotstar:id/textinput_placeholder')))
        for digit in phone_number:
            keycode = 7 + int(digit)
            driver.press_keycode(keycode)
            time.sleep(0.8)

    # 3. Click Get OTP
    get_otp_btn = wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, '//*[@text="Get OTP"]')))
    get_otp_btn.click()
    time.sleep(2)

    # 4. Enter OTP
    with allure.step("Entering OTP digits"):
        for digit in otp:
            keycode = 7 + int(digit)
            driver.press_keycode(keycode)
            time.sleep(0.8)

    try:
        logout_btn = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((AppiumBy.XPATH, '//*[@text="Log Out"]'))
        )
        logout_btn.click()
        print("Logout successful.")
    except TimeoutException:
        print("Logout button not present, skipping this step...")


@allure.step("Switching to Kids profile")
def _switching_to_kids(driver, wait):
    #myspace click
    wait.until(
        EC.element_to_be_clickable((AppiumBy.ANDROID_UIAUTOMATOR, 'new UiSelector().text("My Space")'))).focusandclick()

    time.sleep(5)
    wait.until(EC.element_to_be_clickable((AppiumBy.XPATH,'(//android.widget.TextView[@resource-id="in.startv.hotstar:id/profile_name" and @text="Kids"])[1]'))).focusandclick()
    time.sleep(3)


@allure.step("Switching back to main profile from Kids profile")
def _Switching_back_to_main_profile(driver, wait):
    time.sleep(3)
    _open_side_nav(driver)
    driver.press_keycode(KEYCODE_DPAD_LEFT)
    # myspace click
    wait.until(
        EC.element_to_be_clickable((AppiumBy.ANDROID_UIAUTOMATOR, 'new UiSelector().text("My Space")'))).focusandclick()

    time.sleep(5)
    adult_profile = (AppiumBy.XPATH,
                     '(//android.widget.TextView[@resource-id="in.startv.hotstar:id/profile_name" and @text="ADULT"])')
    fallback_profile = (AppiumBy.XPATH,
                        '(//android.widget.ImageView[@resource-id="in.startv.hotstar:id/iv_profile"])[1]')
    try:
        # 1. Try to find the 'ADULT' profile with a short, specific wait
        element = WebDriverWait(driver, 5).until(EC.element_to_be_clickable(adult_profile))
        element.focusandclick()
        print("Clicked ADULT profile.")

    except TimeoutException:
        # 2. If 'ADULT' isn't found, try the fallback ImageView
        print("ADULT profile not found, trying fallback...")
        try:
            element = WebDriverWait(driver, 5).until(EC.element_to_be_clickable(fallback_profile))
            element.focusandclick()
            print("Clicked fallback profile image.")
        except TimeoutException:
            print("Neither element was found on the screen.")
    parental_lock = wait.until(
        EC.visibility_of_element_located((AppiumBy.ID, 'in.startv.hotstar:id/tv_parental_lock'))
    )

    if parental_lock:
        pin_string = "1234"
        print(f"PIN entry visible. Entering PIN: {pin_string}")

        with allure.step("Entering profile PIN"):
            for digit in pin_string:
                keycode = 7 + int(digit)
                driver.press_keycode(keycode)
                print(f"Entered digit: {digit}")
                time.sleep(0.8)


@allure.step("Verify Home page elements are scrollable vertically and horizontally")
def _verify_home_scroll(driver, wait):
    """Scroll down x2, up x2, right x2, left x2 on Home and verify content loads."""

    wait.until(EC.visibility_of_element_located(HOME_LOCATOR))

    with allure.step("Scroll Down x2"):
        for i in range(2):
            driver.press_keycode(KEYCODE_DPAD_DOWN)
            time.sleep(1)

    with allure.step("Scroll Right x2"):
        for i in range(2):
            driver.press_keycode(KEYCODE_DPAD_RIGHT)
            time.sleep(1)

    with allure.step("Scroll Left x2"):
        for i in range(2):
            driver.press_keycode(KEYCODE_DPAD_LEFT)
            time.sleep(1)

    with allure.step("Scroll Up x2"):
        for i in range(2):
            driver.press_keycode(KEYCODE_DPAD_UP)
            time.sleep(1)

    print("Home page scroll verification completed")

def press_up_until_quality(driver, timeout=30, interval=3):

    end_time = time.time() + timeout

    while time.time() < end_time:
        try:
            element = driver.find_element(
                AppiumBy.ANDROID_UIAUTOMATOR,
                'new UiSelector().text("Quality")'
            )
            if element.is_displayed():
                print("Quality option is visible")
                return True
        except NoSuchElementException:
            pass

        print("Quality not visible, pressing DPAD_UP...")

        try:
            # Preferred (more stable)
            driver.execute_script("mobile: pressKey", {"keycode": KEYCODE_DPAD_UP})
        except:
            # Fallback
            driver.press_keycode(KEYCODE_DPAD_UP)

        time.sleep(interval)

    print("Timeout: 'Quality' not found")
    return False

@allure.step("Select Profile and Enter PIN")
def _profile_onboarding(driver, wait):
    """Select main profile and enter PIN if required."""
    print("Profile selection started")

    try:

        # Check if PIN screen appears
        try:
            parental_lock = wait.until(
                EC.visibility_of_element_located((AppiumBy.ID, 'in.startv.hotstar:id/tv_parental_lock'))
            )

            if parental_lock:
                pin_string = "1234"
                print(f"PIN entry visible. Entering PIN: {pin_string}")

                with allure.step("Entering profile PIN"):
                    for digit in pin_string:
                        keycode = 7 + int(digit)
                        driver.press_keycode(keycode)
                        print(f"Entered digit: {digit}")
                        time.sleep(0.8)

        except Exception:
            print("Parental lock not available for this user. Proceeding...")

    except Exception:
        print("Profile selection screen not available. Skipping profile onboarding.")

def _open_side_nav(driver, max_attempts=10):
    home_xpath = '//android.widget.TextView[@resource-id="in.startv.hotstar:id/tv_title" and @text="Home"]'

    for _ in range(max_attempts):
        elements = driver.find_elements(AppiumBy.XPATH, home_xpath)
        if elements:
            return elements[0]  # return the element once found

        driver.press_keycode(21)  # KEYCODE_DPAD_LEFT
        time.sleep(1)

    raise Exception("Home side-nav not visible after navigating left")

def _validate_side_nav(wait):
    with allure.step("Validate Side Nav is displayed"):
        nav_items = {
            "My Space": '//android.widget.TextView[@resource-id="in.startv.hotstar:id/tv_title" and @text="My Space"]',
            "Home": '//android.widget.TextView[@resource-id="in.startv.hotstar:id/tv_title" and @text="Home"]',
            "Search": '//android.widget.TextView[@resource-id="in.startv.hotstar:id/tv_title" and @text="Search"]',
            "TV": '//android.widget.TextView[@resource-id="in.startv.hotstar:id/tv_title" and @text="TV"]',
            "Movies": '//android.widget.TextView[@resource-id="in.startv.hotstar:id/tv_title" and @text="Movies"]',
            "Sports": '//android.widget.TextView[@resource-id="in.startv.hotstar:id/tv_title" and @text="Sports"]',
            "Categories": '//android.widget.TextView[@resource-id="in.startv.hotstar:id/tv_title" and @text="Categories"]'
        }

        for name, xpath in nav_items.items():
            btn = wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, xpath)))
            assert btn is not None, f"{name} side-nav is not available"
            print(f"{name} side-nav is available")


@allure.step("Navigate back to Home Screen gracefully")
def _navigate_back_to_home(driver, max_attempts=5, timeout_per_attempt=5):
    """Repeatedly presses back until the home element is found."""
    print(f"Attempting to navigate back to Home Screen (max {max_attempts} attempts)...")
    nav_home_button = '//android.widget.TextView[@resource-id="in.startv.hotstar:id/tv_title" and @text="Home"]'
    for attempt in range(1, max_attempts + 1):
        try:
            home_check = WebDriverWait(driver, timeout_per_attempt).until(
                EC.visibility_of_element_located(HOME_LOCATOR))
            print(f"Successfully reached Home Screen on attempt {attempt}.")
            return home_check
        except TimeoutException:
            print(f"Attempt {attempt}/{max_attempts}: Home element not found. Pressing back.")
            driver.press_keycode(KEYCODE_BACK)
            driver.press_keycode(KEYCODE_DPAD_LEFT)
            time.sleep(1)
    raise TimeoutException("Failed to navigate back to the Home Screen after maximum attempts.")

@allure.step("Send app to background using HOME and relaunch the app")
def _background_and_reopen_validate(driver):

    wait = WebDriverWait(driver, 20)

    driver.press_keycode(3)
    time.sleep(5)

    wait.until(lambda d: d.current_package != APP_PACKAGE)

    driver.activate_app(APP_PACKAGE)

    wait.until(lambda d: d.current_package == APP_PACKAGE)

    print("Application closed and reopened")


@allure.step("Perform Logout")
def _logout(driver, wait, navigate_back_func):
    """Logs the user out via Settings menu."""
    print("Logout initiated")
    try:
        # Ensure we are on the home screen before attempting to navigate the menu
        _navigate_back_to_home(driver)

        _open_side_nav(driver)

        wait.until(
            EC.element_to_be_clickable((AppiumBy.ANDROID_UIAUTOMATOR, 'new UiSelector().text("My Space")'))
        ).focusandclick()
        try:
            help_settings = wait.until(
                EC.element_to_be_clickable((AppiumBy.ID, 'in.startv.hotstar:id/btn_help_settings_cta'))
            )
        except TimeoutException:
            print("Help & Settings not found — likely kids profile. Switching to adult.")

            _Switching_back_to_main_profile(driver,wait)
        wait.until(
            EC.element_to_be_clickable((AppiumBy.ID, 'in.startv.hotstar:id/btn_help_settings_cta'))).focusandclick()
        wait.until(EC.element_to_be_clickable((AppiumBy.ID, 'in.startv.hotstar:id/btn_logout'))).focusandclick()
        wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, '//*[@text="Log Out"]'))).click()
        print("Logout successful")

    except Exception as e:
        # Log the error but allow teardown to continue if possible
        print(f"Error during logout: {e}")
        # Re-raise the exception only if in a test body, not in teardown cleanup
        if 'test_' in pytest.current_test:
            raise e



@allure.step("Search for term: {search_term}")
def _search(driver, search_term):
    """Types a search term using the on-screen keyboard."""
    for char in search_term:
        key_to_press = "Space" if char == ' ' else char.upper()
        xpath_expression = f'//*[@text="{key_to_press}" or @content-desc="{key_to_press}"]'
        try:
            driver.find_element(AppiumBy.XPATH, xpath_expression).click()
        except Exception as e:
            print(f"Error clicking key '{key_to_press}': {e}")
            raise


@allure.step("Validate that the PSP page is displayed")
def validate_psp_page_visible(wait, timeout_msg="PSP page not found"):
    """Verifies the user has reached the Subscription/PSP screen."""
    try:
        psp_premium = wait.until(
            EC.element_to_be_clickable((AppiumBy.ANDROID_UIAUTOMATOR, 'new UiSelector().text("PREMIUM")')))
        psp_super = wait.until(
            EC.element_to_be_clickable((AppiumBy.ANDROID_UIAUTOMATOR, 'new UiSelector().text("SUPER")')))
        assert psp_premium is not None, timeout_msg
        assert psp_super is not None, timeout_msg
        print("Verification Successful: PSP page is available.")
        return True
    except TimeoutException:
        print(f"Verification Failed: {timeout_msg}")
        pytest.fail(timeout_msg)


@allure.step("Create profile for fresh user")
def _create_profile(driver, wait):
    """Creates a profile for a fresh/new user."""
    profile_input = wait.until(
        EC.visibility_of_element_located((AppiumBy.XPATH,
        '//android.widget.EditText[@resource-id="in.startv.hotstar:id/et_user_name"]'))
    )
    profile_input.click()
    username = wait.until(
        EC.visibility_of_element_located((AppiumBy.XPATH,
                                          '//android.widget.EditText[@resource-id="in.startv.hotstar:id/et_name"]'))
    )
    username.send_keys("Test")

    time.sleep(1)
    driver.press_keycode(KEYCODE_DPAD_DOWN)
    driver.press_keycode(KEYCODE_DPAD_DOWN)
    driver.press_keycode(KEYCODE_DPAD_DOWN)
    driver.press_keycode(KEYCODE_DPAD_LEFT)
    driver.press_keycode(KEYCODE_DPAD_CENTER)

    # wait.until(EC.element_to_be_clickable((AppiumBy.XPATH,'//android.view.ViewGroup[@resource-id="in.startv.hotstar:id/btn_continue"]'))).click()
    time.sleep(5)
    lang_kannada = wait.until(
        EC.element_to_be_clickable(
            (AppiumBy.XPATH, '(//android.widget.ImageView[@resource-id="in.startv.hotstar:id/heart_frame"])[8]')
        )
    )
    lang_kannada.click()
    wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, '//android.view.ViewGroup[@resource-id="in.startv.hotstar:id/btn_continue"]'))).click()


# --- Test Cases ---

@allure.story("[Fresh User] Verify a Fresh User is able to Login and browse the app, verify Click on Subscribe CTA in Home Page & myspace")
@allure.title("RL-T1487")
def test_case_RLT1487(driver_setup):
    driver, wait, _ = driver_setup
    fresh_phone, fresh_otp, fresh_hid = get_test_credentials("Phone_Fresh_User")

    if not fresh_phone:
        pytest.fail("Failed to fetch Phone_Fresh credentials from API")

    _login(driver, wait, fresh_phone, fresh_otp)
    _create_profile(driver, wait)
    wait.until(EC.visibility_of_element_located(HOME_LOCATOR))
    _verify_home_scroll(driver, wait)
    _open_side_nav(driver)
    _validate_side_nav(wait)

    with allure.step("Tap on Subscribe in My Space"):
        wait.until(EC.element_to_be_clickable((AppiumBy.ANDROID_UIAUTOMATOR, 'new UiSelector().text("My Space")'))).focusandclick()
        wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, '//android.view.ViewGroup[@resource-id="in.startv.hotstar:id/btn_cta"]'))).focusandclick()
        validate_psp_page_visible(wait)
        driver.press_keycode(KEYCODE_BACK)

    with allure.step("Search and attempt to play premium content"):
        _open_side_nav(driver)
        wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, '//android.widget.TextView[@resource-id="in.startv.hotstar:id/tv_title" and @text="Search"]'))).focusandclick()
        search_bar = wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, '//android.widget.EditText[@resource-id="in.startv.hotstar:id/search_bar"]')))
        search_bar.send_keys("King and Conqueror")
        wait.until(EC.element_to_be_clickable((AppiumBy.ID, 'in.startv.hotstar:id/hero_img'))).focusandclick()
        wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, '//android.widget.TextView[@resource-id="in.startv.hotstar:id/textLabel"]'))).focusandclick()
        validate_psp_page_visible(wait)
        driver.press_keycode(KEYCODE_BACK)
        time.sleep(1)
        driver.press_keycode(KEYCODE_BACK)
        _open_side_nav(driver)


@allure.story("[Free User] As a Free user, I see PSP upon playing non-free content and see PSP page after completing 4hrs of free timer")
@allure.title("RL-T356")
def test_case_RLT356(driver_setup):
    driver, wait, video_wait = driver_setup
    free_phone, otp, hid = get_test_credentials("Free_Timer_Eligible_users_two")
    if not free_phone:
        pytest.fail("Failed to fetch Phone_Fresh credentials from API")

    reset_user_watch_time(hid, watch_time_ms=7134000)
    _login(driver, wait, free_phone, otp)

    wait.until(EC.visibility_of_element_located(HOME_LOCATOR))

    with allure.step("Search and play free content to trigger timer"):
        _open_side_nav(driver)
        wait.until(EC.element_to_be_clickable((AppiumBy.XPATH,
                                               '//android.widget.TextView[@resource-id="in.startv.hotstar:id/tv_title" and @text="Search"]'))).focusandclick()
        search_bar = wait.until(EC.element_to_be_clickable(
            (AppiumBy.XPATH, '//android.widget.EditText[@resource-id="in.startv.hotstar:id/search_bar"]')))
        search_bar.send_keys("Thaai Kizhavi")
        wait.until(EC.element_to_be_clickable(
            (AppiumBy.ID, 'in.startv.hotstar:id/hero_img'))).focusandclick()
        wait.until(EC.element_to_be_clickable(
            (AppiumBy.XPATH, '//android.widget.TextView[@resource-id="in.startv.hotstar:id/textLabel"]'))).focusandclick()

        time.sleep(20)  # wait for ad to finish

    with allure.step("Validate free timer is running"):
        timer_locator = (AppiumBy.XPATH, '//android.widget.TextView[@resource-id="in.startv.hotstar:id/tv_time"]')
        timer = wait.until(EC.visibility_of_element_located(timer_locator))
        assert timer is not None, "Timer is not available"

        time_1 = wait.until(EC.visibility_of_element_located(timer_locator)).text
        print(f"Initial timer value: {time_1}")
        time.sleep(5)
        time_2 = driver.find_element(*timer_locator).text
        print(f"Timer after 5s: {time_2}")
        assert time_1 != time_2, f"Timer is stuck at {time_1}. Video might not be playing."
        print("Timer is running — video playback confirmed")

    with allure.step("Wait for free timer expiry and validate PSP is shown"):
        try:
            sub_now = WebDriverWait(driver, 120).until(
                EC.presence_of_element_located((
                    AppiumBy.ID, 'in.startv.hotstar:id/tv_player_error_title'
                ))
            )
            print("Subscription prompt appeared after timer expiry")
        except Exception as e:
            print(f"Subscription prompt not found within timeout: {e}")

        validate_psp_page_visible(wait)
        driver.press_keycode(KEYCODE_BACK)
        time.sleep(2)
        driver.press_keycode(KEYCODE_BACK)
        time.sleep(2)
        driver.press_keycode(KEYCODE_BACK)

    with allure.step("Validate honeypot banner on Home after free timer expiry"):
        _open_side_nav(driver)
        wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, '//android.widget.TextView[@resource-id="in.startv.hotstar:id/tv_title" and @text="Home"]'))).focusandclick()
        time.sleep(6)
        driver.press_keycode(KEYCODE_DPAD_RIGHT)
        time.sleep(2)
        driver.press_keycode(KEYCODE_DPAD_DOWN)
        hp_banner = wait.until(
            EC.visibility_of_element_located((
                AppiumBy.XPATH,
                '//*[contains(@text, "Your free access is over") '
                'or contains(@text, "Plans starting at") '
                'or contains(@text, "Limited Time Offer") '
                'or contains(@text, "Your exclusive offer ends")]'
            ))
        )
        assert hp_banner is not None, "Honeypot banner is not displayed"
        print(f"Honeypot banner displayed: '{hp_banner.text}'")
        btn = wait.until(
            EC.element_to_be_clickable((
                AppiumBy.ID,
                "in.startv.hotstar:id/commn_primary_btn"
            ))
        )
        btn.focusandclick()
        validate_psp_page_visible(wait)


@allure.story("[Premium User] As a Premium user, playing a series from TV Submenu and seeing Binge Controls, Watch Next/MLT trays")
@allure.title("RL-T375")
def test_case_T375_4K_Seasons(driver_setup):
    """Validates 4K logos and season navigation on Android."""
    driver, wait, video_wait = driver_setup
    premium_phone, otp, hid = get_test_credentials("Phone_Smppremium")
    if not premium_phone:
        pytest.fail("Failed to fetch Phone_Premium credentials from API")

    _login(driver, wait, premium_phone, otp)
    _profile_onboarding(driver, wait)
    wait.until(EC.visibility_of_element_located(HOME_LOCATOR))
    _open_side_nav(driver)
    _validate_side_nav(wait)

    with allure.step("Search and start playback of 'Resort'"):
        wait.until(EC.element_to_be_clickable(
            (AppiumBy.ANDROID_UIAUTOMATOR,
             'new UiSelector().text("Search")'))).focusandclick()
        search_bar = wait.until(EC.element_to_be_clickable(
            (AppiumBy.XPATH, '//android.widget.EditText[@resource-id="in.startv.hotstar:id/search_bar"]')))
        search_bar.send_keys("Resort")
        wait.until(EC.element_to_be_clickable(
            (AppiumBy.ID, 'in.startv.hotstar:id/hero_img'))).focusandclick()
        wait.until(EC.element_to_be_clickable((AppiumBy.XPATH,
                                               "//*[contains(@text, 'Watch Latest Season') or "
                                               "contains(@text, 'Watch from Beginning') or "
                                               "contains(@text, 'Watch First Episode')]"))).focusandclick()
        try:
            skip_recap = driver.find_element(AppiumBy.XPATH, "//*[@text='Skip Recap' or @text='Skip Intro']")
            assert skip_recap.is_displayed(), "Skip Recap button was not visible"
            skip_recap.click()
        except Exception as e:
            print(f"Skip Recap/Intro not available: {e}")

    with allure.step("Validate Asli 4K quality selection and logo visibility"):
        try:
            time.sleep(8)
            driver.press_keycode(KEYCODE_DPAD_CENTER)
            time.sleep(2)
            driver.press_keycode(KEYCODE_DPAD_UP)

            quality_btn = wait.until(
                EC.element_to_be_clickable((AppiumBy.ANDROID_UIAUTOMATOR, 'new UiSelector().text("Quality")')))
            quality_btn.focusandclick()
            wait.until(
                EC.element_to_be_clickable((AppiumBy.ANDROID_UIAUTOMATOR, 'new UiSelector().text("Asli 4K")'))).click()
            time.sleep(5)
            asli_4k_logo = driver.find_element(AppiumBy.ID, 'in.startv.hotstar:id/lottie_asli_4k')
            assert asli_4k_logo.is_displayed(), "Asli 4K logo is not displayed after selection"
            print("Asli 4K logo confirmed visible")

            driver.press_keycode(KEYCODE_DPAD_CENTER)
            driver.press_keycode(KEYCODE_DPAD_UP)
            wait.until(
                EC.element_to_be_clickable((AppiumBy.ANDROID_UIAUTOMATOR, 'new UiSelector().text("Quality")'))).focusandclick()
            wait.until(
                EC.element_to_be_clickable((AppiumBy.ANDROID_UIAUTOMATOR, 'new UiSelector().text("Full HD")'))).click()
            time.sleep(5)
            logos = driver.find_elements(AppiumBy.ID, 'in.startv.hotstar:id/lottie_asli_4k')
            assert len(logos) == 0
            print("Asli 4K logo correctly absent after switching to Full HD")
        except Exception as e:
            print(f"4K quality check skipped — likely non-4K content or device: {e}")

    with allure.step("Validate Episodes tray and navigate to Next Episode"):
        time.sleep(10)
        driver.press_keycode(KEYCODE_DPAD_CENTER)
        time.sleep(2)
        driver.press_keycode(KEYCODE_DPAD_UP)
        ep_name_id = "in.startv.hotstar:id/tv_subtitle"
        current_episode_name = wait.until(
            EC.visibility_of_element_located((AppiumBy.ID, ep_name_id))
        ).text
        print(f"Current episode: {current_episode_name}")

        episodes_tray = wait.until(
            EC.visibility_of_element_located((AppiumBy.ANDROID_UIAUTOMATOR, 'new UiSelector().text("Episodes")')))
        assert episodes_tray.is_displayed(), "Episodes tray is not visible"

        try:
            driver.press_keycode(KEYCODE_DPAD_DOWN)
            wait.until(EC.element_to_be_clickable((AppiumBy.ANDROID_UIAUTOMATOR, 'new UiSelector().text("Next Episode")'))).focusandclick()
            driver.press_keycode(KEYCODE_DPAD_UP)
            wait.until(EC.presence_of_element_located((AppiumBy.ID, ep_name_id)))
            next_episode_name = driver.find_element(AppiumBy.ID, ep_name_id).text
            print(f"Next episode: {next_episode_name}")
            assert current_episode_name != next_episode_name, f"Episode did not change. Still on: {current_episode_name}"
            print("Episode navigation successful")
        except Exception as e:
            print(f"Next Episode not available — likely last episode: {e}")

    driver.press_keycode(KEYCODE_BACK)
    time.sleep(2)
    driver.press_keycode(KEYCODE_BACK)
    time.sleep(2)
    driver.press_keycode(KEYCODE_BACK)
    _open_side_nav(driver)

    with allure.step("Switch to Kids profile and validate 4K playback"):
        _switching_to_kids(driver, wait)
        driver.press_keycode(KEYCODE_DPAD_LEFT)

        wait.until(EC.element_to_be_clickable(
            (AppiumBy.ANDROID_UIAUTOMATOR, 'new UiSelector().className("android.view.ViewGroup").instance(2)'))).focusandclick()
        search_btn = wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, '//android.widget.EditText[@resource-id="in.startv.hotstar:id/search_bar"]')))
        search_btn.send_keys("How To Train Your Dragon")

        wait.until(EC.element_to_be_clickable(
            (AppiumBy.ID, 'in.startv.hotstar:id/hero_img'))).focusandclick()
        wait.until(EC.element_to_be_clickable(
            (AppiumBy.XPATH, "//android.widget.TextView[@text='Watch Now' or @text='Watch from Beginning']/.."))).focusandclick()
        time.sleep(15)

        driver.press_keycode(KEYCODE_DPAD_CENTER)
        time.sleep(2)
        driver.press_keycode(KEYCODE_DPAD_UP)
        wait.until(EC.element_to_be_clickable((AppiumBy.ANDROID_UIAUTOMATOR, 'new UiSelector().text("Quality")'))).focusandclick()
        wait.until(EC.element_to_be_clickable((AppiumBy.ANDROID_UIAUTOMATOR, 'new UiSelector().text("Asli 4K")'))).click()
        time.sleep(10)
        asli_4k_logo = wait.until(EC.element_to_be_clickable((AppiumBy.ID, 'in.startv.hotstar:id/lottie_asli_4k')))
        assert asli_4k_logo.is_displayed(), "Asli 4K logo is not displayed after selection in Kids profile"
        print("Asli 4K confirmed in Kids profile")

    driver.press_keycode(KEYCODE_BACK)
    time.sleep(2)
    driver.press_keycode(KEYCODE_BACK)
    _open_side_nav(driver)
    _Switching_back_to_main_profile(driver, wait)


@allure.story("[Free User] Verify trailer auto-play based on LPV, static paywall on KIDS profile, and PhonePe QR scan")
@allure.title("RL-T357")
def test_case_T357_Kids_Restrictions(driver_setup):
    """Validates restrictions and trailers in Kids profile on Android."""
    driver, wait, _ = driver_setup
    phone_free, otp, hid = get_test_credentials("Free_Timer_Eligible_users_two")
    if not phone_free:
        pytest.fail("Failed to fetch Phone_Fresh credentials from API")

    reset_user_watch_time(hid, watch_time_ms=74440000)
    _login(driver, wait, phone_free, otp)
    _profile_onboarding(driver, wait)
    _open_side_nav(driver)

    with allure.step("Search content and validate trailer auto-play with language switch"):
        wait.until(EC.element_to_be_clickable((AppiumBy.XPATH,
                                               '//android.widget.TextView[@resource-id="in.startv.hotstar:id/tv_title" and @text="Search"]'))).focusandclick()
        search_bar = wait.until(EC.element_to_be_clickable(
            (AppiumBy.XPATH, '//android.widget.EditText[@resource-id="in.startv.hotstar:id/search_bar"]')))
        search_bar.send_keys("Sarvam Maya")
        wait.until(EC.element_to_be_clickable(
            (AppiumBy.ID, 'in.startv.hotstar:id/hero_img'))).focusandclick()

        try:
            time.sleep(6)
            trailer_element = '//android.widget.FrameLayout[@resource-id="in.startv.hotstar:id/media_content_container"]'
            wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, trailer_element)))
            languages = wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//android.widget.TextView[contains(@text, "Languages")]')))
            total_language = 0
            if len(languages) > 0:
                language_text = languages[0].text
                digit_as_str = language_text.split()[0]
                total_language = int(digit_as_str)
            random_index = random.randint(1, total_language)
            print(f"Switching to language index {random_index} of {total_language}")
            language_switch = f"(//androidx.recyclerview.widget.RecyclerView[@resource-id='in.startv.hotstar:id/languages']//android.widget.TextView)[{random_index}]"
            wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, language_switch))).click()
            error_msg = driver.find_elements(AppiumBy.XPATH, "//*[contains(@text,'Trailer is unavailable')]")
            if len(error_msg) > 0:
                assert error_msg[0].is_displayed()
                print("Trailer unavailable message shown for selected language")
            else:
                wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, trailer_element)))
                print("Trailer loaded successfully for selected language")
        except Exception as e:
            print(f"Trailer validation skipped: {e}")

    driver.press_keycode(KEYCODE_BACK)

    with allure.step("Switch to Kids profile and validate static paywall on premium content"):
        _open_side_nav(driver)
        _switching_to_kids(driver, wait)
        _open_side_nav(driver)
        wait.until(EC.element_to_be_clickable(
            (AppiumBy.ANDROID_UIAUTOMATOR,
             'new UiSelector().className("android.view.ViewGroup").instance(2)'))).focusandclick()
        search_btn = wait.until(EC.element_to_be_clickable(
            (AppiumBy.XPATH, '//android.widget.EditText[@resource-id="in.startv.hotstar:id/search_bar"]')))
        search_btn.send_keys("How To Train Your Dragon")
        wait.until(EC.element_to_be_clickable(
            (AppiumBy.ID, 'in.startv.hotstar:id/hero_img'))).focusandclick()
        wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, "//*[@text='Subscribe to Watch' or @text='Upgrade to Watch']"))).focusandclick()
        validate_psp_page_visible(wait)
        print("PSP correctly shown for premium content in Kids profile")
        driver.press_keycode(KEYCODE_BACK)
        time.sleep(2)
        driver.press_keycode(KEYCODE_BACK)
        time.sleep(1)
        driver.press_keycode(KEYCODE_BACK)

    _Switching_back_to_main_profile(driver, wait)


@allure.story("[Premium User] Verify a Premium User is able to login, search content, play it, and logout")
@allure.title("RL-T1488")
def test_case_T1488_watch_movie(driver_setup):
    driver, wait, video_wait = driver_setup
    phone_premium, otp, hid = get_test_credentials("Phone_Smppremium")
    if not phone_premium:
        pytest.fail("Failed to fetch Phone_Premium credentials from API")

    _login(driver, wait, phone_premium, otp)
    _profile_onboarding(driver, wait)
    _verify_home_scroll(driver, wait)
    _open_side_nav(driver)
    _validate_side_nav(wait)

    with allure.step("Navigate to Search"):
        wait.until(EC.element_to_be_clickable(
            (AppiumBy.ANDROID_UIAUTOMATOR,
             'new UiSelector().text("Search")'))).focusandclick()

    with allure.step("Search and open 'How To Train Your Dragon'"):
        search_btn = wait.until(EC.element_to_be_clickable(
            (AppiumBy.XPATH, '//android.widget.EditText[@resource-id="in.startv.hotstar:id/search_bar"]')))
        search_btn.send_keys("How To Train Your Dragon")
        wait.until(EC.element_to_be_clickable(
            (AppiumBy.ID,
             'in.startv.hotstar:id/hero_img'))).focusandclick()

    with allure.step("Start Playback"):
        watch_btn = wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, '//*[@text="Watch from Beginning" or @text="Watch Now" or @text="Watch Latest Season" or @text="Watch First Episode"]')))
        watch_btn.focusandclick()
        assert watch_btn is not None, "Watch button not available"

    with allure.step("Wait for video to load"):
        SPINNER_XPATH = '//*[@resource-id="in.startv.hotstar:id/loader"]'
        video_wait.until(EC.invisibility_of_element_located((AppiumBy.XPATH, SPINNER_XPATH)))
        print("Video loaded — spinner gone")

    with allure.step("Change quality to Full HD and verify"):
        time.sleep(25)
        driver.press_keycode(85)
        driver.press_keycode(KEYCODE_DPAD_UP)
        video_wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//*[@text="Quality"]')))

        wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, '//*[@text="Quality"]'))).focusandclick()
        wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, '//*[@text="Full HD"]'))).click()
        print("Quality set to Full HD")
        time.sleep(5)

    with allure.step("Switch audio to Tamil and then to English [CC]"):
        driver.press_keycode(85)
        driver.press_keycode(KEYCODE_DPAD_UP)
        wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, '//*[@text="Audio & Subtitles"]'))).focusandclick()
        wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, '//*[@text="Tamil"]'))).click()
        print("Audio switched to Tamil")
        time.sleep(5)

        driver.press_keycode(85)
        driver.press_keycode(KEYCODE_DPAD_UP)
        wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, '//*[@text="Audio & Subtitles"]'))).focusandclick()
        wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, '//*[@text="English [CC]"]'))).click()
        print("Audio switched to English [CC]")

    with allure.step("Play for 15s, exit player, and logout"):
        time.sleep(15)
        driver.press_keycode(KEYCODE_BACK)
        driver.press_keycode(KEYCODE_BACK)
        _open_side_nav(driver)
        wait.until(
            EC.element_to_be_clickable((AppiumBy.ANDROID_UIAUTOMATOR, 'new UiSelector().text("My Space")'))).focusandclick()
        wait.until(EC.element_to_be_clickable((AppiumBy.ID, 'in.startv.hotstar:id/btn_help_settings_cta'))).focusandclick()
        wait.until(EC.element_to_be_clickable((AppiumBy.ID, 'in.startv.hotstar:id/btn_logout'))).focusandclick()
        wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, '//*[@text="Log Out"]'))).click()
        print("User logged out successfully")

# @allure.story("[Fresh User] Verify a Fresh User is able to Login and browse the app, verify Click on Subscribe CTA in Home Page & myspace")
# @allure.title("RL-T1487")
# def test_case_RLT1487(driver_setup):
#     driver, wait, _ = driver_setup
#     fresh_phone, fresh_otp, fresh_hid = get_test_credentials("Phone_Fresh_User")
#
#     if not fresh_phone:
#         pytest.fail("Failed to fetch Phone_Fresh credentials from API")
#
#     _login(driver, wait, fresh_phone, fresh_otp)
#     _create_profile(driver, wait)
#     wait.until(EC.visibility_of_element_located(HOME_LOCATOR))
#     _verify_home_scroll(driver, wait)
#     _open_side_nav(driver)
#     _validate_side_nav(wait)
#
#     with allure.step("Tap on Subscribe in My Space"):
#         wait.until(EC.element_to_be_clickable((AppiumBy.ANDROID_UIAUTOMATOR, 'new UiSelector().text("My Space")'))).focusandclick()
#         wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, '//android.view.ViewGroup[@resource-id="in.startv.hotstar:id/btn_cta"]'))).focusandclick()
#         validate_psp_page_visible(wait)
#         driver.press_keycode(KEYCODE_BACK)
#
#     with allure.step("Try to play any content"):
#         _open_side_nav(driver)
#         wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, '//android.widget.TextView[@resource-id="in.startv.hotstar:id/tv_title" and @text="Search"]'))).focusandclick()
#         search_bar = wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, '//android.widget.EditText[@resource-id="in.startv.hotstar:id/search_bar"]')))
#         search_bar.send_keys("King and Conqueror")
#         wait.until(EC.element_to_be_clickable((AppiumBy.ID, 'in.startv.hotstar:id/hero_img'))).focusandclick()
#         wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, '//android.widget.TextView[@resource-id="in.startv.hotstar:id/textLabel"]'))).focusandclick()
#         validate_psp_page_visible(wait)
#         driver.press_keycode(KEYCODE_BACK)
#         time.sleep(1)
#         driver.press_keycode(KEYCODE_BACK)
#         _open_side_nav(driver)
#
#
# @allure.story("[Free User] As a Free user, I see PSP upon playing non-free content and see PSP page after completing 4hrs of free timer")
# @allure.title("RL-T356")
# def test_case_RLT356(driver_setup):
#     driver, wait, video_wait = driver_setup
#     free_phone, otp, hid = get_test_credentials("Free_Timer_Eligible_users_two")
#     if not free_phone:
#         pytest.fail("Failed to fetch Phone_Fresh credentials from API")
#
#     reset_user_watch_time(hid, watch_time_ms=7134000)
#     _login(driver, wait, free_phone, otp)
#     # _profile_onboarding(driver, wait)
#
#     wait.until(EC.visibility_of_element_located(HOME_LOCATOR))
#     _open_side_nav(driver)
#     wait.until(EC.element_to_be_clickable((AppiumBy.XPATH,
#                                            '//android.widget.TextView[@resource-id="in.startv.hotstar:id/tv_title" and @text="Search"]'))).focusandclick()
#     search_bar = wait.until(EC.element_to_be_clickable(
#         (AppiumBy.XPATH, '//android.widget.EditText[@resource-id="in.startv.hotstar:id/search_bar"]')))
#     search_bar.send_keys("Thaai Kizhavi")
#     wait.until(EC.element_to_be_clickable(
#         (AppiumBy.ID, 'in.startv.hotstar:id/hero_img'))).focusandclick()
#     wait.until(EC.element_to_be_clickable(
#         (AppiumBy.XPATH, '//android.widget.TextView[@resource-id="in.startv.hotstar:id/textLabel"]'))).focusandclick()
#
#     time.sleep(20) #ad
#
#     timer_locator = (AppiumBy.XPATH, '//android.widget.TextView[@resource-id="in.startv.hotstar:id/tv_time"]')
#     timer = wait.until(EC.visibility_of_element_located(timer_locator))
#     assert timer is not None, "Timer is not available"
#     print("Timer is available")
#
#     time_1 = wait.until(EC.visibility_of_element_located(timer_locator)).text
#     print(f"Initial time: {time_1}")
#     time.sleep(5)
#     time_2 = driver.find_element(*timer_locator).text
#     print(f"Time after 5s: {time_2}")
#     assert time_1 != time_2, f"Timer is stuck at {time_1}. Video might not be playing."
#     print("Validation Successful: Timer is running.")
#
#     try:
#         sub_now = WebDriverWait(driver, 120).until(
#             EC.presence_of_element_located((
#                 AppiumBy.ID, 'in.startv.hotstar:id/tv_player_error_title'
#             ))
#         )
#         print("subs page is found")
#
#     except Exception as e:
#         print("Element not found:", e)
#
#     validate_psp_page_visible(wait)
#     driver.press_keycode(KEYCODE_BACK)
#     time.sleep(2)
#     driver.press_keycode(KEYCODE_BACK)
#     time.sleep(2)
#     driver.press_keycode(KEYCODE_BACK)
#
#     _open_side_nav(driver)
#     wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, '//android.widget.TextView[@resource-id="in.startv.hotstar:id/tv_title" and @text="Home"]'))).focusandclick()
#     time.sleep(6)
#     driver.press_keycode(KEYCODE_DPAD_RIGHT)
#     driver.press_keycode(KEYCODE_DPAD_DOWN)
#     hp_banner = wait.until(
#         EC.visibility_of_element_located((
#             AppiumBy.XPATH,
#             '//*[contains(@text, "Your free access is over") '
#             'or contains(@text, "Plans starting at") '
#             'or contains(@text, "Limited Time Offer") '
#             'or contains(@text, "Your exclusive offer ends")]'
#         ))
#     )
#     assert hp_banner is not None, "Honeypot banner is not displayed"
#     print("Honeypot banner is displayed")
#     btn = wait.until(
#         EC.element_to_be_clickable((
#             AppiumBy.ID,
#             "in.startv.hotstar:id/commn_primary_btn"
#         ))
#     )
#     btn.focusandclick()
#     validate_psp_page_visible(wait)
#
# @allure.story("[Premium User] As a Premium user, playing a series from TV Submenu and seeing Binge Controls, Watch Next/MLT trays")
# @allure.title("RL-T375")
# def test_case_T375_4K_Seasons(driver_setup):
#     """Validates 4K logos and season navigation on Android."""
#     driver, wait, video_wait = driver_setup
#     premium_phone, otp, hid = get_test_credentials("Phone_Smppremium")
#     if not premium_phone:
#         pytest.fail("Failed to fetch Phone_Premium credentials from API")
#
#     _login(driver, wait, premium_phone, otp)
#     _profile_onboarding(driver, wait)
#     wait.until(EC.visibility_of_element_located(HOME_LOCATOR))
#     _open_side_nav(driver)
#     _validate_side_nav(wait)
#     wait.until(EC.element_to_be_clickable(
#         (AppiumBy.ANDROID_UIAUTOMATOR,
#          'new UiSelector().text("Search")'))).focusandclick()
#     search_bar = wait.until(EC.element_to_be_clickable(
#         (AppiumBy.XPATH, '//android.widget.EditText[@resource-id="in.startv.hotstar:id/search_bar"]')))
#     search_bar.send_keys("Resort")
#     wait.until(EC.element_to_be_clickable(
#         (AppiumBy.ID, 'in.startv.hotstar:id/hero_img'))).focusandclick()
#     wait.until(EC.element_to_be_clickable((AppiumBy.XPATH,
#                                            "//*[contains(@text, 'Watch Latest Season') or "
#                                            "contains(@text, 'Watch from Beginning') or "
#                                            "contains(@text, 'Watch First Episode')]"))).focusandclick()
#     try:
#         skip_recap = driver.find_element(AppiumBy.XPATH, "//*[@text='Skip Recap' or @text='Skip Intro']")
#         assert skip_recap.is_displayed(), "Skip Recap button was not visible"
#         skip_recap.click()
#     except Exception as e:
#         print(f"Recap is not available: {e}")
#
#     try:
#         time.sleep(8)
#         driver.press_keycode(KEYCODE_DPAD_CENTER)
#         time.sleep(2)
#         driver.press_keycode(KEYCODE_DPAD_UP)
#
#         quality_btn = wait.until(
#             EC.element_to_be_clickable((AppiumBy.ANDROID_UIAUTOMATOR, 'new UiSelector().text("Quality")')))
#         quality_btn.focusandclick()
#         wait.until(
#             EC.element_to_be_clickable((AppiumBy.ANDROID_UIAUTOMATOR, 'new UiSelector().text("Asli 4K")'))).click()
#         time.sleep(5)
#         asli_4k_logo = driver.find_element(AppiumBy.ID, 'in.startv.hotstar:id/lottie_asli_4k')
#         assert asli_4k_logo.is_displayed(), "Asli 4K logo is not displayed after selection"
#
#         driver.press_keycode(KEYCODE_DPAD_CENTER)
#         driver.press_keycode(KEYCODE_DPAD_UP)
#         wait.until(
#             EC.element_to_be_clickable((AppiumBy.ANDROID_UIAUTOMATOR, 'new UiSelector().text("Quality")'))).focusandclick()
#         wait.until(
#             EC.element_to_be_clickable((AppiumBy.ANDROID_UIAUTOMATOR, 'new UiSelector().text("Full HD")'))).click()
#         time.sleep(5)
#         logos = driver.find_elements(AppiumBy.ID, 'in.startv.hotstar:id/lottie_asli_4k')
#         assert len(logos) == 0
#     except Exception as e:
#         print(f"T375 Quality change failed, seems a Non-4K Content or Device: {e}")
#
#     time.sleep(10)
#     driver.press_keycode(KEYCODE_DPAD_CENTER)
#     time.sleep(2)
#     driver.press_keycode(KEYCODE_DPAD_UP)
#     ep_name_id = "in.startv.hotstar:id/tv_subtitle"
#     current_episode_name = wait.until(
#         EC.visibility_of_element_located((AppiumBy.ID, ep_name_id))
#     ).text
#     print(current_episode_name)
#     episodes_tray = wait.until(
#         EC.visibility_of_element_located((AppiumBy.ANDROID_UIAUTOMATOR, 'new UiSelector().text("Episodes")')))
#     assert episodes_tray.is_displayed(), "Episodes tray is not visible"
#
#     # _background_and_reopen_validate(driver)
#
#     try:
#         driver.press_keycode(KEYCODE_DPAD_DOWN)
#         wait.until(EC.element_to_be_clickable((AppiumBy.ANDROID_UIAUTOMATOR, 'new UiSelector().text("Next Episode")'))).focusandclick()
#         # time.sleep(15)
#         # driver.press_keycode(KEYCODE_DPAD_CENTER)
#         driver.press_keycode(KEYCODE_DPAD_UP)
#         wait.until(EC.presence_of_element_located((AppiumBy.ID, ep_name_id)))
#         next_episode_name = driver.find_element(AppiumBy.ID, ep_name_id).text
#         print(f"{next_episode_name}")
#         assert current_episode_name != next_episode_name, f"Episode name did not change! Still: {current_episode_name}"
#     except Exception as e:
#         print("Seems it's the last episode.")
#
#
#     driver.press_keycode(KEYCODE_BACK)
#     time.sleep(2)
#     driver.press_keycode(KEYCODE_BACK)
#     time.sleep(2)
#     driver.press_keycode(KEYCODE_BACK)
#     _open_side_nav(driver)
#
#     _switching_to_kids(driver, wait)
#     driver.press_keycode(KEYCODE_DPAD_LEFT)
#
#     wait.until(EC.element_to_be_clickable(
#         (AppiumBy.ANDROID_UIAUTOMATOR, 'new UiSelector().className("android.view.ViewGroup").instance(2)'))).focusandclick()
#     search_btn = wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, '//android.widget.EditText[@resource-id="in.startv.hotstar:id/search_bar"]')))
#     search_btn.send_keys("How To Train Your Dragon")
#
#     wait.until(EC.element_to_be_clickable(
#         (AppiumBy.ID, 'in.startv.hotstar:id/hero_img'))).focusandclick()
#     wait.until(EC.element_to_be_clickable(
#         (AppiumBy.XPATH, "//android.widget.TextView[@text='Watch Now' or @text='Watch from Beginning']/.."))).focusandclick()
#     time.sleep(15)
#
#     driver.press_keycode(KEYCODE_DPAD_CENTER)
#     time.sleep(2)
#     driver.press_keycode(KEYCODE_DPAD_UP)
#     wait.until(EC.element_to_be_clickable((AppiumBy.ANDROID_UIAUTOMATOR, 'new UiSelector().text("Quality")'))).focusandclick()
#     wait.until(EC.element_to_be_clickable((AppiumBy.ANDROID_UIAUTOMATOR, 'new UiSelector().text("Asli 4K")'))).click()
#     time.sleep(10)
#     asli_4k_logo = wait.until(EC.element_to_be_clickable((AppiumBy.ID, 'in.startv.hotstar:id/lottie_asli_4k')))
#     assert asli_4k_logo.is_displayed(), "Asli 4K logo is not displayed after selection"
#
#     driver.press_keycode(KEYCODE_BACK)
#     time.sleep(2)
#     driver.press_keycode(KEYCODE_BACK)
#     _open_side_nav(driver)
#     _Switching_back_to_main_profile(driver, wait)
#
#
# @allure.story("[Free User] Verify trailer auto-play based on LPV, static paywall on KIDS profile, and PhonePe QR scan")
# @allure.title("RL-T357")
# def test_case_T357_Kids_Restrictions(driver_setup):
#     """Validates restrictions and trailers in Kids profile on Android."""
#     driver, wait, _ = driver_setup
#     phone_free, otp, hid = get_test_credentials("Free_Timer_Eligible_users_two")
#     if not phone_free:
#         pytest.fail("Failed to fetch Phone_Fresh credentials from API")
#
#     reset_user_watch_time(hid, watch_time_ms=74440000)
#     _login(driver, wait, phone_free, otp)
#     _profile_onboarding(driver, wait)
#
#     _open_side_nav(driver)
#
#     wait.until(EC.element_to_be_clickable((AppiumBy.XPATH,
#                                            '//android.widget.TextView[@resource-id="in.startv.hotstar:id/tv_title" and @text="Search"]'))).focusandclick()
#     search_bar = wait.until(EC.element_to_be_clickable(
#         (AppiumBy.XPATH, '//android.widget.EditText[@resource-id="in.startv.hotstar:id/search_bar"]')))
#     search_bar.send_keys("Sarvam Maya")
#     wait.until(EC.element_to_be_clickable(
#         (AppiumBy.ID, 'in.startv.hotstar:id/hero_img'))).focusandclick()
#
#     try:
#         time.sleep(6)
#         trailer_element = '//android.widget.FrameLayout[@resource-id="in.startv.hotstar:id/media_content_container"]'  #element need to check
#         wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, trailer_element)))
#         languages = wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//android.widget.TextView[contains(@text, "Languages")]')))
#         total_language = 0
#         if len(languages) > 0:
#             language_text = languages[0].text
#             digit_as_str = language_text.split()[0]
#             total_language = int(digit_as_str)
#         random_index = random.randint(1, total_language)
#         language_switch = f"(//androidx.recyclerview.widget.RecyclerView[@resource-id='in.startv.hotstar:id/languages']//android.widget.TextView)[{random_index}]"
#         wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, language_switch))).click()
#         error_msg = driver.find_elements(AppiumBy.XPATH, "//*[contains(@text,'Trailer is unavailable')]")
#         if len(error_msg) > 0:
#             assert error_msg[0].is_displayed()
#         else:
#             wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, trailer_element)))
#     except Exception as e:
#         print(f"Trailer not available: {e}")
#
#     driver.press_keycode(KEYCODE_BACK)
#
#     _open_side_nav(driver)
#     _switching_to_kids(driver, wait)
#     _open_side_nav(driver)
#     wait.until(EC.element_to_be_clickable(
#         (AppiumBy.ANDROID_UIAUTOMATOR,
#          'new UiSelector().className("android.view.ViewGroup").instance(2)'))).focusandclick()
#     search_btn = wait.until(EC.element_to_be_clickable(
#         (AppiumBy.XPATH, '//android.widget.EditText[@resource-id="in.startv.hotstar:id/search_bar"]')))
#     search_btn.send_keys("How To Train Your Dragon")
#     wait.until(EC.element_to_be_clickable(
#         (AppiumBy.ID, 'in.startv.hotstar:id/hero_img'))).focusandclick()
#     wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, "//*[@text='Subscribe to Watch' or @text='Upgrade to Watch']"))).focusandclick()
#     validate_psp_page_visible(wait)
#     driver.press_keycode(KEYCODE_BACK)  # to PSP
#     time.sleep(2)
#     driver.press_keycode(KEYCODE_BACK)  # to details page
#     time.sleep(1)
#     driver.press_keycode(KEYCODE_BACK)
#     _Switching_back_to_main_profile(driver, wait)
#
#
# @allure.story("[Premium User] Verify a Premium User is able to login, search content, play it, and logout")
# @allure.title("RL-T1488")
# def test_case_T1488_watch_movie(driver_setup):
#     driver, wait, video_wait = driver_setup
#     phone_premium, otp, hid = get_test_credentials("Phone_Smppremium")
#     if not phone_premium:
#         pytest.fail("Failed to fetch Phone_Premium credentials from API")
#
#     _login(driver, wait, phone_premium, otp)
#     _profile_onboarding(driver, wait)
#     _verify_home_scroll(driver, wait)
#     _open_side_nav(driver)
#     _validate_side_nav(wait)
#
#     with allure.step("Navigate to Search"):
#         wait.until(EC.element_to_be_clickable(
#             (AppiumBy.ANDROID_UIAUTOMATOR,
#              'new UiSelector().text("Search")'))).focusandclick()
#
#     with allure.step("Select Search Result"):
#         search_btn = wait.until(EC.element_to_be_clickable(
#             (AppiumBy.XPATH, '//android.widget.EditText[@resource-id="in.startv.hotstar:id/search_bar"]')))
#         search_btn.send_keys("How To Train Your Dragon")
#         wait.until(EC.element_to_be_clickable(
#             (AppiumBy.ID,
#              'in.startv.hotstar:id/hero_img'))).focusandclick()
#
#     with allure.step("Start Playback"):
#         watch_btn = wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, '//*[@text="Watch from Beginning" or @text="Watch Now" or @text="Watch Latest Season" or @text="Watch First Episode"]')))
#         watch_btn.focusandclick()
#         assert watch_btn is not None, "Watch button not available"
#
#     with allure.step("Wait for Video Playback to Start"):
#         SPINNER_XPATH = '//*[@resource-id="in.startv.hotstar:id/loader"]'
#         video_wait.until(EC.invisibility_of_element_located((AppiumBy.XPATH, SPINNER_XPATH)))
#
#     with allure.step("Modify Video Quality and Audio/Subtitles"):
#         time.sleep(25)
#         driver.press_keycode(85)
#         driver.press_keycode(KEYCODE_DPAD_UP)
#         video_wait.until(EC.visibility_of_element_located((AppiumBy.XPATH, '//*[@text="Quality"]')))
#
#         wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, '//*[@text="Quality"]'))).focusandclick()
#         wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, '//*[@text="Full HD"]'))).click()
#
#         time.sleep(5)
#         driver.press_keycode(85)
#         driver.press_keycode(KEYCODE_DPAD_UP)
#         wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, '//*[@text="Audio & Subtitles"]'))).focusandclick()
#         wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, '//*[@text="Tamil"]'))).click()
#         time.sleep(5)
#
#         driver.press_keycode(85)
#         driver.press_keycode(KEYCODE_DPAD_UP)
#         wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, '//*[@text="Audio & Subtitles"]'))).focusandclick()
#         wait.until(EC.element_to_be_clickable((AppiumBy.XPATH, '//*[@text="English [CC]"]'))).click()
#         # driver.press_keycode(KEYCODE_BACK)
#
#     with allure.step("Play for 10 seconds and Exit"):
#         print("Playing with new settings for 10 seconds...")
#         time.sleep(15)
#         driver.press_keycode(KEYCODE_BACK)   # Exit player
#         driver.press_keycode(KEYCODE_BACK)   # Exit Details page
#         _open_side_nav(driver)
#         wait.until(
#             EC.element_to_be_clickable((AppiumBy.ANDROID_UIAUTOMATOR, 'new UiSelector().text("My Space")'))).focusandclick()
#         wait.until(EC.element_to_be_clickable((AppiumBy.ID,'in.startv.hotstar:id/btn_help_settings_cta'))).focusandclick()
#         wait.until(EC.element_to_be_clickable((AppiumBy.ID,'in.startv.hotstar:id/btn_logout'))).focusandclick()
#         wait.until(EC.element_to_be_clickable((AppiumBy.XPATH,'//*[@text="Log Out"]'))).click()
