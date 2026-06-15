import time
from playwright.sync_api import sync_playwright

def log_url(frame):
    # This event triggers every time a page changes its URL
    print(f"[Tracked URL] {frame.url}")

def main():
    with sync_playwright() as p:
        # Launch visible browser (headed mode)
        browser = p.firefox.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()

        # Listen for any navigation events across the browser session
        page.on("framenavigated", log_url)

        # Start with an initial webpage
        print("Browser started. Navigate anywhere to see tracking in action...")
        page.goto("https://wikipedia.org")

        # Keep the script running to track your manual browsing activity
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nTracking stopped.")
            browser.close()

if __name__ == "__main__":
    main()
