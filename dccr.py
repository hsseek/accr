import os
import zipfile
from glob import glob

import selenium.common.exceptions
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By

import common
import random
import time
import traceback
from datetime import datetime
from bs4 import BeautifulSoup

HTML_PARSER = 'html.parser'
EXTENSION_CANDIDATES = ('jpg', 'jpeg', 'png', 'gif', 'jfif', 'webp', 'mp4', 'webm', 'mov')
TITLE_IGNORED_PATTERNS = ('코스프레', '코스어')
TOO_YOUNG_DAY = 0
TOO_OLD_DAY = 2


def log(message: str, has_tst: bool = True):
    path = common.read_from_file('DC_LOG_PATH.pv')
    common.log(message, path, has_tst)


ROOT_DOMAIN = common.read_from_file('DC_ROOT_DOMAIN.pv')
LOGIN_DOMAIN = common.read_from_file('DC_LOGIN_PATH.pv')
GALLERY_DOMAINS = common.build_tuple('DC_DOMAINS.pv')
IGNORED_DOMAINS = common.build_tuple('DC_IGNORED_DOMAINS.pv')
LOG_PATH = common.read_from_file('DC_LOG_PATH.pv')
DRIVER_PATH = common.read_from_file('DRIVER_PATH.pv')
ACCOUNT = common.read_from_file('EMAIL.pv')
PW = common.read_from_file('PW.pv')

DOWNLOAD_PATH = common.read_from_file('DOWNLOAD_PATH.pv')


def __get_date_difference(tst_str: str) -> int:
    try:
        date = datetime.strptime(tst_str, '%Y-%m-%d')  # 2021-11-07
        now = datetime.now()
        return (now - date).days
    except Exception as tst_exception:
        print('(%s) The timestamp did not match the format: %s.' % (tst_exception, tst_str))


def initiate_browser(download_path: str):
    # A chrome web driver with headless option
    service = Service(DRIVER_PATH)
    options = webdriver.ChromeOptions()
    options.add_experimental_option("prefs", {
        "download.default_directory": download_path,
        "download.prompt_for_download": False
    })
    options.add_argument('headless')
    # options.add_argument('disable-gpu')
    # options.add_experimental_option("detach", True)
    driver = webdriver.Chrome(service=service, options=options)
    return driver


def get_size(start_path: str):
    total_size = 0
    for dir_path, dir_names, filenames in os.walk(start_path):
        for f in filenames:
            fp = os.path.join(dir_path, f)
            # skip if it is symbolic link
            if not os.path.islink(fp):
                total_size += os.path.getsize(fp)
    return total_size


def wait_for_downloading(temp_dir_path: str, loading_sec: float, extended: bool = False):
    seconds = 0
    check_interval = 1
    timeout_multiplier = 25 if extended else 5

    # The timeout: 15 ~ 600
    timeout = max(1, int(loading_sec * timeout_multiplier))
    if timeout > 600:
        timeout = 600

    last_size = 0
    while seconds <= timeout:
        while len(os.listdir(temp_dir_path)) == 0 and seconds <= timeout:
            print('Waiting to start downloading.(%d/%d)' % (seconds, timeout))
            time.sleep(check_interval)
            seconds += check_interval
        current_size = get_size(temp_dir_path)
        if current_size != last_size:  # File size increasing, i.e. downloading
            print('%.1f -> %.1f MB' % (last_size / 1000000, current_size / 1000000))
        if 0 < last_size == current_size:
            # The file size not increasing, which means download finished.
            # (Unless downloading speed is slower than 1 byte/sec.)
            print('Download successful.')
            return True  # Successful download
        last_size = current_size  # Update the file size.
        time.sleep(check_interval)
        seconds += check_interval
    else:
        print('Download NOT successful.')
        return False  # Download not successful


