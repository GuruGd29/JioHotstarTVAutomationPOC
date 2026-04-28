from appium.webdriver.webelement import WebElement

def focusandclick(self):
    driver = self.parent
    self.click()
    driver.press_keycode(23)

WebElement.focusandclick = focusandclick