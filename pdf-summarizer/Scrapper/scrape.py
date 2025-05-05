import asyncio
import os
import time
import logging
import shutil
import calendar
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
from datetime import datetime

# --- Configuration ---
ARCHIVE_URL = "https://archive.pib.gov.in/"
OUTPUT_DIR = "pib_archive_pdfs"  # Main directory for date-wise folders
COLLECTIVE_OUTPUT_DIR = "pib_archive_pdfs_collective" # Directory for all PDFs together
BASE_PRINT_URL = "https://archive.pib.gov.in/newsite/PrintRelease.aspx?relid=" # Base URL for print view

# --- Date Range ---
START_YEAR = 2004
CURRENT_YEAR = datetime.now().year
END_YEAR = CURRENT_YEAR # Scrape up to the current year

# --- Concurrency Settings ---
# Number of PDF downloads to run in parallel per YEAR.
# Increase cautiously! High values stress the server and your machine.
# Start maybe around 100-200 and monitor.
CONCURRENCY_LIMIT = 1000 # ADJUST THIS CAREFULLY!

# --- Delays ---
# Delay after processing all releases for one YEAR, before starting the next year (in seconds)
# Can be low or 0 if confident about stability.
YEAR_PROCESS_DELAY = 5 # Short delay between years

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(name)

# --- Helper Functions ---
async def save_page_as_pdf(page, relid, year, month, day):
    """Saves the provided page object (assumed print view) as PDF to both date-wise and collective folders."""
    saved_to_date_folder = False
    pdf_path = None # Initialize pdf_path
    try:
        # --- Define PDF path (Date-wise) ---
        month_str = str(month).zfill(2)
        day_str = str(day).zfill(2)
        pdf_dir = os.path.join(OUTPUT_DIR, str(year), month_str)
        os.makedirs(pdf_dir, exist_ok=True)
        pdf_filename = f"PIB_{relid}{year}{month_str}_{day_str}.pdf"
        pdf_path = os.path.join(pdf_dir, pdf_filename)

        # --- Check if PDF already exists in collective folder (Primary Check) ---
        # Optimization: If it exists in the collective folder, we assume it also
        # exists (or should exist) in the date-wise folder, saving a check and copy.
        collective_pdf_path = os.path.join(COLLECTIVE_OUTPUT_DIR, pdf_filename)
        if os.path.exists(collective_pdf_path):
            logger.info(f"PDF already exists in collective folder: {pdf_filename}. Skipping download and copy.")
            return False # Not newly saved

        # --- Check if PDF exists in date-wise folder (Secondary Check) ---
        # This handles cases where it might exist date-wise but not collectively (e.g., interrupted run)
        if os.path.exists(pdf_path):
            logger.info(f"PDF exists in date folder but not collective: {pdf_filename}. Copying.")
            try:
                shutil.copy2(pdf_path, collective_pdf_path)
                logger.info(f"Successfully copied PDF to collective folder.")
            except Exception as e_copy:
                logger.error(f"Error copying existing date-wise {pdf_filename} to collective folder: {e_copy}")
            return False # Not newly saved


        # --- Download and Save PDF ---
        logger.info(f"Saving PDF: {pdf_path} (Relid: {relid})")
        await page.wait_for_load_state('domcontentloaded', timeout=60000)
        # Shorter timeout after load, maybe page is just rendering slow
        await page.wait_for_timeout(500) # Reduced timeout

        # Inject CSS to hide elements
        print_element_selector = "div[onclick=\"rprint()\"]"
        close_element_selector = "div[onclick=\"wclose()\"]"
        css_to_hide = f"""
        {print_element_selector}, {close_element_selector} {{
            display: none !important; visibility: hidden !important;
        }}"""
        try:
            await page.add_style_tag(content=css_to_hide)
        except Exception as e_css:
            logger.warning(f"Could not apply CSS to hide elements for relid {relid}: {e_css}")

        pdf_margins = {'top': '1cm', 'right': '1cm', 'bottom': '1cm', 'left': '1cm'}
        # Increased PDF generation timeout
        await page.pdf(path=pdf_path, format='A4', print_background=True, margin=pdf_margins, timeout=90000)
        logger.info(f"Successfully saved PDF to date folder: {pdf_filename}")
        saved_to_date_folder = True

        # --- Copy to Collective Folder ---
        # Only copy if it was newly saved
        if saved_to_date_folder:
            try:
                logger.info(f"Copying {pdf_filename} to {COLLECTIVE_OUTPUT_DIR}")
                shutil.copy2(pdf_path, collective_pdf_path) # copy2 preserves metadata
                logger.info(f"Successfully copied PDF to collective folder.")
            except Exception as e_copy:
                logger.error(f"Error copying newly saved {pdf_filename} to collective folder: {e_copy}")
                # Consider if you want to return False here if the copy fails

        return saved_to_date_folder # Return True only if newly saved

    except PlaywrightTimeoutError as e_timeout:
        logger.error(f"Timeout error saving PDF for relid {relid} from {page.url}: {e_timeout}")
    except Exception as e:
        logger.error(f"Error saving PDF for relid {relid} from {page.url}: {e}", exc_info=False) # Less verbose traceback for common errors
    return False # Indicate failure or skip

