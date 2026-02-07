#!/usr/bin/env python3
"""Screenshot Capture Script for Medical KAG Web UI.

Captures screenshots of all pages for documentation.

Requirements:
    pip install playwright
    playwright install chromium

Usage:
    1. Start the Streamlit app first:
       streamlit run web/app.py

    2. Run this script:
       python scripts/capture_screenshots.py
"""

import asyncio
import os
import sys
from pathlib import Path

# Check if playwright is available
try:
    from playwright.async_api import async_playwright
except ImportError:
    print("Playwright not installed. Install with:")
    print("  pip install playwright")
    print("  playwright install chromium")
    sys.exit(1)


# Configuration
BASE_URL = "http://localhost:8501"
SCREENSHOT_DIR = Path(__file__).parent.parent / "docs" / "screenshots"

# Pages to capture
PAGES = [
    {
        "name": "01_home",
        "url": "/",
        "title": "Home - Main Dashboard",
        "wait_for": "text=Medical KAG",
    },
    {
        "name": "02_documents",
        "url": "/Documents",
        "title": "Documents - PDF Management",
        "wait_for": "text=Documents",
    },
    {
        "name": "03_search",
        "url": "/Search",
        "title": "Search - Medical Literature Search",
        "wait_for": "text=Search",
    },
    {
        "name": "04_knowledge_graph",
        "url": "/Knowledge_Graph",
        "title": "Knowledge Graph - Paper Relations",
        "wait_for": "text=Knowledge Graph",
    },
    {
        "name": "05_draft_assistant",
        "url": "/Draft_Assistant",
        "title": "Draft Assistant - Writing Support",
        "wait_for": "text=Draft",
    },
    {
        "name": "06_settings",
        "url": "/Settings",
        "title": "Settings - System Configuration",
        "wait_for": "text=Settings",
    },
]


async def capture_screenshots():
    """Capture screenshots of all pages."""
    # Ensure screenshot directory exists
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Saving screenshots to: {SCREENSHOT_DIR}")
    print("-" * 50)

    async with async_playwright() as p:
        # Launch browser
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            device_scale_factor=2,  # Retina quality
        )
        page = await context.new_page()

        # Check if server is running
        try:
            await page.goto(BASE_URL, timeout=5000)
        except Exception:
            print(f"Error: Cannot connect to {BASE_URL}")
            print("Please start the Streamlit app first:")
            print("  streamlit run web/app.py")
            await browser.close()
            return False

        # Wait for Streamlit to fully load
        await page.wait_for_timeout(2000)

        captured = []

        for page_info in PAGES:
            name = page_info["name"]
            url = page_info["url"]
            title = page_info["title"]
            wait_for = page_info.get("wait_for")

            print(f"Capturing: {title}...")

            try:
                # Navigate to page
                full_url = f"{BASE_URL}{url}"
                await page.goto(full_url)

                # Wait for content
                if wait_for:
                    try:
                        await page.wait_for_selector(wait_for, timeout=10000)
                    except Exception:
                        print(f"  Warning: Could not find '{wait_for}', capturing anyway")

                # Additional wait for dynamic content
                await page.wait_for_timeout(2000)

                # Capture screenshot
                screenshot_path = SCREENSHOT_DIR / f"{name}.png"
                await page.screenshot(path=str(screenshot_path), full_page=True)

                print(f"  Saved: {screenshot_path.name}")
                captured.append(name)

            except Exception as e:
                print(f"  Error capturing {name}: {e}")

        await browser.close()

        print("-" * 50)
        print(f"Captured {len(captured)}/{len(PAGES)} screenshots")

        return len(captured) == len(PAGES)


async def create_screenshot_gallery():
    """Create a markdown gallery of screenshots."""
    gallery_path = SCREENSHOT_DIR / "README.md"

    content = """# Medical KAG Web UI Screenshots

## Pages

"""

    for page_info in PAGES:
        name = page_info["name"]
        title = page_info["title"]
        screenshot_file = f"{name}.png"

        content += f"""### {title}

![{title}]({screenshot_file})

---

"""

    content += """
## How to Update Screenshots

Run the capture script after starting the Streamlit app:

```bash
# Terminal 1: Start the app
streamlit run web/app.py

# Terminal 2: Capture screenshots
python scripts/capture_screenshots.py
```
"""

    with open(gallery_path, "w") as f:
        f.write(content)

    print(f"Created gallery: {gallery_path}")


async def main():
    """Main entry point."""
    print("=" * 50)
    print("Medical KAG Screenshot Capture")
    print("=" * 50)
    print()

    # Capture screenshots
    success = await capture_screenshots()

    if success:
        # Create gallery
        await create_screenshot_gallery()
        print()
        print("Screenshot capture complete!")
    else:
        print()
        print("Screenshot capture incomplete. Please check the errors above.")

    return 0 if success else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
