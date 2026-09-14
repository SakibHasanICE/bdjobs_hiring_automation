import asyncio
import json
import os
from dotenv import load_dotenv
from components.browser_manager import BrowserManager
from components.bdjobs_auth import BDJobsAuth
from components.job_poster import JobPoster

load_dotenv()

async def debug_dom():
    manager = BrowserManager(headless=False)
    try:
        await manager.initialize()
        page = await manager.new_page()
        page.set_default_timeout(15000)  # fail fast instead of 60s

        auth = BDJobsAuth(page)
        await auth.login(os.getenv("BDJOBS_USER"), os.getenv("BDJOBS_PASS"))

        poster = JobPoster(page)
        await poster.navigate_to_post_job()
        await poster.fill_step_1_basic_info({"title": "Debug Test", "vacancies": 1})

        # --- 1. Job Location dropdown: find every leaf element whose text is
        # exactly "Dhaka" anywhere in the document (covers portal/overlay panels
        # that aren't nested inside the input's own parent chain). ---
        trigger = page.get_by_text("Add more", exact=False).first
        await trigger.click(force=True)
        await page.wait_for_timeout(500)
        loc_input = page.locator(
            "input#jobLocation, input[formcontrolname='LocationSearchString']"
        ).first
        await loc_input.click(force=True)
        await page.keyboard.type("Dhaka", delay=100)
        await page.wait_for_timeout(1500)

        location_matches = await page.evaluate("""
            () => {
                const out = [];
                document.querySelectorAll('*').forEach(el => {
                    if (el.children.length === 0 && el.textContent.trim() === 'Dhaka') {
                        const r = el.getBoundingClientRect();
                        out.push({
                            tag: el.tagName,
                            className: el.className,
                            visible: r.width > 0 && r.height > 0,
                            outerHTML: el.outerHTML.slice(0, 300),
                            parentTag: el.parentElement ? el.parentElement.tagName : null,
                            parentClassName: el.parentElement ? el.parentElement.className : null,
                            grandparentTag: el.parentElement?.parentElement ? el.parentElement.parentElement.tagName : null,
                            grandparentClassName: el.parentElement?.parentElement ? el.parentElement.parentElement.className : null,
                        });
                    }
                });
                return out;
            }
        """)
        print("\n===== ELEMENTS WITH TEXT 'Dhaka' =====")
        print(json.dumps(location_matches, indent=2))

        # --- 2. Monthly Salary inputs: find EVERY input with placeholder
        # 'Minimum' / 'Maximum' in the whole document, and whether each is
        # actually visible - tells us if we're grabbing a hidden duplicate. ---
        salary_matches = await page.evaluate("""
            () => {
                const out = [];
                document.querySelectorAll("input[placeholder='Minimum'], input[placeholder='Maximum']").forEach((el, i) => {
                    const r = el.getBoundingClientRect();
                    out.push({
                        index: i,
                        placeholder: el.placeholder,
                        visible: r.width > 0 && r.height > 0,
                        outerHTML: el.outerHTML,
                        nearestLabelText: (() => {
                            let node = el;
                            for (let depth = 0; depth < 6 && node; depth++) {
                                node = node.parentElement;
                                if (node && node.textContent && node.textContent.trim().length < 200) {
                                    // return the text of the smallest ancestor with meaningful content
                                }
                            }
                            return null;
                        })(),
                    });
                });
                return out;
            }
        """)
        print("\n===== ALL 'Minimum'/'Maximum' PLACEHOLDER INPUTS =====")
        print(json.dumps(salary_matches, indent=2))

        print("\nBrowser will stay open for 60s so you can also inspect manually (F12).")
        await page.wait_for_timeout(60000)

    except Exception as e:
        print(f"Debug script failed: {e}")
        try:
            await page.screenshot(path="debug_state.png", full_page=True)
        except Exception:
            pass
    finally:
        await manager.teardown()

if __name__ == "__main__":
    asyncio.run(debug_dom())