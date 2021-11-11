import os
import zipfile
from glob import glob

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions
from selenium.webdriver.support.wait import WebDriverWait

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
    except Exception as e:
        print('(%s) The timestamp did not match the format: %s.' % (e, tst_str))


def __get_local_name(doc_title, url):
    doc_id = url.split('no=')[-1]  # The document id(e.g. '373719')
    try:
        title = doc_title.strip().replace(' ', '-').replace('.', '-').replace('/', '-')
        return title + '-' + doc_id
    except Exception as filename_exception:
        log('Error: cannot format filename %s. (%s)' % (doc_title, filename_exception))
        return doc_id


def initiate_browser(download_path: str):
    # A chrome web driver with headless option
    service = Service(DRIVER_PATH)
    options = webdriver.ChromeOptions()
    options.add_experimental_option("prefs", {
        "download.default_directory": download_path,
        "download.prompt_for_download": False
    })
    options.add_argument('headless')
    options.add_argument('disable-gpu')
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


def wait_for_downloading(temp_dir_path: str, loading_sec: float):
    seconds = 0
    check_interval = 1
    timeout = max(10, int(loading_sec * 30))

    last_size = 0
    while seconds < timeout:
        while get_size(temp_dir_path) == 0 and seconds < timeout:
            print('Waiting to start downloading.(%d/%d)' % (seconds, timeout))
            time.sleep(check_interval)
            seconds += check_interval
        current_size = get_size(temp_dir_path)
        print('%d -> %d bytes' % (last_size, current_size))
        if 0 < last_size == current_size:
            # Download finished, while the file name hasn't been properly changed.
            # (Unless downloading speed is slower than 1 byte/sec.)
            break
        last_size = current_size  # Update the file size.
        time.sleep(check_interval)
        seconds += check_interval
    else:
        return True  # Timeout reached.
    return False


def scan_article(url: str):
    browser.get(url)
    soup = BeautifulSoup(browser.page_source, HTML_PARSER)
    article_title = soup.select_one('h3.title > span.title_subject').string
    try:
        doc_id = url.split('no=')[-1]
    except:
        doc_id = '%04d' % random.randint(0, 9999)
    temp_download_path = DOWNLOAD_PATH + doc_id + '/'
    if not os.path.exists(temp_download_path):
        os.makedirs(temp_download_path)

    # Open another browser.
    downloading_browser = initiate_browser(temp_download_path)
    btn_class_name = 'btn_file_dw'
    try:
        timeout = True
        start_time = datetime.now()
        downloading_browser.get(url)
        log('Processing %s' % url)

        loading_sec = common.get_elapsed_sec(start_time)
        try:
            wait = WebDriverWait(browser, 15)
            wait.until(expected_conditions.visibility_of_element_located((By.CLASS_NAME, btn_class_name)))
            downloading_browser.find_element(By.CLASS_NAME, btn_class_name).click()
            print('Download button located.')
            timeout = wait_for_downloading(temp_download_path, loading_sec)
        except:
            try:
                downloading_browser.find_element(
                    By.XPATH, '/html/body/div[2]/div[2]/main/section/article[2]/div[1]/div/div[6]/ul/li/a'
                ).click()
                timeout = wait_for_downloading(temp_download_path, loading_sec)
            except:
                try:
                    downloading_browser.find_element(
                        By.XPATH, '//*[@id="container"]/section/article[2]/div[1]/div/div[7]/ul/li/a'
                    ).click()
                    timeout = wait_for_downloading(temp_download_path, loading_sec)
                except:
                    log('Error: Cannot locate the download button.')

        if timeout:
            log('Error: Download timeout reached.(%s)' % url)

        local_name = __get_local_name(article_title, url)
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
    except Exception as download_exception:
        log('Error: cannot process download.(%s)' % download_exception)
    finally:
        downloading_browser.quit()


def get_entries_to_scan(placeholder: str, scanning_span: int, page: int = 1) -> ():
    max_page = page + scanning_span - 1  # To prevent infinite looping
    to_scan = []
    ignored_row_types = ('공지', '설문')

    while page <= max_page:  # Page-wise
        start_time = datetime.now()  # A timer for monitoring performance
        url = placeholder.replace('%d', str(page))
        browser.get(url)
        soup = BeautifulSoup(browser.page_source, HTML_PARSER)
        rows = soup.select('table.gall_list > tbody > tr.us-post')

        for i, row in enumerate(rows):  # Inspect the rows
            try:
                row_type = row.select_one('td.gall_subject').string
                if row_type in ignored_row_types:
                    continue
                tst_str = row.select_one('td.gall_date')['title'].split(' ')[0]  # 2021-09-19 23:47:42
                day_diff = __get_date_difference(tst_str)
                if day_diff:
                    if day_diff <= TOO_YOUNG_DAY:  # Still, not mature: uploaded on the yesterday.
                        continue  # Move to the next row
                    elif day_diff >= TOO_OLD_DAY:  # Too old.
                        # No need to scan older rows.
                        log('Page %d took %.2fs. Stop searching.\n' % (page, common.get_elapsed_sec(start_time)), False)
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
                                log('#%02d | (ignored) %s' % (i + 1, title), False)
                                break
                        else:
                            article_url = row.select_one('td.gall_tit > a')['href'].split('&page')[0]
                            to_scan.append(article_url)
                            log('#%02d | %s' % (i + 1, title), False)
            except Exception as row_exception:
                log('Error: cannot process row %d from %s.(%s)' % (i + 1, url, row_exception))
                continue
        log('Page %d took %.2fs.' % (page, common.get_elapsed_sec(start_time)), False)
        time.sleep(random.uniform(0.5, 2.5))
        page += 1
    return tuple(to_scan)


def process_domain(domains: tuple, scanning_span: int, starting_page: int = 1):
    try:
        for domain in domains:
            domain_start_time = datetime.now()
            log('Looking up %s.' % domain)
            scan_list = get_entries_to_scan(domain, scanning_span, starting_page)
            for i, article_no in enumerate(scan_list):  # [32113, 39213, 123412, ...]
                pause = random.uniform(2, 4)
                print('Pause for %.1f.' % pause)
                time.sleep(pause)

                article_url = ROOT_DOMAIN + str(article_no)
                scan_start_time = datetime.now()
                scan_article(article_url)
                log('Scanned %d/%d articles(%.1f")' % (i + 1, len(scan_list), common.get_elapsed_sec(scan_start_time)))
            log('Finished scanning %s in %d min.' % (domain, int(common.get_elapsed_sec(domain_start_time) / 60)))
    except Exception as normal_domain_exception:
        log('[Error] %s\n[Traceback]\n%s' % (normal_domain_exception, traceback.format_exc(),))


browser = initiate_browser(DOWNLOAD_PATH)
try:
    time.sleep(random.uniform(60, 2100))
    process_domain(GALLERY_DOMAINS, scanning_span=5, starting_page=1)
finally:
    browser.quit()
