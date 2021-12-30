import os
import zipfile
from glob import glob
import selenium.common.exceptions
from selenium import webdriver
# from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
import random
import time
import traceback
from datetime import datetime
from bs4 import BeautifulSoup
import common
import downloader


class Constants:
    TOO_YOUNG_DAY = 1
    TOO_OLD_DAY = 3
    SCANNING_SPAN = 2
    STARTING_PAGE = 1

    ROOT_DOMAIN = common.read_from_file('HI_ROOT.pv')
    SUBDIRECTORIES = common.build_tuple_of_tuples('HI_SUBDIRECTORIES.pv')

    DESTINATION_PATH = common.Constants.DOWNLOAD_PATH
    TMP_DOWNLOAD_PATH = common.read_from_file('HI_DOWNLOAD_PATH.pv')
    LOG_PATH = common.read_from_file('HI_LOG_PATH.pv')


def log(message: str, has_tst: bool = True):
    path = Constants.LOG_PATH
    common.log(message, path, has_tst)


def __get_date_difference(tst_str: str) -> int:
    if ',' in tst_str:
        try:
            tst = datetime.strptime(tst_str, '%b %d, %Y, %I:%M %p')  # Oct 21, 2021, 3:10 AM
            return (datetime.now() - datetime(tst.year, tst.month, tst.day)).days
        except Exception as tst_exception:
            print('Error: %s.' % tst_exception)
    else:  # Assuming '2011년 10월 3일'
        try:
            chunks = tst_str.split(' ')
            y = int(chunks[0].strip('년'))
            m = int(chunks[1].strip('월'))
            d = int(chunks[2].strip('일'))
            return (datetime.now() - datetime(y, m, d)).days
        except Exception as tst_exception:
            print('Error: %s.' % tst_exception)


def initiate_browser():
    # A Chrome web driver with headless option
    # service = Service(common.Constants.DRIVER_PATH)
    options = webdriver.ChromeOptions()
    options.add_experimental_option("prefs", {
        "download.default_directory": Constants.TMP_DOWNLOAD_PATH,
        "download.prompt_for_download": False
    })
    options.add_argument('--proxy-server=socks5://127.0.0.1:9050')
    options.add_argument('headless')
    # options.add_argument('disable-gpu')
    driver = webdriver.Chrome(executable_path=common.Constants.DRIVER_PATH, options=options)
    driver.set_page_load_timeout(120)
    return driver


def element_exists_by_class(driver: webdriver.Chrome, class_name: str) -> bool:
    try:
        driver.find_element(By.CLASS_NAME, class_name)
    except selenium.common.exceptions.NoSuchElementException:
        return False
    return True


def mark_and_move(current_path: str, destination_path: str):
    for file in os.listdir(current_path):
        os.rename(current_path + file, destination_path + 'err-' + file)


def try_access_page(driver: webdriver.Chrome, url: str, trial: int = 2):
    for i in range(trial):
        try:
            driver.get(url)
            break
        except selenium.common.exceptions.TimeoutException:
            # It happens occasionally. Just try again.
            log('Warning: Timeout reached while trying loading the article.')
        except selenium.common.exceptions.WebDriverException as load_exception:
            common.pause_briefly(40, 80)
            log('Warning: Cannot access the page.(%s)' % load_exception)
    else:
        log('Error: Failed to load the article.')
        return False
    return True


def scan_article(url: str, tag_name: str = None):
    min_thumbnail_count = 1

    # Start a new session because clicking Download button companies irritating pop-ups
    article_browser = initiate_browser()
    log('Processing %s' % url)

    # A temporary folder to store the zip file.
    common.check_dir_exists(Constants.TMP_DOWNLOAD_PATH)

    # Load the article.
    page_load_start_time = datetime.now()
    try:
        is_on_page = try_access_page(article_browser, url)
        if not is_on_page:
            article_browser.quit()
            return False
        loading_sec = common.get_elapsed_sec(page_load_start_time)

        # Exclude short ones.
        soup = BeautifulSoup(article_browser.page_source, common.Constants.HTML_PARSER)
        thumbnail_count = len(soup.select('ul.thumbnail-list > li'))
        if thumbnail_count < min_thumbnail_count:
            log('Too short(%d images), skipping.' % thumbnail_count)
            return True

        # Click the download button to start download script.
        download_start_time = datetime.now()
        download_successful = click_download_button(article_browser, loading_sec)
        downloading_sec = common.get_elapsed_sec(download_start_time)

        time_report = 'Page loading: %.0f" / Downloading: %.1f\'' % (loading_sec, (downloading_sec / 60))
        article_browser.quit()
    except Exception as scan_article_exception:
        log('Warning: Cannot process the article.(%s)' % scan_article_exception)
        article_browser.quit()
        return False

    if download_successful:
        log('Download finished.(%s)' % time_report)
        __move_downloaded_file(tag_name)
        return True
    else:
        log('Warning: Download failed.(%s)' % time_report)
        if len(os.listdir(Constants.TMP_DOWNLOAD_PATH)) > 0:
            mark_and_move(Constants.TMP_DOWNLOAD_PATH, Constants.DESTINATION_PATH)
            log('Error: Files left after download failure.')
        return False  # Nothing to do.


