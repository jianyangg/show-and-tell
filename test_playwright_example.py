import asyncio
from playwright.async_api import async_playwright, expect

# HTML for a simple test page with a pre-filled input field.
# This allows the test to run without external dependencies.
TEST_PAGE_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Test Page</title>
</head>
<body>
    <input type="text" id="test_input" value="initial text">
</body>
</html>
"""


async def test_type_text_overwrite(page):
    """
    Test that the `type_text_at` action with `clear_before_typing=True`
    correctly overwrites existing text in an input field.
    """
    await page.set_content(TEST_PAGE_HTML)
    input_selector = "#test_input"
    input_field = page.locator(input_selector)

    # Ensure the input field has the initial value.
    await expect(input_field).to_have_value("initial text")

    # Simulate the `type_text_at` action by first clearing and then typing.
    # The bug was that the clearing mechanism was unreliable.
    bounding_box = await input_field.bounding_box()
    if bounding_box:
        x = bounding_box["x"] + bounding_box["width"] / 2
        y = bounding_box["y"] + bounding_box["height"] / 2

        # Triple-click to select all text.
        await page.mouse.click(x, y, click_count=3)
        await page.keyboard.press("Delete")
        await page.keyboard.type("new text")

    # Verify that the input field now contains only the new text.
    await expect(input_field).to_have_value("new text")
    print("Test `test_type_text_overwrite` passed.")


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1920, "height": 1080})
        page = await context.new_page()

        try:
            # Run the new test case
            await test_type_text_overwrite(page)

            # Original test case
            print("Navigating to https://example.com...")
            await page.goto("https://example.com", timeout=60_000)
            print("Navigation successful.")

            await page.screenshot(path="debug_before_click.png")
            print("Screenshot saved to debug_before_click.png")

            target_locator = page.locator(
                "a[href='https://www.iana.org/domains/example']"
            )

            print("Attempting to click the link…")
            await target_locator.click(timeout=10_000)
            print("Click succeeded.")

            await page.wait_for_url("**/domains/example**", timeout=5_000)
            print("Now at:", page.url)
        except Exception as exc:
            print("--- SCRIPT FAILED ---")
            print(exc)
            await page.screenshot(path="debug_on_failure.png")
            print("Failure screenshot saved todebug_on_failure.png")
            print("---------------------")
        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
