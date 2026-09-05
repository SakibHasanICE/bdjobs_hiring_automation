# app/main.py
import asyncio
from components.browser_manager import BrowserManager

async def test_browser():
    print("Initializing Browser Manager...")
    # Set headless=False to watch the browser launch
    manager = BrowserManager(headless=False)
    
    try:
        # Initialize context and create a new page
        await manager.initialize()
        page = await manager.new_page()
        
        print("Navigating to BDJobs...")
        await page.goto("https://www.bdjobs.com/", timeout=30000)
        
        # Grab the title to prove we loaded the page
        title = await page.title()
        print(f"Success! Page Title loaded: {title}")
        
        # Pause for 3 seconds so you can see it before it closes
        await asyncio.sleep(3)
        
    except Exception as e:
        print(f"An error occurred during testing: {e}")
        
    finally:
        print("Tearing down browser session...")
        await manager.teardown()

if __name__ == "__main__":
    asyncio.run(test_browser())