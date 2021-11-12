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


GALLERY_DOMAINS = common.build_tuple('DC_DOMAINS.pv')
IGNORED_DOMAINS = common.build_tuple('DC_IGNORED_DOMAINS.pv')
LOG_PATH = common.read_from_file('DC_LOG_PATH.pv')
DRIVER_PATH = common.read_from_file('DRIVER_PATH.pv')

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
    options.add_argument('disable-gpu')
    # options.add_experimental_option("detach", True)
    driver = webdriver.Chrome(service=service, options=options)
    return driver


def wait_for_downloading(temp_dir_path: str, loading_sec: float, trial: int = 0):
    seconds = 0
    check_interval = 1
    timeout_multiplier = (4 ^ trial + 1)  # (2, 5, 17, 65, ... )

    # The timeout: 10 ~ 600
    timeout = max(10, int(loading_sec * timeout_multiplier))
    if timeout > 600:
        timeout = 600

    last_size = 0
    while seconds <= timeout:
        current_size = sum(os.path.getsize(f) for f in glob(temp_dir_path + '*') if os.path.isfile(f))
        if current_size == last_size and last_size > 0:
            return True
        print('Waiting to finish downloading.(%d/%d)' % (seconds, timeout))
        # Report
        if current_size != last_size:
            print('%.1f -> %.1f MB' % (last_size / 1000000, current_size / 1000000))
        # Wait
        time.sleep(check_interval)
        seconds += check_interval
        last_size = current_size
    print('Download timeout reached.')
    return False  # Timeout


def scan_article(url: str):
    log('\nProcessing %s' % url)
    article_no = __get_no_from_url(url)

    # A temporary folder to store the zip file.
    # The folder name can be anything, but use the article number to prevent duplicate names.
    temp_download_path = DOWNLOAD_PATH + article_no + '/'
    if not os.path.exists(temp_download_path):
        os.makedirs(temp_download_path)

    # Open another browser.
    downloading_browser = initiate_browser(temp_download_path)
    try:
        start_time = datetime.now()
        downloading_browser.get(url)
        loading_sec = common.get_elapsed_sec(start_time)
        # Retrieve the title to name the local files.
        try:
            soup = BeautifulSoup(downloading_browser.page_source, HTML_PARSER)
            article_title = soup.select_one('h3.title > span.title_subject').string
            local_name = article_title.strip().replace(' ', '-').replace('.', '-').replace('/', '-')
        except:
            local_name = article_no

        download_successful = click_download_button(downloading_browser, url, temp_download_path, loading_sec)

        if not download_successful:  # Timeout reached again. Log and move to the next article.
            log('Error: Download failed.')
            if len(os.listdir(temp_download_path)) == 0:
                os.rmdir(temp_download_path)
            else:
                log('Error: Files left in the directory.(%s)' % temp_download_path)
            return  # Nothing to do.
    finally:
        downloading_browser.quit()

    # Process the downloaded file. (Mostly, a zip file or an image)
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


def click_download_button(temp_browser, url: str, temp_download_path: str, loading_sec: float) -> bool:
    # The download buttons
    btn_class_name = 'btn_file_dw'
    single_download_btn_xpath_1 = '//*[@id="container"]/section/article[2]/div[1]/div/div[7]/ul/li/a'
    single_download_btn_xpath_2 = '//*[@id="container"]/section/article[2]/div[1]/div/div[6]/ul/li/a'

    for i in range(3):
        try:
            if i > 0:  # Has failed. Refresh the browser.
                log('Download failed with trial #%d.' % i)
                temp_browser.get(url)   # refresh() does not wait the page to be loaded. So, use get(url)  instead.
            temp_browser.find_element(By.CLASS_NAME, btn_class_name).click()
            print('"Download all" button located.')
            successful = wait_for_downloading(temp_download_path, loading_sec, trial=i)
            if successful:  # Without reaching timeout
                break
            # Else, loop again.
        except selenium.common.exceptions.NoSuchElementException:
            try:
                temp_browser.find_element(By.XPATH, single_download_btn_xpath_1).click()
                print('Download button 1 located.')

                # Don't wait as the session has waited long enough.
                successful = wait_for_downloading(temp_download_path, loading_sec, trial=i)
                if successful:
                    break
            except selenium.common.exceptions.NoSuchElementException:
                try:
                    temp_browser.find_element(By.XPATH, single_download_btn_xpath_2).click()
                    print('Download button 2 located.')

                    successful = wait_for_downloading(temp_download_path, loading_sec, trial=i)
                    if successful:
                        break
                except selenium.common.exceptions.NoSuchElementException:
                    log('Error: Cannot locate the download button.')
                    return False  # The button cannot be located.
                except:
                    return False  # Something went wrong trying 'Download 2'
            except:
                return False  # Something went wrong trying 'Download 1'
        except Exception as download_btn_exception:
            log('Download button exception: %s' % download_btn_exception)
            return False  # Something went wrong trying 'Download all'
    else:  # The loop terminated without break, which means successful download.
        return False

    # Did not encounter exceptions. Downloaded the file successfully.
    log('Download finished successfully.')
    return True


def __get_no_from_url(url: str) -> str:
    return url.split('&no=')[-1].split('&')[0]


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
                                article_no = __get_no_from_url(row.select_one('td.gall_tit > a')['href'])
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

                article_url = gall.replace('lists', 'view').replace('page', 'no').replace('%d', str(article_no))
                scan_start_time = datetime.now()
                scan_article(article_url)
                log('Scanned %d/%d articles(%.1f")' % (i + 1, len(scan_list), common.get_elapsed_sec(scan_start_time)))
            log('Finished scanning %s in %d min.' % (gall, int(common.get_elapsed_sec(domain_start_time) / 60)))
    except Exception as normal_domain_exception:
        log('[Error] %s\n[Traceback]\n%s' % (normal_domain_exception, traceback.format_exc(),))


try:
    time.sleep(random.uniform(60, 2100))  # Sleep minutes to randomize the starting time.
    process_domain(GALLERY_DOMAINS, min_likes=50, scanning_span=2, starting_page=1)
except Exception as e:
    log('Error: main loop error.(%s)\n[Traceback]\n%s' % (e, traceback.format_exc()))
