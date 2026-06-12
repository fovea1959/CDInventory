import logging

from playwright.sync_api import sync_playwright


def track_urls(start_url):
    with (sync_playwright() as p):
        # 1. Spawn a visible browser
        browser = p.chromium.launch_persistent_context(user_data_dir="chromium_user_data", headless=False)
        page = browser.new_page()
        context = page.context
        page_or_context = page

        # Track all network requests made by the page
        def on_request(request):
            logging.debug(f"Request: {request.method} -> {request.url}")

        page_or_context.on("request", on_request)

        # "framenavigated" to reliably capture full page transitions on MusicBrainz
        def on_navigation(frame):
            logging.info(f"Navigated to: {frame.url}")

        page_or_context.on("framenavigated", on_navigation)

        # 4. Open the initial URL
        logging.info(f"Spawning browser for: {start_url}")
        try:
            page.goto(start_url)
            while not page.is_closed():
                page.wait_for_timeout(1000)

        except Exception as e:
            logging.error(f"An error occurred: {e}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    track_urls("https://musicbrainz.org")