def scan_article(url: str, article_no: str):
    log('Processing %s' % url)

    temp_download_path = DOWNLOAD_PATH + article_no + '/'
    if not os.path.exists(temp_download_path):
        os.makedirs(temp_download_path)
        print('Temporary downloading destination created: %s' % temp_download_path)

    # Open another browser.
    downloading_browser = initiate_browser(temp_download_path)
    try:
        start_time = datetime.now()
        downloading_browser.get(url)
        # Retrieve the title to name the local files.
        try:
            soup = BeautifulSoup(downloading_browser.page_source, HTML_PARSER)
            article_title = soup.select_one('h3.title > span.title_subject').string
            local_name = article_title.strip().replace(' ', '-').replace('.', '-').replace('/', '-')
        except:
            local_name = article_no

        download_successful = click_download_button(downloading_browser, temp_download_path, start_time)
        if not download_successful:
            log('Error: Download timeout reached, trying again.')
            start_time = datetime.now()
            downloading_browser.get(url)  # Access the page again. (Equivalent to Refresh)
            download_successful = click_download_button(downloading_browser, temp_download_path,
                                                        start_time=start_time, extended=True)

        if not download_successful:  # Timeout reached again. Log and move to the next article.
            log('Error: Extended download timeout reached.(%s)' % url)
            os.rmdir(temp_download_path)
            return  # Nothing to do.
    finally:
        downloading_browser.quit()

    try:
        DOMAIN_TAG = '-dc-'

        # Unzip the downloaded file.
        zip_files = glob(temp_download_path + '*.zip')
        for zip_file_path in zip_files:
            with zipfile.ZipFile(zip_file_path, 'r') as zip_ref:
                zip_ref.extractall(temp_download_path)
            os.remove(zip_file_path)

        # Convert webp files.
        for file_name in os.listdir(temp_download_path):  # The file name might have been changed.
            if file_name.endswith('.webp'):
                common.convert_webp_to_png(temp_download_path, file_name)

        # Rename the file(s).
        for file_name in os.listdir(temp_download_path):  # List only file names.
            if len(file_name) < 50:
                os.rename(temp_download_path + file_name, DOWNLOAD_PATH + local_name + DOMAIN_TAG + file_name)
            else:
                long_name, extension = common.split_on_last_pattern(file_name, '.')
                os.rename(temp_download_path + file_name, DOWNLOAD_PATH + local_name + DOMAIN_TAG +
                          long_name[:50] + '.' + extension)
                print('Truncate a long name: %s' % long_name)

        # If the folder is empty, remove it.
        if not len(os.listdir(temp_download_path)):
            os.rmdir(temp_download_path)
    except Exception as post_download_exception:
        log('Error: cannot process download.(%s)' % post_download_exception)


def click_download_button(temp_browser, temp_download_path: str, start_time, extended: bool = False) -> bool:
    # The download buttons
    btn_class_name = 'btn_file_dw'
    single_download_btn_xpath_1 = '//*[@id="container"]/section/article[2]/div[1]/div/div[7]/ul/li/a'
    single_download_btn_xpath_2 = '//*[@id="container"]/section/article[2]/div[1]/div/div[6]/ul/li/a'
    successful = False

    try:
        temp_browser.find_element(By.CLASS_NAME, btn_class_name).click()
        print('"Download all" button located.')

        loading_sec = common.get_elapsed_sec(start_time)
        successful = wait_for_downloading(temp_download_path, loading_sec, extended=extended)
    except selenium.common.exceptions.ElementNotInteractableException:
        loading_sec = common.get_elapsed_sec(start_time)
        successful = wait_for_downloading(temp_download_path, loading_sec, extended=extended)
    except Exception as e1:
        try:
            print('Download button exception: %s' % e1)
            temp_browser.find_element(By.XPATH, single_download_btn_xpath_1).click()
            print('Download button 1 located.')

            # Don't wait as the session has waited long enough.
            loading_sec = common.get_elapsed_sec(start_time)
            successful = wait_for_downloading(temp_download_path, loading_sec, extended=extended)
        except:
            try:
                temp_browser.find_element(By.XPATH, single_download_btn_xpath_2).click()
                print('Download button 2 located.')

                loading_sec = common.get_elapsed_sec(start_time)
                successful = wait_for_downloading(temp_download_path, loading_sec, extended=extended)
            except:
                log('Error: Cannot locate the download button.')
    return successful


