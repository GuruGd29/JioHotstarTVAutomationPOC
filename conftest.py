import pytest
import allure
import os

@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()

    if report.when in ["setup", "call"] and report.failed:
        driver = item.funcargs.get("driver_setup")

        if driver:
            if isinstance(driver, tuple):
                driver = driver[0]

            try:
                screenshot = driver.get_screenshot_as_png()

                allure.attach(
                    screenshot,
                    name="failure_screenshot",
                    attachment_type=allure.attachment_type.PNG
                )

                os.makedirs("screenshots", exist_ok=True)
                path = f"screenshots/{item.name}.png"
                driver.save_screenshot(path)

                print(f"Screenshot saved: {path}")

            except Exception as e:
                print(f"Screenshot capture failed: {e}")