import asyncio
import re
from datetime import datetime
from playwright.async_api import Page

class JobPoster:
    """Navigates the employer dashboard to publish job circulars."""
    def __init__(self, page: Page):
        self.page = page

    async def navigate_to_post_job(self) -> bool:
        """Clicks the 'Post a New Job' button and waits for the form to load."""
        button_selector = "text='Post a New Job'"
        
        await self.page.wait_for_selector(button_selector, state="visible", timeout=15000)
        await self.page.locator(button_selector).first.click()
        
        await self.page.wait_for_load_state("networkidle")
        return True

    async def fill_step_1_basic_info(self, job_data: dict) -> bool:
        """Fills the initial text inputs for Step 1: Job Information."""
        title_input = "input[placeholder*='Enter Job Title']"
        vacancy_input = "input[placeholder*='Enter Vacancy No']"
        
        await self.page.wait_for_selector(title_input, state="visible", timeout=10000)
        await self.page.locator(title_input).first.fill(job_data["title"])
        
        if job_data.get("vacancies"):
            await self.page.locator(vacancy_input).first.fill(str(job_data["vacancies"]))
            
        return True

    async def fill_step_1_options(self, job_data: dict) -> bool:
        """Selects standard radio buttons and checkboxes based on their visible labels."""
        if status := job_data.get("employment_status"):
            await self.page.locator(f"label:has-text('{status}')").first.click()
            
        if workplace := job_data.get("workplace"):
            await self.page.locator(f"label:has-text('{workplace}')").first.click()
            
        return True

    async def fill_step_1_complex_fields(self, job_data: dict) -> bool:
        """Handles custom dropdowns and date pickers in Step 1."""
        
        # 1. Job Category Dropdown (Keyboard Strategy)
        if category := job_data.get("category"):
            dropdown_placeholder = "text='Choose a Job Category'"
            
            await self.page.locator(dropdown_placeholder).first.click(force=True)
            await self.page.wait_for_timeout(500)
            
            await self.page.keyboard.type(category, delay=100)
            
            await self.page.wait_for_timeout(1000)
            await self.page.keyboard.press("Enter")

        # 2. Job Location Dropdown (Structural Locator)
        if location := job_data.get("job_location"):
            # input#jobLocation carries an "input-hidden" class and has no on-screen
            # box until the field is activated - clicking it directly throws
            # "outside of the viewport" even with force=True. Activate the visible
            # widget first (the "Add more" trigger next to the location chips).
            trigger = self.page.get_by_text("Add more", exact=False).first
            if await trigger.count() == 0:
                # Fallback: click the field's own container if "Add more" isn't present
                trigger = self.page.locator("label:has-text('Job Location')").locator("xpath=..").first
            await trigger.scroll_into_view_if_needed()
            await trigger.click(force=True)
            await self.page.wait_for_timeout(500)

            # Re-locate the input now that the widget is active - it should be visible
            loc_input = self.page.locator(
                "input#jobLocation, input[formcontrolname='LocationSearchString']"
            ).first
            await loc_input.wait_for(state="visible", timeout=5000)
            await loc_input.click(force=True)

            await self.page.keyboard.type(location, delay=100)
            await self.page.wait_for_timeout(1500) # Wait for dropdown results to render

            # Real markup (confirmed via DOM dump): each suggestion is
            # <button class="location-option"><span class="location-name"><strong>...</strong></span></button>
            # Prefer the option whose visible text is an exact match (e.g. plain
            # "Dhaka" rather than "Dhaka (Dhaka Court)"); otherwise take the top
            # suggestion, same intent as the original "press Enter" behaviour.
            option = self.page.locator("button.location-option").filter(
                has=self.page.locator(f"span.location-name:text-is('{location}')")
            ).first
            if await option.count() == 0:
                option = self.page.locator("button.location-option").first
            await option.click(force=True)

            # Make sure the panel actually closed - if it's left open, it
            # intercepts clicks in every step after this one (Deadline,
            # Salary, and - confirmed live - even the Step 2 "Add Additional
            # Requirements" button two pages later) and silently swallows
            # them. A bare Escape + fixed wait wasn't reliable enough for
            # this widget, so use the shared cleanup helper instead, which
            # also waits for the option list to actually disappear.
            await self._dismiss_stray_overlays()
            
        # 3. Select Deadline (Date Picker)
        if deadline := job_data.get("deadline"):
            deadline_input_selector = "input[placeholder*='Select Deadline']"
            deadline_input = self.page.locator(deadline_input_selector).first

            # The icon is the real click target that opens the picker overlay
            # (clicking the plain <input> alone does not open it).
            calendar_icon = self.page.locator("span.icon-calendar, .icon-calendar").first
            if await calendar_icon.count() > 0:
                await calendar_icon.scroll_into_view_if_needed()
                await calendar_icon.click(force=True)
            else:
                print("Deadline calendar: icon.icon-calendar not found, falling back to clicking the input.")
                await deadline_input.click(force=True)

            await self.page.wait_for_timeout(600)
            await self.page.screenshot(path="debug_deadline_calendar_open.png", full_page=True)

            # PREVIOUS BUG #1: this scan filtered elements with `el.offsetParent
            # !== null`, which is always null for position:fixed elements -
            # exactly what a CDK overlay pane (.cdk-overlay-pane, already in the
            # selector list below) normally is. That silently hid the real
            # calendar panel from this diagnostic even while it was visibly open
            # on screen (confirmed by the screenshot), so we only ever "found"
            # the closed toggle icon. Use getBoundingClientRect() instead, which
            # doesn't have that blind spot.
            calendar_snapshot = await self.page.evaluate(
                """
                () => {
                    const isVisible = (el) => {
                        const rect = el.getBoundingClientRect();
                        return rect.width > 0 && rect.height > 0;
                    };
                    const selectors = [
                        '[class*="datepicker" i]', '[class*="date-picker" i]',
                        '[class*="calendar" i]', '.cdk-overlay-pane',
                        '.mat-datepicker-content', '[role="dialog"]'
                    ];
                    const seen = new Set();
                    const results = [];
                    for (const sel of selectors) {
                        document.querySelectorAll(sel).forEach(el => {
                            if (!seen.has(el) && isVisible(el)) {
                                seen.add(el);
                                results.push({ selector: sel, html: el.outerHTML.slice(0, 2500) });
                            }
                        });
                    }

                    // Class-name selectors keep missing the real overlay (it may
                    // be a custom element tag like <ngb-datepicker>/<p-calendar>
                    // with no "calendar"/"datepicker" in its class list at all).
                    // Fall back to tag-name matching...
                    document.querySelectorAll('*').forEach(el => {
                        const tag = el.tagName.toLowerCase();
                        if (!seen.has(el) && isVisible(el) &&
                            (tag.includes('calendar') || tag.includes('datepicker') || tag.includes('date-picker'))) {
                            seen.add(el);
                            results.push({ selector: `tag:${tag}`, html: el.outerHTML.slice(0, 2500) });
                        }
                    });

                    // ...and as a last resort, a weekday-header heuristic: any
                    // visible element whose OWN direct text (not descendants'
                    // combined text) area contains the "Mo Tu We Th Fr Sa Su"
                    // pattern is almost certainly the calendar grid container,
                    // regardless of what it's named.
                    if (results.length === 0) {
                        let best = null;
                        document.querySelectorAll('*').forEach(el => {
                            const t = el.textContent || '';
                            if (isVisible(el) && /Mo.{0,3}Tu.{0,3}We.{0,3}Th.{0,3}Fr.{0,3}Sa.{0,3}Su/.test(t)) {
                                if (!best || t.length < best.textContent.length) best = el;
                            }
                        });
                        if (best) {
                            results.push({ selector: 'weekday-heuristic', html: best.outerHTML.slice(0, 2500) });
                        }
                    }

                    return results;
                }
                """
            )
            if calendar_snapshot:
                print(f"Deadline calendar: found {len(calendar_snapshot)} visible calendar-like element(s):")
                for item in calendar_snapshot:
                    print(f"--- matched by {item['selector']} ---")
                    print(item["html"])
            else:
                print(
                    "Deadline calendar: no calendar-like overlay found after clicking the "
                    "input. It may not have opened at all, or use markup this scan doesn't "
                    "recognize - see debug_deadline_calendar_open.png."
                )

            # PREVIOUS BUG #2 (the actual root cause of the original failure):
            # after opening the calendar and screenshotting it for diagnostics,
            # the old code went straight to Escape - it never clicked an actual
            # day. Now confirmed via the diagnostic dump: this is ng-bootstrap's
            # <ngb-datepicker>. Its markup gives us two much more reliable
            # anchors than guessing at visible text:
            #   1. Month/year navigation is two native <select> elements
            #      (aria-label="Select month" / "Select year") - use
            #      select_option(), not clicking chevrons or text.
            #   2. Each day cell has an exact, unambiguous aria-label like
            #      "Tuesday, September 8, 2026" on the role="gridcell" div,
            #      and disabled/adjacent-month cells are literally marked
            #      class="ngb-dp-day disabled" - no guessing needed.
            #
            # deadline is "MM/DD/YYYY" (see mock_internal_job in main.py).
            target_date = datetime.strptime(deadline, "%m/%d/%Y")

            month_select = self.page.locator("select[aria-label='Select month']").first
            year_select = self.page.locator("select[aria-label='Select year']").first

            if await month_select.count() == 0 or await year_select.count() == 0:
                await self.page.screenshot(path="error_deadline_nav_not_found.png", full_page=True)
                raise RuntimeError(
                    "Could not find the ngb-datepicker month/year <select> elements. "
                    "Saved error_deadline_nav_not_found.png - the calendar component may "
                    "have changed; re-check the 'Deadline calendar: found N visible "
                    "calendar-like element(s)' log above."
                )

            await month_select.select_option(value=str(target_date.month))
            await self.page.wait_for_timeout(200)
            await year_select.select_option(value=str(target_date.year))
            await self.page.wait_for_timeout(300)

            # Build the exact aria-label ngb-bootstrap renders for this date,
            # e.g. "Friday, September 25, 2026" - matches the disabled-cell
            # samples seen in the diagnostic dump ("Saturday, September 5, 2026").
            target_aria_label = target_date.strftime("%A, %B ") + str(target_date.day) + target_date.strftime(", %Y")

            day_cell = self.page.locator(
                f"div[role='gridcell'][aria-label='{target_aria_label}']:not(.disabled)"
            ).first

            if await day_cell.count() == 0:
                await self.page.screenshot(path="error_deadline_day_not_found.png", full_page=True)
                raise RuntimeError(
                    f"Could not find an enabled day cell with aria-label "
                    f"'{target_aria_label}'. Saved error_deadline_day_not_found.png - the "
                    f"deadline date may be outside the range the picker allows to select, "
                    f"or the aria-label format has changed."
                )

            # Click the inner ngbDatepickerDayView element (the actual click
            # target Angular listens on), not just the outer gridcell wrapper.
            day_view = day_cell.locator("[ngbdatepickerdayview]").first
            target = day_view if await day_view.count() > 0 else day_cell
            await target.scroll_into_view_if_needed()
            await target.click(force=True)
            await self.page.wait_for_timeout(400)

            # Verify, don't trust the click blindly: the input should now hold
            # a non-empty value and the "Deadline can't be empty" error should
            # be gone. Raise clearly instead of silently moving on to a form
            # that's still missing a required field.
            value = (await deadline_input.input_value()).strip()
            if not value:
                await self.page.screenshot(path="error_deadline_not_set.png", full_page=True)
                raise RuntimeError(
                    f"Deadline click did not populate the input for target date "
                    f"{deadline} (aria-label '{target_aria_label}'). Saved "
                    f"error_deadline_not_set.png for inspection."
                )
            print(f"Deadline calendar: input now reads '{value}'.")

        return True

    
    async def fill_step_1_details(self, job_data: dict) -> bool:
        """Fills job responsibilities and salary information in Step 1."""
        
        # 1. Job Responsibilities & Context
        if resp := job_data.get("job_responsibilities"):
            # The old comma-separated selector's .first picked whichever matching
            # element came first in raw DOM order - if another (hidden) rich-text
            # editor exists elsewhere in the wizard, that's what got grabbed instead
            # of this field, causing "element is not visible" timeouts. Anchor the
            # lookup to the "Job Responsibilities" heading itself so we always get
            # the right one regardless of how many editors exist on the page.
            editor = self.page.locator(
                "xpath=//*[contains(text(),'Job Responsibilities')]"
                "/ancestor::*[.//*[contains(@class,'ql-editor') or @contenteditable='true']][1]"
                "//*[contains(@class,'ql-editor') or @contenteditable='true']"
            ).first
            await editor.scroll_into_view_if_needed()
            await editor.click(force=True)
            
            # Using evaluate to set innerText bypasses complex keyboard event listeners on
            # rich-text editors. Pass the text as an evaluate() argument (not string-
            # interpolated into the JS) so backticks / ${...} in the responsibilities
            # text can't break the generated script.
            await editor.evaluate(
                "(el, text) => { el.innerText = text; "
                "el.dispatchEvent(new Event('input', { bubbles: true })); }",
                resp,
            )
            
        # 2. Monthly Salary
        if salary := job_data.get("salary"):
            # Confirmed via DOM dump: id="Minimum" / id="Maximum" are globally
            # unique and visible - no need for the fragile ancestor-xpath scoping.
            if min_sal := salary.get("min"):
                min_input = self.page.locator("#Minimum")
                await min_input.scroll_into_view_if_needed()
                await min_input.click()
                await min_input.fill(str(min_sal))
                
            if max_sal := salary.get("max"):
                max_input = self.page.locator("#Maximum")
                await max_input.click()
                await max_input.fill(str(max_sal))
                
        return True

    async def fill_compensation_and_benefits(self, job_data: dict) -> bool:
        """Opens the 'Compensation and Benefits' modal and fills it in."""
        comp = job_data.get("compensation_benefits")
        if not comp:
            return True

        # Open the modal
        add_btn = self.page.get_by_text("Add compensation and benefit information", exact=False).first
        await add_btn.scroll_into_view_if_needed()
        await add_btn.click(force=True)
        await self.page.wait_for_timeout(800)

        # 1. Multi-select benefit chips (T/A, Provident fund, Insurance, etc.)
        # These are unique, one-off labels unlikely to repeat elsewhere on the
        # page, so a plain exact-text match is enough - no special scoping needed.
        print(f"Compensation modal: selecting benefit chips {comp.get('benefits', [])}...")
        for label in comp.get("benefits", []):
            chip = self.page.get_by_text(label, exact=True).first
            if await chip.count() > 0:
                await chip.click(force=True)
                await self.page.wait_for_timeout(200)
            else:
                print(f"Compensation chip not found, skipped: {label}")

        # 2. Lunch Facility (single-select: Partially subsidize / Full Subsidize)
        if lunch := comp.get("lunch_facility"):
            print(f"Compensation modal: selecting lunch facility '{lunch}'...")
            option = self.page.get_by_text(lunch, exact=True).first
            if await option.count() > 0:
                await option.click(force=True)

        # 3. Salary Review (single-select: Half Yearly / Yearly)
        if review := comp.get("salary_review"):
            print(f"Compensation modal: selecting salary review '{review}'...")
            option = self.page.get_by_text(review, exact=True).first
            if await option.count() > 0:
                await option.click(force=True)

        # 4. Festival Bonus - this is a native <select> element (confirmed: the
        # placeholder resolves to an <option value="0">), not a custom dropdown,
        # so it needs select_option() rather than a click.
        if bonus := comp.get("festival_bonus"):
            print(f"Compensation modal: selecting festival bonus '{bonus}'...")
            festival_select = self.page.locator(
                "select:has(option:text-is('Select Number of Festival Bonus'))"
            ).first
            bonus_str = str(bonus)
            try:
                await festival_select.select_option(label=bonus_str)
            except Exception:
                try:
                    await festival_select.select_option(value=bonus_str)
                except Exception as select_error:
                    print(f"Could not select Festival Bonus '{bonus_str}': {select_error}")

        # 5. Other Benefits (rich text editor). The ancestor-based scoping that
        # worked for Job Responsibilities can grab the wrong editor here if the
        # nearest common ancestor is the whole modal (which may still contain
        # other hidden editors earlier in DOM order). Instead, walk forward in
        # document order from the "Other Benefits" heading and take the very
        # next editor-like element - matches this form's top-to-bottom layout.
        if other := comp.get("other_benefits"):
            print("Compensation modal: locating Other Benefits editor...")
            editor = self.page.locator(
                "xpath=//*[contains(text(),'Other Benefits')]"
                "/following::*[contains(@class,'ql-editor') or @contenteditable='true'][1]"
            ).first
            await editor.scroll_into_view_if_needed()
            print("Compensation modal: Other Benefits editor is visible, filling it...")
            await editor.click(force=True)
            await editor.evaluate(
                "(el, text) => { el.innerText = text; "
                "el.dispatchEvent(new Event('input', { bubbles: true })); }",
                other,
            )
            print("Compensation modal: Other Benefits filled.")

        # 6. Save - anchor forward from "Other Benefits" too, so we land on
        # this modal's own Save button rather than some unrelated "Save"
        # element elsewhere in the page's DOM.
        print("Compensation modal: locating Save button...")
        save_btn = self.page.locator(
            "xpath=//*[contains(text(),'Other Benefits')]"
            "/following::*[self::button or @role='button'][contains(text(),'Save')][1]"
        ).first
        if await save_btn.count() == 0:
            save_btn = self.page.get_by_text("Save", exact=True).last
        await save_btn.scroll_into_view_if_needed()
        await save_btn.click(force=True)

        # Don't just assume the modal closed after a fixed pause - if it silently
        # stayed open, it will intercept every subsequent click (including the
        # Step 1 -> Step 2 "Continue" button) without any visible error. Watch
        # the actual editable field itself (not the "Other Benefits" text -
        # that heading is also part of the page's saved summary card once the
        # modal closes, so it never goes hidden and would always look "stuck").
        modal_check_target = editor if other else save_btn
        try:
            await modal_check_target.wait_for(state="hidden", timeout=5000)
            print("Compensation modal: confirmed closed.")
        except Exception:
            print(
                "WARNING: Compensation modal may still be open after clicking Save."
                "This will likely block the next 'Continue' click."
            )
            await self.page.screenshot(path="warning_compensation_modal_still_open.png", full_page=True)

        return True

    async def proceed_to_next_step(self, wait_for_text: str | None = None) -> bool:
        """Clicks the button to save the current step and advance the wizard.

        wait_for_text: text unique to the NEXT step (e.g. "Preferred Gender" when
        moving from Step 1 -> Step 2). If given, we verify the transition actually
        happened before returning, instead of trusting the click blindly. This
        matters because .last on an unfiltered "Continue|Next" match can grab a
        button belonging to a different, currently-hidden step (many wizard UIs
        keep every step's markup mounted and just toggle visibility), and
        click(force=True) bypasses the normal "is this actually clickable"
        checks - so a mis-click like that fails silently instead of raising.
        """

        # Target elements containing "Continue" or "Next", but only ones that are
        # actually visible right now - not a same-text button belonging to some
        # other (hidden) step's markup elsewhere in the DOM.
        candidates = self.page.get_by_text(re.compile("Continue|Next", re.IGNORECASE))
        count = await candidates.count()
        visible_indices = [i for i in range(count) if await candidates.nth(i).is_visible()]

        print(f"proceed_to_next_step: found {count} 'Continue/Next' matches, {len(visible_indices)} visible.")
        for i in range(count):
            el = candidates.nth(i)
            try:
                text = (await el.inner_text()).strip().replace("\n", " ")[:40]
                visible = await el.is_visible()
                box = await el.bounding_box()
                print(f"  [{i}] visible={visible} text={text!r} box={box}")
            except Exception as diag_err:
                print(f"  [{i}] <could not inspect: {diag_err}>")

        if not visible_indices:
            await self.page.screenshot(path="error_no_continue_button.png", full_page=True)
            raise RuntimeError(
                "No visible 'Continue'/'Next' button found - the page may be in an "
                "unexpected state (e.g. a modal still open). Saved error_no_continue_button.png."
            )

        continue_btn = candidates.nth(visible_indices[-1])

        # A force=True click bypasses Playwright's normal actionability checks -
        # including "is this element enabled". If the app disables Continue via a
        # client-side validation rule (form invalid, hidden required field, etc.),
        # a forced click typically no-ops: no exception, no navigation, nothing.
        # That's indistinguishable from "the click just didn't register" unless
        # we check for it explicitly.
        is_enabled = await continue_btn.is_enabled()
        aria_disabled = await continue_btn.get_attribute("aria-disabled")
        print(f"proceed_to_next_step: Continue button is_enabled={is_enabled} aria-disabled={aria_disabled}")
        if not is_enabled or aria_disabled == "true":
            print(
                "WARNING: the Continue button appears disabled. The wizard likely has an "
                "unmet validation requirement somewhere in Step 1 - force-clicking a "
                "disabled control usually does nothing."
            )

        # Watch network responses and JS errors during the click, since "briefly
        # reaches the next step then bounces back to this one" usually means the
        # click triggers a save/validate API call, the app optimistically shows
        # the next step, and then reverts when that call comes back with an
        # error - which a screenshot taken after the fact won't show at all.
        failed_responses = []
        console_errors = []
        body_read_tasks = []

        async def _capture_body(response):
            try:
                body = await response.text()
            except Exception as body_err:
                body = f"<could not read response body: {body_err}>"
            failed_responses.append((response.status, response.url, body))

        def _on_response(response):
            if response.status >= 400:
                # response.text() is async and can't be awaited inside this sync
                # callback, so schedule it and await all of them together below,
                # before we print the summary.
                body_read_tasks.append(asyncio.create_task(_capture_body(response)))

        def _on_pageerror(exc):
            console_errors.append(str(exc))

        def _on_console(msg):
            if msg.type == "error":
                console_errors.append(msg.text)

        self.page.on("response", _on_response)
        self.page.on("pageerror", _on_pageerror)
        self.page.on("console", _on_console)

        try:
            # Scroll and force the click in case a sticky footer or chat widget is overlapping it
            await continue_btn.scroll_into_view_if_needed()
            await continue_btn.click(force=True)

            # Grab a screenshot the instant after clicking, before any of our own
            # waits run - if the app shows a transient validation toast/snackbar
            # ("please complete X"), it will very likely have faded by the time we
            # screenshot later after a failed wait_for, several seconds on.
            await self.page.screenshot(path="debug_immediately_after_continue_click.png", full_page=True)

            # A second checkpoint partway through, in case the app shows Step 2
            # briefly before an API error bounces it back to Step 1 - a single
            # "before" and "after" screenshot would miss that entirely.
            await self.page.wait_for_timeout(1500)
            await self.page.screenshot(path="debug_1500ms_after_continue_click.png", full_page=True)

            # Wait for the next step's UI to load and stabilize
            await self.page.wait_for_load_state("networkidle")
            await self.page.wait_for_timeout(2000)

            if body_read_tasks:
                await asyncio.gather(*body_read_tasks, return_exceptions=True)
        finally:
            self.page.remove_listener("response", _on_response)
            self.page.remove_listener("pageerror", _on_pageerror)
            self.page.remove_listener("console", _on_console)

        if failed_responses:
            print(f"proceed_to_next_step: {len(failed_responses)} failed HTTP response(s) during transition:")
            for status, url, body in failed_responses:
                print(f"  [{status}] {url}")
                print(f"    body: {body[:1000]}")
        if console_errors:
            print(f"proceed_to_next_step: {len(console_errors)} console/page error(s) during transition:")
            for err in console_errors:
                print(f"  {err[:300]}")

        if wait_for_text:
            try:
                await self.page.get_by_text(wait_for_text, exact=False).first.wait_for(
                    state="visible", timeout=15000
                )
            except Exception as e:
                await self.page.screenshot(path="error_step_transition.png", full_page=True)
                raise RuntimeError(
                    f"Step transition may have failed: expected '{wait_for_text}' to appear "
                    f"after clicking Continue, but it never did within 15s. This usually means "
                    f"the click didn't land (e.g. a modal from the previous step was still open "
                    f"and swallowed it). Saved error_step_transition.png. Original error: {e}"
                )

        return True

    async def _dismiss_stray_overlays(self) -> None:
        """Closes/clears away any leftover open dropdown or suggestion panel
        - most notably the Job Location autocomplete's `button.location-option`
        list - that can keep occupying screen space long after its own field
        is done with it and silently intercept clicks meant for later,
        unrelated controls.

        CONFIRMED LIVE BUG: the Step 2 "Add Additional Requirements" modal
        never opened because a stray `button.location-option` element (left
        over from Step 1's Job Location field) was still sitting on top of
        that button and intercepting pointer events. Worse, the `force=True`
        retry landed on that SAME stray element instead of the real button
        underneath it - `force=True` only skips Playwright's own
        actionability checks, it does not change which element the real
        browser click is delivered to, and the browser always delivers a
        click to whatever is actually topmost at those pixel coordinates.
        So the fix has to get the stray element out of the way first, not
        click through it.

        Call this right after any field that opens its own dropdown/overlay
        (Job Location), and again defensively right before any click that
        has previously been reported as intercepted (Additional
        Requirements).
        """
        await self.page.keyboard.press("Escape")
        # Click a neutral, always-present part of the page to force a blur/
        # close on whatever custom widget still thinks it's open - Escape
        # alone isn't reliably bound to this particular Angular widget.
        neutral = self.page.get_by_text("Post a Job", exact=False).first
        if await neutral.count() > 0:
            try:
                await neutral.click(force=True, timeout=2000)
            except Exception:
                pass
        try:
            await self.page.locator("button.location-option").first.wait_for(
                state="hidden", timeout=3000
            )
        except Exception:
            # Either already gone, or genuinely stuck - don't hang the rest
            # of the run over a single cleanup step either way.
            pass
        await self.page.wait_for_timeout(200)

    async def _get_tag_container(self, heading_text: str):
        """Returns the Locator for the widget container directly below a
        given visible heading (e.g. "Skills & Area of expertise"). Shared by
        `_clear_existing_tags` (removing old chips) and `_add_tag_via_suggestion`
        (verifying a new chip actually landed), so both always agree on
        which DOM region counts as "this widget".
        """
        return self.page.locator(
            f"xpath=//*[contains(text(),'{heading_text}')]"
            f"/following::*[self::div or self::section][1]"
        ).first

    async def _get_chip_texts(self, container) -> set:
        """Returns the lower-cased label text of every currently committed
        chip inside `container` (Skills / Preferred Industries widgets).

        Identifies each chip by walking up from its own remove/x control,
        the same starting point `_clear_existing_tags` uses. The walk is
        capped: at each ancestor level we only accept the candidate text if
        it's short (<=60 chars, generous for a single chip label) - the
        moment an ancestor's text gets longer than that, we stop and use the
        last short one we saw. This is what keeps the check honest: without
        the cap, climbing far enough eventually reaches a shared ancestor
        that also contains unrelated, much longer text elsewhere on the
        same page (e.g. the Job Responsibilities / Additional Requirements
        text this project already fills in, which can easily contain the
        exact same words as the skills being added - "PostgreSQL", "Django",
        "Docker" all appear verbatim in that copy). Capping the size is what
        stops a real committed chip from being indistinguishable from a
        false match against that unrelated copy.
        """
        remove_controls = container.locator(
            "button:has-text('×'), button:has-text('X'), "
            "[class*='remove' i], [class*='close' i], svg[class*='close' i]"
        )
        texts = set()
        count = await remove_controls.count()
        for idx in range(count):
            control = remove_controls.nth(idx)
            best_text = ""
            for level in range(1, 5):  # climb a handful of ancestor levels
                ancestor = control.locator("xpath=" + "/".join([".."] * level))
                try:
                    candidate = (await ancestor.inner_text()).strip()
                except Exception:
                    break
                if not candidate:
                    continue
                if len(candidate) <= 60:
                    best_text = candidate
                else:
                    break  # too big to be a single chip - keep the last good one
            if best_text:
                texts.add(best_text.lower())
        return texts

    async def _find_best_suggestion_match(self, value: str, log_label: str = None):
        """Scans every currently-visible dropdown/listbox-like panel on the
        page for an option matching `value` - exact (case-insensitive) match
        preferred, else the shortest option that contains `value` as a
        substring. Returns (matched_text, matched_panel) or (None, None) if
        nothing matched anywhere within ~5s.

        This is the same panel-scoped matching logic already proven for the
        Skills/Preferred-Industries tag widgets, extracted so the Degree
        Major/Subject field can use it too. That field previously used a
        page-wide `get_by_text()` lookup instead (first for an exact match,
        then falling back to just the first WORD of the target, matched
        anywhere on the page) - since the real suggestion list renders full
        compound labels like "Bachelor of Science (BSc) in Computer Science
        & Engineering" rather than the bare major name, the exact-match
        branch would fail, and the loose fallback was then free to match ANY
        element on the page containing that word, not just the genuine open
        suggestion. That's the most likely cause of the Major/Subject field
        repeatedly landing on the wrong suggestion.
        """
        label = log_label or value
        panel_candidates = self.page.locator(
            "ngb-typeahead-window:visible, [role='listbox']:visible, .dropdown-menu:visible"
        )

        panel_logged = False
        for _ in range(17):  # ~5s total
            await self.page.wait_for_timeout(300)
            candidate_count = await panel_candidates.count()
            if candidate_count == 0:
                continue

            for panel_idx in range(candidate_count):
                candidate = panel_candidates.nth(panel_idx)

                options = candidate.locator("[role='option']:visible")
                if await options.count() == 0:
                    options = candidate.locator("button:visible")
                if await options.count() == 0:
                    options = candidate.locator("li:visible")
                option_count = await options.count()
                if option_count == 0:
                    continue

                if not panel_logged:
                    try:
                        snippet = (await candidate.inner_text())[:300].replace("\n", " | ")
                        print(f"  [{label!r}] candidate panel #{panel_idx} options: {snippet!r}")
                    except Exception:
                        pass

                option_texts = [(await options.nth(idx).inner_text()).strip() for idx in range(option_count)]

                for text in option_texts:
                    if text.lower() == value.lower():
                        return text, candidate

                best_text = None
                for text in option_texts:
                    if value.lower() in text.lower():
                        if best_text is None or len(text) < len(best_text):
                            best_text = text
                if best_text is not None:
                    return best_text, candidate

            panel_logged = True

        return None, None

    async def _clear_existing_tags(self, heading_text: str) -> None:
        """Removes every existing chip in a tag widget (Skills / Preferred
        Industries) BEFORE adding new ones.

        BUG FIX: the observed screenshot showed 9 "Preferred Industry" chips
        (Garments, Textile, Group of Companies, ...) after asking for only 2
        ("Information Technology", "Software"), and skill chips
        ("Documentation of Loan") with no textual relation at all to any of
        the 5 requested skills. That mismatch can't come from this run's
        typing alone - it's almost certainly leftover state from earlier
        runs against the SAME saved job draft (BDJobs appears to let you
        resume an in-progress posting, so any chip a previous - including
        older, buggier - run managed to click stays saved for next time).
        Since the old code only ever ADDS tags and never checks what's
        already there, garbage from past runs just keeps piling up. Clear
        the field first so every run starts from a known-empty state.

        `heading_text`: the visible heading directly above the widget (e.g.
        "Which industry you prefer candidates to have experience", "Skills &
        Area of expertise"). Scoping to the container under that heading
        keeps this from touching chips in some OTHER tag widget on the page.
        """
        container = await self._get_tag_container(heading_text)
        if await container.count() == 0:
            print(f"_clear_existing_tags: couldn't locate container for '{heading_text}', skipping clear.")
            return

        removed_count = 0
        for _ in range(20):  # hard ceiling so a wrong locator can't loop forever
            remove_btn = container.locator(
                "button:has-text('×'), button:has-text('X'), "
                "[class*='remove' i], [class*='close' i], svg[class*='close' i]"
            ).first
            if await remove_btn.count() == 0:
                break
            await remove_btn.click(force=True)
            await self.page.wait_for_timeout(200)
            removed_count += 1

        if removed_count:
            print(f"_clear_existing_tags: removed {removed_count} pre-existing chip(s) under '{heading_text}'")
        else:
            print(f"_clear_existing_tags: no pre-existing chips found under '{heading_text}'")

    async def _add_tag_via_suggestion(self, value: str, open_trigger=None, input_locator=None, heading_text: str = None) -> None:
        """Types `value` into a tag/autocomplete field and CLICKS the matching
        suggestion, instead of pressing Enter.

        This site's tag widgets (Skills, Preferred Industries, Degree Major -
        same pattern already confirmed working for Degree Major below) only
        commit a chip when the rendered suggestion is clicked. Pressing Enter
        leaves the raw text sitting in the input uncommitted.

        BUG FIX #1 (concatenation - "PythonDjango", "PytFastAPI"): the old
        code only .click()'d the input before typing. click() just focuses -
        it does NOT select/clear existing text. If the widget doesn't wipe
        its own <input> value after a chip is committed (common with these
        custom tag widgets), the next call's keystrokes land on top of
        whatever text is still sitting there from the previous tag, producing
        garbage that matches no real suggestion ("No skill found!"). We now
        explicitly select-all + delete the field before every typed value,
        and double-check input_value() is actually empty afterward.

        BUG FIX #2 (wrong/unrelated suggestion clicked - e.g. a "Garments"
        industry showing up for "Information Technology"): the old code did
        `self.page.get_by_text(value, ...)`, which searches the ENTIRE page,
        not just the open suggestion dropdown. Once the input contained
        garbled text (bug #1), that garbled string wouldn't match the real
        dropdown, so `exact=False` was free to match some unrelated element
        anywhere else in the DOM containing a similar substring, and `.first`
        clicked it. We now scope the suggestion search to the visible
        dropdown/listbox panel itself. This project has already confirmed
        this site uses ng-bootstrap (`ngb-datepicker` for the deadline
        picker), so the typeahead panel is most likely `ngb-typeahead-window`
        with `.dropdown-item`/`role='option'` entries - if this still fails,
        capture a DOM dump of the open panel (same technique used for the
        deadline calendar above) to confirm/adjust the selector.

        `open_trigger`: optional zero-arg callable returning a Locator to
        click first (e.g. "Add more") to open/focus a fresh slot.
        `input_locator`: optional zero-arg callable returning the Locator to
        click before typing. Omit this if `open_trigger` already leaves the
        real input focused.
        `heading_text`: the visible heading above this tag widget (e.g.
        "Skills & Area of expertise"). When given, a successful commit is
        verified against the ACTUAL chip container instead of only "did the
        input go blank" - see BUG FIX #4 below for why that mattered.
        """
        # BUG FIX #7 (this run - "no error logged, but the final Step 3
        # review screen shows 'Skills & Expertise: Not Added'"): capture
        # which chips already exist in this widget's container BEFORE we
        # type/click anything. The previous version (BUG FIX #6) checked
        # for success by testing whether the container's raw text contained
        # the skill name - but that container also holds *other* form
        # fields lower on the same row (confirmed by the earlier "Add
        # Additional Requirements" button sitting directly under "Skills &
        # Area of expertise" in the same block), and the Additional
        # Requirements / Job Responsibilities copy in this project's own
        # mock data literally contains "PostgreSQL", "Django", and "Docker"
        # as plain words. So the check kept passing - not because a chip
        # had been added, but because that unrelated paragraph elsewhere in
        # the same container happened to share vocabulary with the skill
        # being searched for. Diffing against a "before" snapshot fixes
        # this: only a NEWLY appeared chip counts, so pre-existing/unrelated
        # text that was already there (and would already be in the
        # baseline) can never be mistaken for a fresh commit.
        baseline_chip_texts = set()
        if heading_text:
            baseline_container = await self._get_tag_container(heading_text)
            baseline_chip_texts = await self._get_chip_texts(baseline_container)

        if open_trigger is not None:
            trigger = open_trigger()
            if await trigger.count() > 0:
                await trigger.scroll_into_view_if_needed()
                await trigger.click(force=True)
                await self.page.wait_for_timeout(300)

        input_el = None
        if input_locator is not None:
            input_el = input_locator()
            await input_el.wait_for(state="visible", timeout=5000)
            await input_el.click(force=True)

            # BUG FIX #1: force the field empty before typing the next tag.
            await input_el.press("Control+A")
            await input_el.press("Backspace")
            leftover = await input_el.input_value()
            if leftover:
                # Some of these Angular tag widgets restore a stray character
                # on refocus - fall back to manual backspacing until it's
                # actually empty rather than trusting select-all+delete once.
                for _ in range(len(leftover) + 5):
                    await self.page.keyboard.press("Backspace")

            # BUG FIX (cosmetic): typing immediately after clearing can race
            # the widget's own focus/clear repaint, which is a plausible
            # cause of the "starts writing from the second character" visual
            # glitch - the first keystroke lands, then gets visually
            # overwritten by a re-render that hasn't settled yet. A short
            # pause here lets that settle before we start typing.
            await self.page.wait_for_timeout(150)

        await self.page.keyboard.type(value, delay=100)
        await self.page.wait_for_timeout(150)

        # DIAGNOSTIC: settle whether keystrokes are landing intact. This
        # directly checks the "starts writing from the second character"
        # symptom you noticed live - if the box doesn't read exactly what we
        # typed, the backend search itself may be receiving a truncated
        # query (which would explain 'Information Technology' matching
        # nothing at all, and 'Software' only fuzzy-matching because a
        # truncated 'oftware' still happens to be a substring of it).
        if input_el is not None:
            actual_typed = (await input_el.input_value())
            if actual_typed != value:
                print(f"  [_add_tag_via_suggestion:{value!r}] WARNING: input reads {actual_typed!r} after typing, not the full value")

        # BUG FIX #2b/#2c: matching is now delegated to the shared
        # `_find_best_suggestion_match` helper (see its docstring) - this
        # used to be inline here with the exact same logic; extracting it
        # let the Degree Major/Subject field reuse it too instead of the
        # fragile page-wide lookup it had before.
        matched_text, matched_panel = await self._find_best_suggestion_match(
            value, log_label=f"_add_tag_via_suggestion:{value}"
        )

        if matched_text is None:
            # No suggestion rendered in the real panel - clear the field
            # completely (not a blind fixed-count backspace, which under-
            # corrects if the box holds more than we expect) so the raw text
            # can't bleed into whatever gets typed next.
            if input_el is not None:
                await input_el.click(force=True)
                await input_el.press("Control+A")
                await input_el.press("Backspace")
            else:
                for _ in range(len(value) + 3):
                    await self.page.keyboard.press("Backspace")
            raise RuntimeError(f"No autocomplete suggestion appeared for '{value}'")

        # BUG FIX #3b: the previous version selected via ArrowDown+Enter,
        # then - if that didn't visibly commit within 400ms - fell back to
        # re-resolving `option_locator.nth(target_index)` and clicking that.
        # That re-resolution is INDEX-based, so if the panel had re-rendered
        # or reordered in between (very plausible right after a keyboard
        # interaction with it), index N could now point at a DIFFERENT
        # option than the one we originally matched - a very likely
        # explanation for skills ending up with BOTH a plain tag ('django')
        # AND an unrelated compound one ('Python Django') for a single
        # requested skill. Simplify to one click site, targeted by the exact
        # MATCHED TEXT (not a position), so it can't silently drift to a
        # different element.
        #
        # BUG FIX #4 (this run - "skills chosen wrong again"): the OLD
        # fallback here was `target_option.click(force=True)`. force=True
        # only skips PLAYWRIGHT's own actionability checks (visible,
        # stable, not covered) - it does NOT change which element the real
        # browser click lands on. The browser always delivers a click to
        # whatever is topmost at those pixel coordinates, so if something
        # is genuinely overlapping the real option (confirmed elsewhere in
        # this file for the Additional Requirements button, caused by a
        # leftover Job Location overlay), a force click silently lands on
        # THAT interceptor instead. Clear known stray overlays and retry a
        # normal click instead of forcing through whatever's in the way.
        # BUG FIX #9 (this run - "goes to the right suggestion, highlights
        # it, but doesn't select it, then just moves on to the next skill"):
        # get_by_text(matched_text, exact=True) matches whichever element's
        # OWN text content is exactly matched_text - on a typeahead panel
        # that bolds the matching portion (e.g. "Python <b>Django</b>"),
        # that's very often the innermost <b>/<span> wrapping just that
        # substring, NOT the actual clickable row (a <button>/<li>/
        # [role='option']) the framework's click handler is bound to.
        # Clicking that decorative inner node should still bubble up to a
        # real (click) handler on the row - but if the row's real handler is
        # instead bound to (mousedown) (common in ng-bootstrap-style
        # typeaheads, which drive selection off an "active" item rather
        # than a plain click), or if a hover-triggered reflow shifts the
        # inner node's coordinates a few pixels after Playwright resolves
        # them, the click can land but never fire what actually commits the
        # tag - fully consistent with what you're seeing (the correct item
        # visibly highlights, then nothing happens). Climb from the matched
        # text up to its nearest interactive ancestor first, so the click
        # always targets the real option row rather than a label fragment.
        matched_node = matched_panel.get_by_text(matched_text, exact=True).first
        target_option = matched_node.locator(
            "xpath=ancestor-or-self::*[self::button or self::li or @role='option'][1]"
        ).first
        if await target_option.count() == 0:
            target_option = matched_node
        try:
            await target_option.click(timeout=5000)
        except Exception as click_err:
            print(f"  [_add_tag_via_suggestion:{value!r}] click on '{matched_text}' was intercepted ({click_err}); clearing overlays and retrying.")
            await self._dismiss_stray_overlays()
            await target_option.click(timeout=5000)

        # BUG FIX #4b (previous run): verifying success by "did the input go
        # blank" alone can't tell a genuine commit apart from a click that
        # silently missed - both look identical from the input's point of
        # view until something ELSE (e.g. a later, unrelated blur) causes
        # the widget to auto-resolve whatever's left.
        #
        # BUG FIX #5 (this run - "skills field ends up completely empty,
        # but nothing is reported as failed"): the #4b fix above checked
        # `container.inner_text()` for the target word, but the SAME
        # container that holds the committed chips ALSO holds the still-
        # open suggestion dropdown while it's rendering - and that dropdown
        # obviously already contains the word we're searching for (that's
        # the whole point of a suggestion list). So the check was passing
        # immediately, before any real commit happened, purely because it
        # was reading the dropdown's own option text back to itself. This
        # is why every skill logged as "successful" yet the field ended up
        # empty in the screenshot - the click never actually committed
        # anything, we just stopped checking for a real reason.
        # Fix: wait for the suggestion panel itself to close first, THEN
        # only look at actual chip elements (identified the same way
        # `_clear_existing_tags` finds them - by their own remove/× control)
        # for the target text, never the raw container text.
        committed = False
        if heading_text:
            try:
                await self.page.locator(
                    "ngb-typeahead-window:visible, [role='listbox']:visible, .dropdown-menu:visible"
                ).first.wait_for(state="hidden", timeout=3000)
            except Exception:
                pass  # already closed, or stuck open - check chips either way

            # BUG FIX #6 (previous run - "chip clearly visible on screen /
            # confirmed in screenshot, but logged as FAILED anyway"): the
            # version before this one located a remove/close icon inside the
            # chip, then walked up EXACTLY ONE parent (`xpath=..`) to read
            # that chip's text - too shallow for this widget's real markup,
            # which nests the close icon one level deeper. That produced
            # false FAILUREs.
            #
            # BUG FIX #7 (this run - the opposite problem: FALSE SUCCESS):
            # simplifying #6 to "does the whole container's text contain the
            # skill name" swung too far the other way - see the long comment
            # above `baseline_chip_texts` for why that container's text can
            # contain a skill's name from an entirely unrelated field.
            # `_get_chip_texts` (capped-climb version of the #6 approach)
            # plus this before/after diff fixes both problems at once: only
            # a genuinely NEW chip - not shallow-icon false negatives, not
            # unrelated-paragraph false positives - counts as committed.
            container = await self._get_tag_container(heading_text)
            target_lower = matched_text.lower()
            value_lower = value.lower()
            for _ in range(20):  # ~5s total - Angular's own re-render can lag
                await self.page.wait_for_timeout(250)
                current_chip_texts = await self._get_chip_texts(container)
                newly_added = current_chip_texts - baseline_chip_texts
                if any(target_lower in t or value_lower in t for t in newly_added):
                    committed = True
                    break
        elif input_el is not None:
            for _ in range(15):  # ~3s total (was 1.2s - too eager)
                await self.page.wait_for_timeout(200)
                if not (await input_el.input_value()).strip():
                    committed = True
                    break

        if not committed and heading_text:
            # BUG FIX #9b (fallback): if the click genuinely didn't commit
            # anything - not an interception (already retried above), just
            # a click that visually highlighted the right row and did
            # nothing else - this project already confirmed the site runs
            # on ng-bootstrap (the deadline picker is <ngb-datepicker>).
            # ng-bootstrap's typeahead selects its currently ACTIVE item via
            # the keyboard (Enter), independent of mouse clicks, and the
            # matched item was already the one visibly highlighted in your
            # screenshot - i.e. already "active" - before we ever touched
            # it. Try that native path once before giving up entirely.
            print(f"  [_add_tag_via_suggestion:{value!r}] click didn't commit; trying Enter as a fallback.")
            await self.page.keyboard.press("Enter")
            await self.page.wait_for_timeout(400)
            for _ in range(10):  # ~2.5s total
                await self.page.wait_for_timeout(250)
                current_chip_texts = await self._get_chip_texts(container)
                newly_added = current_chip_texts - baseline_chip_texts
                if any(target_lower in t or value_lower in t for t in newly_added):
                    committed = True
                    break

        if not committed:
            # Don't leave uncommitted text sitting in the field - as noted
            # above, that leftover text is exactly what caused a mismatched
            # chip to appear later on an unrelated action.
            if input_el is not None:
                await input_el.click(force=True)
                await input_el.press("Control+A")
                await input_el.press("Backspace")
            raise RuntimeError(
                f"Suggestion for '{value}' was found ('{matched_text}') and clicked, "
                f"but no matching chip appeared - no chip appears to have been committed."
            )

    async def fill_step_2_candidate_requirements(self, job_data: dict) -> bool:
        """Fills out the Candidate Requirements form (Step 2) using keyboard simulation.

        Each field group is wrapped independently (same philosophy as the Step 1
        step_sequence in main.py): a locator that fails to resolve - e.g. because
        a label carries a required-field '*' as part of its own text node, which
        breaks EXACT text='...' matching - logs and moves on instead of hanging
        for the full default timeout and aborting every field after it.
        """

        # Fail fast: if the wizard never actually left Step 1 (e.g. the Continue
        # click from Step 1 was swallowed by a still-open modal), NONE of the
        # fields below will ever be found. Rather than let each one time out
        # independently for a total of several minutes and then still report
        # success, check for a Step-2-only anchor once, up front, with a short
        # timeout, and raise clearly if it's missing.
        try:
            await self.page.get_by_text("Preferred Gender", exact=False).first.wait_for(
                state="visible", timeout=8000
            )
        except Exception as e:
            await self.page.screenshot(path="error_step2_not_loaded.png", full_page=True)
            raise RuntimeError(
                "Step 2 (Candidate Requirements) never loaded - none of its fields are "
                "on screen. This usually means the 'Continue' click at the end of Step 1 "
                "didn't actually advance the wizard (e.g. the Compensation & Benefits "
                "modal was still open and intercepted it). Saved error_step2_not_loaded.png."
            ) from e

        # 1. Preferred Gender
        if gender := job_data.get("gender"):
            try:
                # exact=False -> substring match, so a label rendered as
                # "Preferred Gender*" (required-field asterisk in the same text
                # node) still resolves. text='Preferred Gender' would not.
                label = self.page.get_by_text("Preferred Gender", exact=False).first
                await label.scroll_into_view_if_needed()
                await label.locator("xpath=..").click(force=True)
                await self.page.wait_for_timeout(500)
                await self.page.keyboard.type(gender, delay=100)
                await self.page.keyboard.press("Enter")
            except Exception as e:
                print(f"Step 2 - Preferred Gender FAILED: {e}")
                await self.page.screenshot(path="error_step2_gender.png", full_page=True)

        # 2. Age Limits
        if age := job_data.get("age"):
            if min_age := age.get("min"):
                try:
                    await self.page.get_by_text("Minimum age", exact=False).first.click(force=True)
                    await self.page.wait_for_timeout(500)
                    await self.page.keyboard.type(str(min_age), delay=100)
                    await self.page.keyboard.press("Enter")
                except Exception as e:
                    print(f"Step 2 - Minimum age FAILED: {e}")
                    await self.page.screenshot(path="error_step2_min_age.png", full_page=True)

            if max_age := age.get("max"):
                try:
                    await self.page.get_by_text("Maximum age", exact=False).first.click(force=True)
                    await self.page.wait_for_timeout(500)
                    await self.page.keyboard.type(str(max_age), delay=100)
                    await self.page.keyboard.press("Enter")
                except Exception as e:
                    print(f"Step 2 - Maximum age FAILED: {e}")
                    await self.page.screenshot(path="error_step2_max_age.png", full_page=True)

        # 3. Educational Qualification - THREE cascading controls, confirmed by
        # the earlier failure: get_by_text("Select Degree Level") resolved to
        # <option disabled hidden value="-1">Select Degree Level</option>,
        # which means this is a real native <select> (the hidden placeholder
        # option), not a custom dropdown - clicking the option itself throws
        # "Element is not visible" because it's the disabled/hidden placeholder.
        # The fix is the same select_option() approach already used for the
        # ngb-datepicker month/year controls in Step 1: target the <select>
        # itself, not text inside it.
        if degree_level := job_data.get("degree_level"):
            try:
                # BUG FIX ("subject still shows the same value across runs,
                # looks like it's choosing wrong again"): unlike Skills and
                # Preferred Industries, this Degree entry list never got its
                # own "start from empty" pass, even though the same root
                # cause applies here too - BDJobs persists this saved draft
                # across runs, so a chip a previous (including an older,
                # buggier) run already added just sits there. That made a
                # perfectly correct fresh pick indistinguishable from a
                # stale leftover, since both render as the same text. Clear
                # any existing Degree chip first so this run's result is
                # actually its own.
                await self._clear_existing_tags("Degree")

                degree_level_select = self.page.locator(
                    "xpath=//select[option[normalize-space(text())='Select Degree Level']]"
                ).first
                await degree_level_select.select_option(label=degree_level)
                await self.page.wait_for_timeout(500)

                # Choosing a level reveals a second cascading <select>, "Select
                # Degree Name" (options depend on the level just chosen - e.g.
                # "Bachelor of Science (BSc)" only appears once "Bachelor/Honors"
                # is selected, per the screenshots).
                if degree_name := job_data.get("education_level"):
                    degree_name_select = self.page.locator(
                        "xpath=//select[option[normalize-space(text())='Select Degree Name']]"
                    ).first
                    await degree_name_select.wait_for(state="visible", timeout=8000)
                    await degree_name_select.select_option(label=degree_name)
                    await self.page.wait_for_timeout(500)

                    # Choosing a degree name reveals a free-text Major/Subject
                    # field with a suggestion list (NOT a <select> - a typed
                    # search, same interaction pattern as Job Location in Step
                    # 1). We don't have a confirmed selector for its <input>
                    # (no DOM dump captured for it yet), so this targets the
                    # last visible text input in the Degree row as a best
                    # guess and fails loudly with a screenshot if that's wrong,
                    # rather than silently mis-typing into something else.
                    if degree_title := job_data.get("degree_title"):
                        major_input = self.page.locator(
                            "input[placeholder*='Search' i], "
                            "input[placeholder*='Major' i], "
                            "input[placeholder*='Subject' i], "
                            "input[placeholder*='Degree Name' i]"
                        ).first
                        if await major_input.count() == 0:
                            major_input = self.page.locator("input[type='text']:visible").last
                        await major_input.click(force=True)
                        await major_input.press("Control+A")
                        await major_input.press("Backspace")
                        await self.page.keyboard.type(degree_title, delay=100)
                        await self.page.wait_for_timeout(300)

                        # BUG FIX ("subject choose wrong" - recurring): this
                        # used to search the ENTIRE page with get_by_text(),
                        # first for an exact match of `degree_title` alone,
                        # then - since the real suggestion renders as a full
                        # compound label (e.g. "Bachelor of Science (BSc) in
                        # Computer Science & Engineering"), not the bare
                        # major name - falling back to get_by_text(first
                        # word, exact=False), which is free to match ANY
                        # element anywhere on the page containing that word,
                        # not just the genuine open suggestion. Use the same
                        # panel-scoped matcher already proven for
                        # Skills/Industries instead, so this can only ever
                        # pick a real, currently-open suggestion.
                        matched_text, matched_panel = await self._find_best_suggestion_match(
                            degree_title, log_label="degree_title"
                        )
                        if matched_text is None:
                            raise RuntimeError(
                                f"No autocomplete suggestion appeared for degree major '{degree_title}'"
                            )
                        suggestion = matched_panel.get_by_text(matched_text, exact=True).first
                        try:
                            await suggestion.click(timeout=5000)
                        except Exception:
                            await self._dismiss_stray_overlays()
                            await suggestion.click(timeout=5000)
                        await self.page.wait_for_timeout(300)

                # "+ Add Degree" appears to commit/append this entry (screenshots
                # show it enabled once a level+name are chosen). Best-effort only:
                # if it's not present or disabled, the level/name/major selections
                # above may already be saved live via their own change events, so
                # this doesn't raise on failure.
                add_degree_btn = self.page.get_by_text("Add Degree", exact=False).first
                if await add_degree_btn.count() > 0 and await add_degree_btn.is_enabled():
                    await add_degree_btn.click(force=True)
                    await self.page.wait_for_timeout(300)
            except Exception as e:
                print(f"Step 2 - Education Level FAILED: {e}")
                await self.page.screenshot(path="error_step2_education.png", full_page=True)

        # 4. Experience Requirements
        if exp := job_data.get("experience"):
            try:
                wants_experience = exp.get("required", True)
                toggle_text = "Experience Required" if wants_experience else "No Experience Required"

                # CRITICAL BUG FIX: get_by_text(toggle_text, exact=False) does
                # a SUBSTRING match, and "No Experience Required" itself
                # contains the substring "Experience Required" - so when
                # wants_experience is True, `.first` was ambiguous between
                # the two tab buttons and (per the last run's screenshot,
                # which showed "No Experience Required" highlighted as
                # active instead of "Experience Required") was landing on
                # the WRONG tab. That silently hid the whole Year of
                # Experience / Industry panel again, which explains the
                # "not visible" / "disabled" hangs on Minimum and Maximum
                # below, the industries widget looking wrong, AND is a
                # likely source of the reported screen flicker (the panel
                # toggling to a state nothing else in this method expects).
                # Fix: match a text NODE whose own content is EXACTLY the
                # target label - "No Experience Required" is a different
                # (longer) exact text node, so this can no longer collide.
                toggle = self.page.locator(
                    f"xpath=//text()[normalize-space()='{toggle_text}']/parent::*"
                ).first
                await toggle.wait_for(state="visible", timeout=8000)
                await toggle.scroll_into_view_if_needed()
                await toggle.click(force=True)
                await self.page.wait_for_timeout(800)

                # Best-effort confirmation this actually landed on the right
                # tab - not a hard assertion (we don't know the real
                # "active" class name), just a diagnostic so a wrong click
                # is visible in the log instead of silently cascading into
                # five more failures like last time.
                try:
                    active_class = await toggle.get_attribute("class") or ""
                    print(f"Experience toggle '{toggle_text}' clicked, class='{active_class}'")
                except Exception:
                    pass

                if wants_experience:
                    for label, key in (("Minimum", "min"), ("Maximum", "max")):
                        value = exp.get(key)
                        if not value:
                            continue
                        try:
                            # Confirmed via the last run's error log: this IS
                            # a real Angular reactive-form <select> (visible
                            # attributes included formcontrolname=
                            # "maximumExperience", the "disabled" attribute,
                            # and Bootstrap's "form-select" class) - but it
                            # can be visually hidden or marked disabled while
                            # its custom-styled wrapper is what the user
                            # actually sees, which is why
                            # scroll_into_view_if_needed()/select_option()
                            # hung waiting for "visible"/"enabled" states
                            # that this element may never reach through
                            # normal DOM interaction. Setting .value directly
                            # via JS and dispatching real 'change'/'input'
                            # events updates Angular's FormControl the same
                            # way a user's selection would, without needing
                            # Playwright's own visibility/enabled checks -
                            # and it also works on the (initially disabled)
                            # Maximum select once Minimum's change event has
                            # let Angular's cascade logic enable it.
                            field = self.page.locator(
                                f"xpath=//select[option[normalize-space(text())='{label}']]"
                            ).first
                            if await field.count() > 0:
                                result = await field.evaluate(
                                    """(el, wanted) => {
                                        const opts = Array.from(el.options);
                                        const match = opts.find(o => o.textContent.trim() === wanted)
                                            || opts.find(o => o.value === wanted);
                                        if (!match) {
                                            return { ok: false, options: opts.map(o => o.textContent.trim()) };
                                        }
                                        el.value = match.value;
                                        el.dispatchEvent(new Event('change', { bubbles: true }));
                                        el.dispatchEvent(new Event('input', { bubbles: true }));
                                        return { ok: true };
                                    }""",
                                    str(value),
                                )
                                if not result.get("ok"):
                                    raise RuntimeError(
                                        f"No option matching '{value}' in {label} select "
                                        f"(available: {result.get('options')})"
                                    )
                            else:
                                # Fall back to a typed/searchable combo box,
                                # same click-the-suggestion pattern as
                                # Skills/Industries, in case this control
                                # isn't a native <select> after all.
                                trigger = self.page.locator(
                                    f"xpath=//text()[normalize-space()='{label}']/parent::*"
                                ).first
                                await trigger.scroll_into_view_if_needed()
                                await trigger.click(force=True)
                                await self.page.wait_for_timeout(500)
                                await self.page.keyboard.type(str(value), delay=100)
                                await self.page.wait_for_timeout(800)
                                suggestion = self.page.get_by_text(str(value), exact=True).first
                                if await suggestion.count() > 0:
                                    await suggestion.click(force=True)
                                else:
                                    await self.page.keyboard.press("Enter")
                            await self.page.wait_for_timeout(400)
                        except Exception as e:
                            print(f"Step 2 - {label} Experience FAILED: {e}")
                            await self.page.screenshot(
                                path=f"error_step2_{key}_experience.png", full_page=True
                            )

                    if exp.get("freshers_can_apply"):
                        await self.page.get_by_text(
                            "Freshers can also apply", exact=False
                        ).first.click(force=True)
            except Exception as e:
                print(f"Step 2 - Experience Requirements FAILED: {e}")
                await self.page.screenshot(path="error_step2_experience.png", full_page=True)

        # 5. Preferred Industries (tag input with autocomplete).
        # BUG FIX: per the confirmed current screenshot, this field starts as
        # a plain "Add Industry" text input - there is no "Add more" trigger
        # to click first. The old code always clicked "Add more" before
        # typing, which either mis-clicked something unrelated or left focus
        # nowhere useful, so every industry typed landed with no suggestion.
        # Try the direct input first; only fall back to an "Add more" trigger
        # for slots after the first (some tag widgets on this site do reveal
        # that button only once one chip already exists).
        if industries := job_data.get("preferred_industries"):
            await self._clear_existing_tags("Which industry you prefer candidates to have experience")

            def industry_input_locator():
                return self.page.locator(
                    "input[placeholder*='Add Industry' i], input[placeholder*='Industry' i]"
                ).first

            for i, industry in enumerate(industries):
                try:
                    direct_input = industry_input_locator()
                    heading = "Which industry you prefer candidates to have experience"
                    if await direct_input.count() > 0:
                        await self._add_tag_via_suggestion(
                            industry, input_locator=industry_input_locator, heading_text=heading
                        )
                    else:
                        await self._add_tag_via_suggestion(
                            industry,
                            open_trigger=lambda: self.page.get_by_text("Add more", exact=False).first,
                            heading_text=heading,
                        )
                except Exception as e:
                    print(f"Step 2 - Preferred Industry '{industry}' FAILED: {e}")
                    safe_name = industry.lower().replace(" ", "_").replace("/", "_")
                    await self.page.screenshot(
                        path=f"error_step2_industry_{safe_name}.png", full_page=True
                    )

        # 6. Skills & Area of expertise (tag input with autocomplete).
        # BUG FIX: the previous version typed each skill and pressed Enter,
        # which never committed a chip - the widget requires clicking the
        # rendered suggestion instead. That's why the field ended up showing
        # every skill run together with no spaces ("PythonDjangoFastAPI
        # PostgreSQL") and "No skill found!": each Enter was a no-op, so the
        # next skill's keystrokes just kept appending to the same uncommitted
        # text.
        if skills := job_data.get("skills"):
            await self._clear_existing_tags("Skills & Area of expertise")

            def skills_input_locator():
                return self.page.locator(
                    "input[placeholder*='Add Skills' i], input[placeholder*='Skills' i]"
                ).first

            for skill in skills:
                try:
                    await self._add_tag_via_suggestion(
                        skill, input_locator=skills_input_locator,
                        heading_text="Skills & Area of expertise",
                    )
                except Exception as e:
                    print(f"Step 2 - Skill '{skill}' FAILED: {e}")
                    safe_name = skill.lower().replace(" ", "_").replace("/", "_")
                    await self.page.screenshot(
                        path=f"error_step2_skill_{safe_name}.png", full_page=True
                    )

        # 7. Additional Requirements (rich text editor inside a modal) - same
        # widget and Save/close-verification pattern as "Other Benefits" in
        # fill_compensation_and_benefits: walk forward in document order from
        # the modal's own heading so we land on THIS editor/Save button, not
        # some other hidden one elsewhere in the DOM.
        if extra_requirements := job_data.get("additional_requirements"):
            try:
                print("Step 2: opening Additional Requirements modal...")

                # BUG FIX (this run - "additional requirements still 0%"):
                # the DIAGNOSTIC DUMP confirmed the real button was found
                # correctly, and it also confirmed WHY clicking it never
                # opened the modal - a leftover `button.location-option`
                # element from Step 1's Job Location field was still
                # intercepting pointer events at that spot. The old
                # force=True fallback didn't help, because force=True only
                # skips PLAYWRIGHT's own actionability checks; it doesn't
                # change which element the real browser click is delivered
                # to, and the browser delivers it to whatever's topmost -
                # the same stray element, not the button underneath it.
                # Clear that away first.
                await self._dismiss_stray_overlays()

                open_btn_all = self.page.get_by_text("Add Additional Requirements", exact=False)
                btn_count = await open_btn_all.count()
                if btn_count != 1:
                    print(f"  NOTE: 'Add Additional Requirements' matched {btn_count} element(s), using the first.")
                open_btn = open_btn_all.first
                await open_btn.scroll_into_view_if_needed()

                try:
                    await open_btn.click(timeout=5000)
                except Exception as click_err:
                    print(f"  NOTE: normal click on 'Add Additional Requirements' failed ({click_err}); clearing overlays and retrying.")
                    await self._dismiss_stray_overlays()
                    try:
                        await open_btn.click(timeout=5000)
                    except Exception as click_err2:
                        print(f"  NOTE: retry also failed ({click_err2}); trying force click as a last resort.")
                        await open_btn.click(force=True)

                await self.page.wait_for_timeout(800)

                # BUG FIX: widen beyond Quill (.ql-editor) - we don't
                # actually know which rich-text library this specific modal
                # uses, and guessing a single class name twice hasn't held
                # up. Try the common alternatives, plus a plain <textarea>
                # in case this modal is simpler than Step 1's editors.
                editor = self.page.locator(
                    ".ql-editor:visible, [contenteditable='true']:visible, "
                    ".ProseMirror:visible, .tox-edit-area:visible, "
                    ".DraftEditor-root:visible, textarea:visible"
                ).last

                try:
                    await editor.wait_for(state="visible", timeout=8000)
                except Exception:
                    # DIAGNOSTIC: last run's dump came back completely empty
                    # ('[]') even for something as generic as 'textarea'
                    # across the WHOLE page - that points to the click not
                    # opening anything at all, rather than an editor-selector
                    # problem. This version also reports non-visible matches
                    # and a screenshot, so we can tell "genuinely nothing
                    # opened" apart from "opened but our isVisible() check is
                    # wrong" (e.g. animating in, zero-size wrapper, etc.).
                    dump = await self.page.evaluate("""
                    () => {
                        const isVisible = el => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
                        const sels = ['[role="dialog"]', '[class*="modal" i]', '[class*="popup" i]', '[class*="dialog" i]', 'ngb-modal-window', 'textarea', '[contenteditable]'];
                        const seen = new Set(), out = [];
                        for (const s of sels) document.querySelectorAll(s).forEach(el => {
                            if (!seen.has(el)) { seen.add(el); out.push({sel: s, visible: isVisible(el), html: el.outerHTML.slice(0, 500)}); }
                        });
                        return out;
                    }
                    """)
                    print(f"Step 2 - Additional Requirements DIAGNOSTIC DUMP ({len(dump)} elements, visible or not): {dump}")
                    await self.page.screenshot(path="diagnostic_additional_requirements_after_click.png", full_page=True)
                    print("Saved screenshot: diagnostic_additional_requirements_after_click.png")
                    raise RuntimeError(
                        "Additional Requirements editor never appeared - see "
                        "DIAGNOSTIC DUMP and screenshot above for the real modal structure."
                    )

                popup = editor.locator(
                    "xpath=ancestor::*[.//button[normalize-space(text())='Save'] "
                    "or .//*[@role='button'][normalize-space(text())='Save']][1]"
                ).first

                try:
                    await editor.click(timeout=5000)
                except Exception:
                    await editor.click(force=True)
                await self.page.keyboard.type(extra_requirements, delay=15)
                await self.page.wait_for_timeout(300)

                # Confirm the text actually landed before trying to save -
                # fail loudly here rather than clicking Save on an empty box.
                # contenteditable-style editors expose text via inner_text();
                # a plain <textarea> (now included since we widened the
                # selector) exposes it via input_value() instead - try both.
                typed_text = (await editor.inner_text()).strip()
                if not typed_text:
                    try:
                        typed_text = (await editor.input_value()).strip()
                    except Exception:
                        pass
                if not typed_text:
                    raise RuntimeError(
                        "Editor is still empty after typing - none of the "
                        "widened editor selectors matched the real editor "
                        "inside this modal."
                    )

                save_btn = popup.get_by_text("Save", exact=True).first
                await save_btn.click(force=True)

                try:
                    await editor.wait_for(state="hidden", timeout=5000)
                    print("Step 2: Additional Requirements modal confirmed closed.")
                except Exception:
                    print(
                        "WARNING: Additional Requirements modal may still be open after "
                        "clicking Save - this will likely block the next 'Continue' click."
                    )
                    await self.page.screenshot(
                        path="warning_additional_requirements_modal_still_open.png", full_page=True
                    )
            except Exception as e:
                print(f"Step 2 - Additional Requirements FAILED: {e}")
                await self.page.screenshot(path="error_step2_additional_requirements.png", full_page=True)

        return True

    async def fill_step_3_matching_restrictions(self, job_data: dict) -> bool:
        """Sets the three boolean 'Restrict' switches (Age / Gender / Years
        of experience) on the Matching & Restrictions step.

        These are plain on/off toggles, not text fields: bdjobs shows each
        one already OFF by default. Reads the corresponding key from
        `job_data` -
            "restrict_age", "restrict_gender", "restrict_experience"
        - and only ACTS when that value is truthy: flips the switch on and
        verifies it actually turned green. A False/missing key means "leave
        this switch exactly as the form already has it" - there's no
        legitimate reason for this automation to turn a switch OFF that the
        job data never asked it to touch, so falsy values are simply
        skipped rather than clicked.
        """
        restriction_map = {
            "Age": job_data.get("restrict_age"),
            "Gender": job_data.get("restrict_gender"),
            "Years of experience": job_data.get("restrict_experience"),
        }

        # BUG FIX #11 (this run - "Age never turns on, Gender/Years both
        # do, no error, no disabled flag"): the switch markup for the
        # failed Age click still showed Angular's "ng-untouched ng-pristine"
        # classes afterwards - meaning neither of our two click attempts
        # ever actually reached the real <input>, not that the input
        # rejected them. That's consistent with a transient overlay:
        # right after the Step 2 -> Step 3 transition, the "Applicant
        # Matching" panel (the "Strong" / "8/8" widget next to these
        # cards) is still animating/recalculating for a beat, and Age -
        # being the first card we touch, immediately after
        # wait_for_text="Applicant Restriction" resolves - is the one
        # most likely to still have something else on top of it at click
        # time. Gender and Years only worked because by the time we got
        # to them, Age's own ~800ms of retries had already run out the
        # clock on that transition. Waiting for the matching-strength
        # widget itself (not just the section heading) to be visible,
        # plus a short settle pause, gives the whole panel time to finish
        # rendering before ANY toggle is touched, regardless of order.
        try:
            await self.page.wait_for_selector(
                "text=/\\d\\s*/\\s*\\d/", state="visible", timeout=8000
            )
        except Exception:
            print(
                "Step 3 - matching-strength widget (e.g. '8/8') didn't show up "
                "in time; continuing anyway, but the overlay/timing issue this "
                "wait was meant to avoid may still bite."
            )
        await self.page.wait_for_timeout(500)

        for label, should_restrict in restriction_map.items():
            if not should_restrict:
                print(f"Step 3 - '{label}' restriction not requested, leaving switch as-is.")
                continue
            try:
                # BUG FIX #8 (this run - "only Years of experience actually
                # toggles; Age and Gender silently do nothing"): the old
                # `heading` lookup searched the ENTIRE page for exact text
                # '{label}' and took `.first`. The Step 3 summary panel
                # ABOVE these cards (confirmed in your screenshot) shows the
                # submitted criteria using the SAME bare words - a bold
                # "Age" label over "24-38 Years", a bold "Gender" label over
                # "Only Male" - and that panel sits earlier in the DOM than
                # the actual restriction cards. So `.first` kept grabbing
                # the summary panel's "Age"/"Gender" label (which has no
                # "Restrict" toggle anywhere near it) instead of the real
                # card. "Years of experience" only worked because the
                # summary panel phrases that one differently ("Total Year
                # of Experience"), so there was no collision for it.
                #
                # Fix: anchor to the "Applicant Restriction" section header
                # first (that heading is unique on the page), scope every
                # per-card lookup to ONLY the container below it, and only
                # THEN search for '{label}' - so the summary panel above can
                # never be matched at all, no matter what text it repeats.
                section = self.page.locator(
                    "xpath=//*[normalize-space(text())='Applicant Restriction']"
                    "/following::*[self::div][1]"
                ).first
                await section.wait_for(state="visible", timeout=8000)

                heading = section.locator(
                    f"xpath=.//*[normalize-space(text())='{label}']"
                ).first
                await heading.wait_for(state="visible", timeout=8000)
                # All three cards share the identical "Restrict" label text,
                # so within the section we still anchor to THIS card's own
                # heading, then walk up to the nearest ancestor that also
                # contains this card's own "Restrict" text - that keeps the
                # toggle lookup from grabbing a sibling card's switch.
                card = heading.locator(
                    "xpath=ancestor::*[.//text()[normalize-space()='Restrict']][1]"
                ).first

                toggle = card.locator(
                    "input[type='checkbox'], [role='switch'], "
                    "[class*='toggle' i], [class*='switch' i]"
                ).first
                await toggle.scroll_into_view_if_needed()

                # BUG FIX #10 (this run - "Gender and Years both turn on now,
                # Age still doesn't, no error is thrown"): the scoping fix
                # got every card's toggle correctly resolved, so this is a
                # different, Age-specific problem. Two real possibilities
                # that look identical from a print statement alone: (a) this
                # particular switch is disabled client-side for some reason
                # (a disabled native checkbox silently ignores a
                # force=True click - force=True only skips PLAYWRIGHT's own
                # checks, it can't make a genuinely disabled control
                # respond), or (b) the click is landing on the switch TRACK
                # div rather than the actual <input>, and this specific
                # card's click handler happens to be bound to the visible
                # "Restrict" text/label instead (a very common pattern:
                # <label><input type=checkbox hidden><span>Restrict</span>
                # </label>, where clicking the checkbox track directly does
                # nothing but clicking the label text delegates to the
                # input). Check for (a) explicitly first so it's not
                # confused with (b), then try the label-text click as a
                # second attempt before giving up.
                is_disabled = False
                try:
                    is_disabled = await toggle.is_disabled()
                except Exception:
                    pass
                aria_disabled = (await toggle.get_attribute("aria-disabled")) or ""
                if is_disabled or aria_disabled.lower() == "true":
                    print(
                        f"Step 3 - '{label}' restriction switch is DISABLED on the page "
                        f"itself (is_disabled={is_disabled}, aria-disabled={aria_disabled!r}). "
                        f"bdjobs is blocking this toggle client-side - this is not something "
                        f"clicking harder will fix; the form likely requires some other "
                        f"precondition to be met first. Skipping."
                    )
                    await self.page.screenshot(
                        path=f"warning_step3_restrict_{label.lower().replace(' ', '_')}_disabled.png",
                        full_page=True,
                    )
                    continue

                # Some of these custom switches expose real checkbox state
                # (is_checked works); others are just a styled <div>/<span>
                # with an "active"/"checked"/"on" class instead - fall back
                # to a class-name check rather than assuming one or the
                # other and failing outright.
                async def _read_toggle_state():
                    try:
                        return await toggle.is_checked()
                    except Exception:
                        css_class = (await toggle.get_attribute("class") or "").lower()
                        return any(marker in css_class for marker in ("active", "checked", "-on", " on"))

                if await _read_toggle_state():
                    print(f"Step 3 - '{label}' restriction already ON, leaving as is.")
                    continue

                await toggle.click(force=True)
                await self.page.wait_for_timeout(400)

                # Verify the click actually flipped it - same "don't trust a
                # click blindly" philosophy used everywhere else in this
                # file (deadline calendar, compensation modal, etc.).
                confirmed_on = await _read_toggle_state()

                if not confirmed_on:
                    # Fallback attempt: click the visible "Restrict" label
                    # text within this same card instead of the switch
                    # element itself - see BUG FIX #10 above for why that
                    # can succeed where clicking the switch track doesn't.
                    print(f"Step 3 - '{label}' restriction: switch click didn't register; trying the 'Restrict' label text instead.")
                    restrict_label = card.get_by_text("Restrict", exact=True).first
                    if await restrict_label.count() > 0:
                        await restrict_label.click(force=True)
                        await self.page.wait_for_timeout(400)
                        confirmed_on = await _read_toggle_state()

                if not confirmed_on:
                    # BUG FIX #11 (continued): both attempts above are
                    # mouse-based clicks - Playwright's force=True skips
                    # ITS OWN actionability checks, but the click is still
                    # dispatched at the element's on-screen coordinates,
                    # so a transient overlay physically on top of the
                    # switch at that pixel can still swallow it (this is
                    # exactly what the still-"ng-untouched ng-pristine"
                    # class list on Age pointed to). A native JS
                    # el.click() has no such blind spot - it calls the
                    # DOM click() method directly, with no dependency on
                    # screen position, so it lands on the real <input>
                    # regardless of what's visually stacked above it.
                    print(f"Step 3 - '{label}' restriction: label click didn't register either; trying a native JS click.")
                    try:
                        await toggle.evaluate("el => el.click()")
                    except Exception as js_click_err:
                        print(f"Step 3 - '{label}' restriction: native JS click raised {js_click_err}")
                    await self.page.wait_for_timeout(400)
                    confirmed_on = await _read_toggle_state()

                if confirmed_on:
                    print(f"Step 3 - '{label}' restriction turned ON.")
                else:
                    # Dump the actual markup so the real cause (a third,
                    # not-yet-considered possibility) is visible instead of
                    # guessed at next time.
                    try:
                        toggle_html = await toggle.evaluate("el => el.outerHTML")
                    except Exception as dump_err:
                        toggle_html = f"<could not read outerHTML: {dump_err}>"
                    print(
                        f"Step 3 - '{label}' restriction WARNING: clicked the switch (and its "
                        f"label) but couldn't confirm it turned on. Switch markup:\n{toggle_html}"
                    )
                    await self.page.screenshot(
                        path=f"warning_step3_restrict_{label.lower().replace(' ', '_')}.png",
                        full_page=True,
                    )
            except Exception as e:
                print(f"Step 3 - '{label}' restriction FAILED: {e}")
                safe_name = label.lower().replace(" ", "_")
                await self.page.screenshot(path=f"error_step3_restrict_{safe_name}.png", full_page=True)

        return True