def get_entries_to_scan(placeholder: str, min_likes: int, scanning_span: int, page: int = 1) -> ():
    max_page = page + scanning_span - 1  # To prevent infinite looping
    to_scan = []
    ignored_row_types = ('공지', '설문')
    prev_url = ''
    browser = initiate_browser(DOWNLOAD_PATH)

    try:
        while page <= max_page:  # Page-wise
            start_time = datetime.now()  # A timer for monitoring performance
            url = placeholder.replace('%d', str(page))
            browser.get(url)
            soup = BeautifulSoup(browser.page_source, HTML_PARSER)
            rows = soup.select('table.gall_list > tbody > tr.us-post')

            for i, row in enumerate(rows):  # Inspect the rows
                try:
                    row_type = row.select_one('td.gall_subject').string
                    if row_type in ignored_row_types:  # Filter irregular rows.
                        continue
                    likes = int(row.select_one('td.gall_recommend').string)
                    if likes < min_likes:
                        continue

                    tst_str = row.select_one('td.gall_date')['title'].split(' ')[0]  # 2021-09-19 23:47:42
                    day_diff = __get_date_difference(tst_str)
                    if day_diff:
                        if day_diff <= TOO_YOUNG_DAY:  # Still, not mature: uploaded on the yesterday.
                            continue  # Move to the next row
                        elif day_diff >= TOO_OLD_DAY:  # Too old.
                            # No need to scan older rows.
                            log('Page %d took %.2fs. Stop searching for older articles\n' %
                                (page, common.get_elapsed_sec(start_time)), False)
                            return tuple(to_scan)
                        else:  # Mature
                            try:
                                title = row.select_one('td.gall_tit > a').text
                            except Exception as title_exception:
                                title = '%05d' % random.randint(1, 99999)
                                log('Error: cannot retrieve article title of row %d.(%s)\n(%s)' %
                                    (i + 1, title_exception, url))
                            for pattern in TITLE_IGNORED_PATTERNS:  # Compare the string pattern: the most expensive
                                if pattern in title:
                                    log('#%02d (%02d) | (ignored) %s' % (i + 1, likes, title), False)
                                    break
                            else:
                                article_no = row.select_one('td.gall_tit > a')['href'].split('&page')[0]
                                to_scan.append(article_no)
                                log('#%02d (%02d) | %s' % (i + 1, likes, title), False)
                except Exception as row_exception:
                    log('Error: cannot process row %d from %s.(%s)' % (i + 1, url, row_exception))
                    continue
            if browser.current_url == prev_url:
                log('Error: Page %d doesn\'t exists. Skip the following pages.' % page)
                return tuple(to_scan)
            else:
                prev_url = browser.current_url  # Store the url for the next comparison.
            log('Page %d took %.2fs.' % (page, common.get_elapsed_sec(start_time)), False)
            time.sleep(random.uniform(0.5, 2.5))
            page += 1
    finally:
        browser.quit()
    return tuple(to_scan)


def process_domain(domains: tuple, min_likes: int, scanning_span: int, starting_page: int = 1):
    try:
        for gall in domains:
            domain_start_time = datetime.now()
            log('Looking up %s.' % gall)
            scan_list = get_entries_to_scan(gall, min_likes, scanning_span, starting_page)
            for i, article_no in enumerate(scan_list):  # [32113, 39213, 123412, ...]
                pause = random.uniform(2, 4)
                print('Pause for %.1f.' % pause)
                time.sleep(pause)

                article_url = ROOT_DOMAIN + str(article_no)
                scan_start_time = datetime.now()
                scan_article(article_url, article_no)
                log('Scanned %d/%d articles(%.1f")' % (i + 1, len(scan_list), common.get_elapsed_sec(scan_start_time)))
            log('Finished scanning %s in %d min.' % (gall, int(common.get_elapsed_sec(domain_start_time) / 60)))
    except Exception as normal_domain_exception:
        log('[Error] %s\n[Traceback]\n%s' % (normal_domain_exception, traceback.format_exc(),))


try:
    time.sleep(random.uniform(60, 2100))
    process_domain(GALLERY_DOMAINS, min_likes=100, scanning_span=5, starting_page=1)
except Exception as e:
    log('Error: main loop error.(%s)\n[Traceback]\n%s' % (e, traceback.format_exc()))