async def process_single_release(semaphore, context, release_info):
    """
    Opens print view URL for a single release_info (dict), saves PDF, closes tab.
    Uses a semaphore to limit concurrency.
    """
    relid = release_info['relid']
    year = release_info['year']
    month = release_info['month']
    day = release_info['day']

    async with semaphore: # Acquire semaphore before starting
        # Short delay before starting each task to slightly stagger requests
        await asyncio.sleep(0.1)
        logger.debug(f"Starting processing for relid: {relid} ({year}-{month:02d}-{day:02d})")
        print_view_url = f"{BASE_PRINT_URL}{relid}"
        print_page = None
        saved = False
        try:
            # --- Open Print View URL in New Tab ---
            logger.debug(f"Opening print view URL in new tab: {print_view_url}")
            print_page = await context.new_page()
            # Increased navigation timeout for individual pages
            await print_page.goto(print_view_url, wait_until="domcontentloaded", timeout=120000) # Increased timeout
            logger.debug(f"New print view page loaded: {print_page.url}")

            # --- Save the new page as PDF ---
            saved = await save_page_as_pdf(print_page, relid, year, month, day)

        except PlaywrightTimeoutError as e_timeout:
             logger.error(f"Timeout processing print view URL for relid: {relid}. URL: {print_view_url}. Error: {e_timeout}")
        except Exception as e_item:
             logger.error(f"Error processing print view URL for relid: {relid}: {e_item}", exc_info=False) # Less verbose traceback
        finally:
            # --- Close the new page/tab ---
            if print_page and not print_page.is_closed():
                logger.debug(f"Closing print view page for relid: {relid}")
                await print_page.close()
                logger.debug(f"Print view page closed for relid: {relid}")
            else:
                logger.debug(f"Print view page already closed or failed to open for relid: {relid}")


        logger.debug(f"Finished processing for relid: {relid}. Newly Saved: {saved}")
        # Semaphore is released automatically when exiting 'async with' block
        return saved # Return status


