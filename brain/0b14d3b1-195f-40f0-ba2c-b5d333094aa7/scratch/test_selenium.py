from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import time

def test_selenium():
    print("Testing Selenium...")
    try:
        chrome_options = Options()
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--no-sandbox')
        
        driver = webdriver.Chrome(options=chrome_options)
        print("Driver initialized successfully.")
        
        url = "https://www.google.com"
        print(f"Loading {url}...")
        driver.get(url)
        print(f"Page title: {driver.title}")
        
        driver.quit()
        print("Success!")
    except Exception as e:
        print(f"Failed: {e}")

if __name__ == "__main__":
    test_selenium()