# Process the downloaded zip file.
def __move_downloaded_file(tag_name: str):
    try:
        # Unzip the downloaded file.
        zip_files = glob(Constants.TMP_DOWNLOAD_PATH + '*.zip')
        for zip_file_path in zip_files:
            with zipfile.ZipFile(zip_file_path, 'r') as zip_ref:
                # Compose the destination path name.
                dir_name = zip_file_path.split('.zip')[0].split('/')[-1].split('|')[-1]\
                    .strip('_').split('_')[-1].strip()
                for prohibited_char in common.Constants.PROHIBITED_CHARS:
                    dir_name = dir_name.replace(prohibited_char, '_')

                # Add the file count.
                file_count = len(zip_ref.namelist())
                dir_name = '%03d-' % file_count + dir_name

                # Add the tag name at the head.
                if tag_name:
                    dir_name = tag_name + '-' + dir_name

                # Extract all to the composed destination path.
                destination = Constants.DESTINATION_PATH + dir_name + '/'
                zip_ref.extractall(destination)
            os.remove(zip_file_path)  # Remove the zip file.
    except Exception as post_download_exception:
        log('Error: Cannot process downloaded files.(%s)' % post_download_exception)


def wait_for_download_start(dl_browser: webdriver.Chrome, loading_sec: float):
    seconds = 0
    check_interval = 5
    progress_bar_id = 'progressbar'
    progress_value_attr = 'aria-valuenow'

    # The timeout: 30 ~ 3300 + a
    timeout = max(30.0, loading_sec * 300)  # Generous, as a stalled script will return False anyway.
    if timeout > 3300:
        timeout = 3300 * random.uniform(1, 1.2)

    # Is progress bar changing?
    prev_progress = 0
    has_started = False

    dl_btn = dl_browser.find_element(By.ID, progress_bar_id)
    consecutive_failures = 0
    while seconds <= timeout:
        time.sleep(check_interval)
        seconds += check_interval
        is_download_btn_visible = dl_btn.get_attribute('style')
        if not is_download_btn_visible:  # Not visible: download ongoing.
            # Set up the start flag and progress value
            if not has_started:
                has_started = True
            if dl_btn.get_attribute(progress_value_attr):
                progress = float(dl_btn.get_attribute(progress_value_attr))
            else:
                progress = 0.0

            # Check the progress
            if progress > prev_progress:  # Download ongoing
                print('Download script progress %.1f ' % progress + '%\t' + '(%d/%d)' % (seconds, timeout))
                consecutive_failures = 0
            else:
                if consecutive_failures < 10:
                    print('Download script progress %.1f ' % progress + '%\t' +
                          '(%d/%d)\t(STALLED)' % (seconds, timeout))
                    consecutive_failures += 1
                else:  # i.e., 10 consecutive failures.
                    log('Warning: Download progress stopped.')
                    return False  # It is certain that download stopped.
        elif has_started:
            return True  # Download button visible again. Finished downloading.
        # else: Download has not started. Wait to start download.
    log('Warning: Download script timeout.')
    return False  # Timeout reached.


def click_download_button(dl_browser: webdriver.Chrome, loading_sec: float) -> bool:
    btn_id = 'dl-button'
    # Part 1. Wait to start downloading.
    try:
        dl_browser.find_element(By.ID, btn_id).click()
        print('"Download" button located.')
        has_started = wait_for_download_start(dl_browser, loading_sec)
    except selenium.common.exceptions.NoSuchElementException:
        log('Warning: Cannot locate the download button.')
        return False  # Failed in clicking the download button. Nothing to expect.
    except Exception as download_btn_exception:
        if 'click intercepted' in str(download_btn_exception):
            log('Warning: Download button click intercepted.')
        else:
            log('Error: Download button exception\n%s' % download_btn_exception)
        return False  # Something went wrong trying 'Download'
    if not has_started:
        return False

    # Download started and it did not encounter exceptions.
    # Part 2. Wait to finish downloading.
    is_finished = downloader.wait_finish_downloading(Constants.TMP_DOWNLOAD_PATH, Constants.LOG_PATH, loading_sec, 1,
                                                     is_logged=False)
    if is_finished:
        return True
    else:
        log('Warning: crdownload timeout.')
        return False