# --- Main Scraping Logic ---
async def main():
    overall_start_time = time.time()
    playwright = None
    browser = None
    context = None

    try:
        playwright = await async_playwright().start()
        # Consider using firefox or webkit if chromium causes issues, though chromium is generally robust.
        browser = await playwright.chromium.launch(headless=True) # Headless True for normal runs
        context = await browser.new_context(
            # Increase default navigation timeout for the main page interactions
            navigation_timeout=90000,
             # Set viewport if necessary, though likely not needed for this site
             # viewport={'width': 1920, 'height': 1080}
        )
        # Increase the overall timeout for actions on the main page
        context.set_default_timeout(45000) # Default timeout for actions like click, select_option

        page = await context.new_page() # Main page for navigation

        logger.info(f"Navigating to {ARCHIVE_URL}")
        await page.goto(ARCHIVE_URL, wait_until='domcontentloaded') # Use context default timeout

        # --- Click 'English Releases' ---
        logger.info("Clicking 'English Releases'")
        english_releases_selector = 'a:has-text("English Releases")'
        try:
            await page.locator(english_releases_selector).first.click()
            await page.wait_for_load_state('domcontentloaded') # Use context default timeout
            logger.info("Navigated to English Releases page.")
        except PlaywrightTimeoutError:
             logger.error("Timeout waiting for English Releases page to load or link not found.")
             return # Exit early if fundamental navigation fails
        except Exception as e_eng:
             logger.error(f"Error clicking English Releases: {e_eng}")
             return # Exit early

        # --- Date Iteration ---
        today = datetime.now().date()

        for year in range(START_YEAR, END_YEAR + 1):
            year_start_time = time.time()
            logger.info(f"=========== Starting Year: {year} ===========")
            releases_for_year = [] # Store {'relid': ..., 'year': ..., 'month': ..., 'day': ...}

            # --- Phase 1: Collect all Release IDs for the year ---
            logger.info(f"--- Phase 1: Collecting Release IDs for {year} ---")
            collection_errors = 0
            for month in range(1, 13):
                days_in_month = calendar.monthrange(year, month)[1]
                for day in range(1, days_in_month + 1):
                    current_processing_date = datetime(year, month, day).date()
                    if current_processing_date > today:
                        logger.info(f"Skipping future date: {current_processing_date.strftime('%Y-%m-%d')}")
                        continue # Skip to the next iteration

                    logger.debug(f"Collecting IDs for Date: {year}-{month:02d}-{day:02d}")

                    try:
                        # --- Select Date ---
                        # Make sure selectors are correct and robust
                        day_selector = "select[name='ctl00$ContentPlaceHolder1$dday']" # Often name is more stable
                        month_selector = "#rmonthID" # Assuming ID is stable
                        year_selector = "#ryearID"  # Assuming ID is stable

                        # Use page.select_option with reliable selectors
                        await page.select_option(year_selector, str(year))
                        # Add small waits ONLY IF NEEDED for dynamic content loading after selection
                        # await page.wait_for_timeout(100) # Minimal wait if UI updates dynamically
                        await page.select_option(month_selector, str(month))
                        # await page.wait_for_timeout(100)
                        await page.select_option(day_selector, str(day))
                        # A slightly longer wait after the final selection might be needed for the results to load
                        await page.wait_for_timeout(500) # Wait for potential JS updates

                        # --- Wait for Results Area & Extract IDs ---
                        results_area_selector = "#lreleaseID" # Assuming ID is stable
                        release_item_selector = f"{results_area_selector} li.rel-list[id]"
                        no_releases_selector = f'{results_area_selector} :text-matches("No releases found|No record found", "i")'

                        # Wait for either the list of releases or the "no releases" message
                        await page.wait_for_selector(f"{release_item_selector}, {no_releases_selector}", state='visible', timeout=30000) # Shorter wait ok here?

                        # Check if "no releases" is visible
                        no_releases_element = page.locator(no_releases_selector)
                        if await no_releases_element.count() > 0 and await no_releases_element.is_visible():
                             logger.debug(f"No releases found for {year}-{month:02d}-{day:02d}.")
                        else:
                            # Extract IDs if releases are found
                            release_items = await page.locator(release_item_selector).all()
                            if release_items:
                                logger.debug(f"Found {len(release_items)} release items for {year}-{month:02d}-{day:02d}.")
                                for item in release_items:
                                    item_id = await item.get_attribute('id')
                                    if item_id and item_id.isdigit():
                                        releases_for_year.append({
                                            'relid': item_id,
                                            'year': year,
                                            'month': month,
                                            'day': day
                                        })
                                    else:
                                        logger.warning(f"Found release item without a valid ID attribute: {await item.inner_html()}")
                            else:
                                # This case might happen if the wait logic is slightly off or the page is inconsistent
                                logger.warning(f"Results area present but no specific release items (li.rel-list[id]) found for {year}-{month:02d}-{day:02d}.")


                    except PlaywrightTimeoutError:
                        logger.error(f"Timeout error collecting IDs for {year}-{month:02d}-{day:02d}. Skipping date.")
                        collection_errors += 1
                        # Attempt to recover by reloading? Maybe too risky. Continue is safer.
                        # await page.reload(wait_until="domcontentloaded") # Optional: attempt reload
                    except Exception as e_date:
                        logger.error(f"Error collecting IDs for date {year}-{month:02d}-{day:02d}: {e_date}", exc_info=False)
                        collection_errors += 1
                        # Optional: attempt reload after unknown error
                        # try:
                        #     await page.reload(wait_until="domcontentloaded")
                        # except Exception as reload_err:
                        #      logger.error(f"Failed to reload page after error: {reload_err}")

            logger.info(f"--- Phase 1 Finished for {year}: Collected {len(releases_for_year)} release IDs. Encountered {collection_errors} date collection errors. ---")

            # --- Phase 2: Process collected releases for the year ---
            if releases_for_year:
                logger.info(f"--- Phase 2: Processing {len(releases_for_year)} PDFs for {year} with concurrency {CONCURRENCY_LIMIT} ---")
                pdf_start_time = time.time()
                semaphore = asyncio.Semaphore(CONCURRENCY_LIMIT)
                tasks = [
                    process_single_release(semaphore, context, release_info)
                    for release_info in releases_for_year
                ]
                results = await asyncio.gather(*tasks, return_exceptions=True)

                # Log results/errors for the year's batch
                success_count = 0
                fail_count = 0
                skipped_count = 0 # Count those skipped because they already existed
                for i, result in enumerate(results):
                    relid = releases_for_year[i]['relid'] # Get relid for logging
                    if isinstance(result, Exception):
                        logger.error(f"PDF Task for relid {relid} failed: {result}")
                        fail_count += 1
                    elif result is True: # Explicitly check for True (newly saved)
                        success_count += 1
                    elif result is False: # Explicitly check for False (skipped or failed within save_page_as_pdf)
                         skipped_count += 1
                         # Note: save_page_as_pdf logs specific errors/skips

                pdf_end_time = time.time()
                logger.info(f"--- Phase 2 Finished for {year}. Time: {pdf_end_time - pdf_start_time:.2f}s. "
                            f"Successful new saves: {success_count}, Skipped/Existing: {skipped_count}, Failures: {fail_count} ---")
            else:
                logger.info(f"No releases found or collected for {year}. Skipping PDF processing phase.")

            # --- Delay before processing next year ---
            year_end_time = time.time()
            logger.info(f"=========== Finished Year: {year} in {year_end_time - year_start_time:.2f} seconds. ===========")
            if year < END_YEAR: # Add delay unless it's the very last year
                 logger.info(f"Waiting {YEAR_PROCESS_DELAY} seconds before starting year {year + 1}...")
                 await asyncio.sleep(YEAR_PROCESS_DELAY)

    except Exception as e_main:
        logger.critical(f"An unexpected critical error occurred in main loop: {e_main}", exc_info=True)
    finally:
        logger.info("Closing browser and playwright...")
        if context:
            try:
                await context.close()
            except Exception as e_ctx:
                logger.error(f"Error closing context: {e_ctx}")
        if browser:
            try:
                await browser.close()
            except Exception as e_br:
                logger.error(f"Error closing browser: {e_br}")
        if playwright:
             try:
                 await playwright.stop()
             except Exception as e_pw:
                 logger.error(f"Error stopping playwright: {e_pw}")

        overall_end_time = time.time()
        logger.info(f"Script finished. Total execution time: {overall_end_time - overall_start_time:.2f} seconds.")


if name == "main":
    # Ensure both output directories exist
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(COLLECTIVE_OUTPUT_DIR, exist_ok=True)
    # Run the async main function
    asyncio.run(main())