def append_articles_to_scan(scan_list: [], placeholder: str, domain_tag, scanning_span: int, page: int = 1) -> []:
    max_page = page + scanning_span - 1  # To prevent infinite looping
    consecutive_failures = 0
    MAX_FAILURE = 3

    while page <= max_page and consecutive_failures < MAX_FAILURE:  # Page-wise
        start_time = datetime.now()  # A timer for monitoring performance
        url = placeholder + str(page)

        is_on_page = try_access_page(browser, url)
        if not is_on_page:
            consecutive_failures += 1
            page += 1
            # Tried, but didn't reach. Move on to the next page.
            break

        for i in range(3):
            soup = BeautifulSoup(browser.page_source, common.Constants.HTML_PARSER)
            rows = soup.select('div.container > div.gallery-content > div')
            if len(rows) > 0:
                break  # Article list has been loaded.
            else:  # Reload the page.
                log('Warning: Cannot load page %d.' % page)
                browser.get(url)
        else:
            consecutive_failures += 1
            log('Error: Cannot load page %d. Move to the next page.' % page)
            page += 1
            continue  # Move on to the next page.

        for i, row in enumerate(rows):  # Inspect the rows
            try:
                tst_str = row.select_one('div > div > p.date').string  # 2021-09-19 23:47:42
                day_diff = __get_date_difference(tst_str)
                if day_diff:
                    if day_diff <= Constants.TOO_YOUNG_DAY:  # Still, not mature: uploaded on the yesterday.
                        print('#%02d | Skipping the too young.' % (i + 1))
                        continue  # Move to the next row
                    elif day_diff >= Constants.TOO_OLD_DAY:  # Too old.
                        print('#%02d | Skipping the too old.' % (i + 1))
                        # No need to scan older rows.
                        log('Page %d took %.1f". Stop searching for older rows.' %
                            (page, common.get_elapsed_sec(start_time)), False)
                        return
                    else:
                        article_link_tag = row.select_one('h1 > a')
                        url = Constants.ROOT_DOMAIN + article_link_tag['href']
                        article_title = article_link_tag.string.split('|')[-1].strip()

                        # Finally, check duplicates
                        for info in scan_list:
                            if url.split('-')[-1] in info[0]:
                                log('#%02d | (Duplicate) %s' % (i + 1, article_title), False)
                                break
                        else:  # No duplicates
                            scan_list.append((url, domain_tag))
                            log('#%02d | %s' % (i + 1, article_title), False)

                        # if url in scan_list:
                        #     log('#%02d | (Duplicate) %s' % (i + 1, article_title), False)
                        # else:
                        #     scan_list.append((url, domain_tag))
                        #     log('#%02d | %s' % (i + 1, article_title), False)
            except Exception as row_exception:
                log('Error: Cannot process row %d from %s.(%s)' % (i + 1, url, row_exception))
                continue

        log('Page %d took %.1f".' % (page, common.get_elapsed_sec(start_time),), False)
        consecutive_failures = 0  # Reset the consecutive failure count.
        page += 1
    else:  # Now at (max_page + 1) page or (consecutive_failures == MAX_FAILURES)
        if consecutive_failures >= MAX_FAILURE:
            log('Consecutive %d failures of loading the page. Aborting scanning the subdirectory.' % MAX_FAILURE)


def process_domain(scan_list: [], placeholder: str, domain_tag: str, scanning_span: int, starting_page: int = 1):
    try:
        domain_start_time = datetime.now()
        log('Looking up %s' % placeholder.split('?')[0])
        append_articles_to_scan(scan_list, placeholder, domain_tag, scanning_span, starting_page)
        log('Finished processing %s in %d".\n' %
            (placeholder.split('?')[0], int(common.get_elapsed_sec(domain_start_time))), False)
    except Exception as normal_domain_exception:
        log('[Error] %s\n[Traceback]\n%s' % (normal_domain_exception, traceback.format_exc(),))


if __name__ == "__main__":
    main_scan_list = []
    buffer_list = []
    for subdirectory, directory_tag in Constants.SUBDIRECTORIES:
        browser = initiate_browser()
        try:
            # Append to the scanning list.
            process_domain(main_scan_list, Constants.ROOT_DOMAIN + subdirectory, directory_tag,
                           scanning_span=Constants.SCANNING_SPAN, starting_page=Constants.STARTING_PAGE)
        finally:
            browser.quit()

    # Then, scan the list
    for k in range(3):
        if buffer_list:  # Failed downloads exist.
            main_scan_list = buffer_list
            buffer_list = []
        log('%d articles to scan.\n' % len(main_scan_list), False)
        for n, article_info in enumerate(main_scan_list):
            scan_start_time = datetime.now()
            for j in range(2):  # If the scan is not successful, just try it again. Interception is whimsical.
                is_article_scan_successful = scan_article(url=article_info[0], tag_name=article_info[1])
                if is_article_scan_successful:
                    break
                else:
                    print('Warning: processing failed.')
            else:
                log('Error: Processing failed multiple times. Move to the next article.')
                buffer_list.append(article_info)
            log("(%d/%d) Processing finished in %.1f min.\n" %
                (n + 1, len(main_scan_list), (common.get_elapsed_sec(scan_start_time) / 60)), False)
        if not buffer_list:  # All articles have been downloaded.
            break
    if buffer_list:
        log("The followings have not been downloaded:", has_tst=False)
        for article_info in buffer_list:
            url = article_info[0]
            if url.strip():
                log(url, has_tst=False)
    log("\nScript finished.")
