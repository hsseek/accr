import os
import zipfile
from glob import glob

import selenium.common.exceptions
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By

import common
import random
import traceback
from datetime import datetime
from bs4 import BeautifulSoup

import downloader


class Constants:
    TOO_YOUNG_DAY = 1
    TOO_OLD_DAY = 3
    SCANNING_SPAN = 30
    STARTING_PAGE = 1

    EXTENSION_CANDIDATES = ('jpg', 'jpeg', 'png', 'gif', 'jfif', 'webp', 'mp4', 'webm', 'mov')
    TITLE_WHITELIST = common.build_tuple('DC_TITLE_WHITELIST.pv')

    ROOT_DOMAIN = common.read_from_file('DC_ROOT.pv')
    SUBDIRECTORIES = common.build_tuple_of_tuples('DC_SUBDIRECTORIES.pv')
    SUBDIRECTORIES_CHAOTIC = common.build_tuple_of_tuples('DC_SUBDIRECTORIES_LARGE.pv')
    ACCOUNT, PASSWORD = common.build_tuple('DC_ACCOUNT.pv')

    DESTINATION_PATH = common.Constants.DOWNLOAD_PATH
    TMP_DOWNLOAD_PATH = common.read_from_file('DC_DOWNLOAD_PATH.pv')
    LOG_PATH = common.read_from_file('DC_LOG_PATH.pv')


def log(message: str, has_tst: bool = True):
    path = Constants.LOG_PATH
    common.log(message, path, has_tst)


def __get_date_difference(tst_str: str) -> int:
    try:
        date = datetime.strptime(tst_str, '%Y-%m-%d')  # 2021-11-07
        now = datetime.now()
        return (now - date).days
    except Exception as tst_exception:
        print('(%s) The timestamp did not match the format: %s.' % (tst_exception, tst_str))


def initiate_browser():
    # A chrome web driver with headless option
    service = Service(common.Constants.DRIVER_PATH)
    options = webdriver.ChromeOptions()
    options.add_experimental_option("prefs", {
        "download.default_directory": Constants.TMP_DOWNLOAD_PATH,
        "download.prompt_for_download": False
    })
    options.add_argument('headless')
    options.add_argument('disable-gpu')
    # options.add_experimental_option("detach", True)
    driver = webdriver.Chrome(service=service, options=options)
    return driver


def login(driver: webdriver.Chrome, current_url: str):
    driver.get(Constants.ROOT_DOMAIN)
    driver.find_element(By.NAME, 'user_id').send_keys(Constants.ACCOUNT)
    driver.find_element(By.NAME, 'pw').send_keys(Constants.PASSWORD)
    driver.find_element(By.ID, 'login_ok').click()
    driver.get(current_url)


def element_exists_by_class(driver: webdriver.Chrome, class_name: str) -> bool:
    try:
        driver.find_element(By.CLASS_NAME, class_name)
    except selenium.common.exceptions.NoSuchElementException:
        return False
    return True


def mark_and_move(current_path: str, destination_path: str):
    for file in os.listdir(current_path):
        os.rename(current_path + file, destination_path + 'err-' + file)


def scan_article(url: str):
    log('\nProcessing %s' % url)
    domain_tag = 'dc'

    # A temporary folder to store the zip file.
    # The folder name can be anything, but use the article number to prevent duplicate names.
    common.check_dir_exists(Constants.TMP_DOWNLOAD_PATH)

    # Load the article.
    start_time = datetime.now()
    browser.get(url)
    check_auth(url)
    loading_sec = common.get_elapsed_sec(start_time)

    # Get the information to format the file name.
    try:
        soup = BeautifulSoup(browser.page_source, common.Constants.HTML_PARSER)
        # Get Likes.
        likes = soup.select_one('div.fr > span.gall_reply_num').string.strip().split(' ')[-1]
        formatted_likes = '%03d' % int(likes)
        # Get the title.
        article_title = soup.select_one('h3.title > span.title_subject').string
        formatted_title = article_title.strip()
        log('<%s> Loaded.' % formatted_title)
        for prohibited_char in common.Constants.PROHIBITED_CHARS:
            formatted_title = formatted_title.replace(prohibited_char, '_')
        # Get the channel name
        channel_name = __get_chan_from_url(url)
        article_no = __get_no_from_url(url)
        formatted_file_name = '%s-%s-%s-%s-%s' % \
                              (domain_tag, channel_name, formatted_likes, formatted_title, article_no)
    except Exception as title_exception:
        log('Error: cannot process the article title.(%s)' % title_exception, has_tst=False)
        # Use the article number as the file name.
        formatted_file_name = domain_tag + '-' + __get_no_from_url(url)

    download_successful = click_download_button(url, Constants.TMP_DOWNLOAD_PATH, loading_sec)

    if not download_successful:  # Timeout reached again. Log and move to the next article.
        log('Error: Download failed.')
        if len(os.listdir(Constants.TMP_DOWNLOAD_PATH)) > 0:
            mark_and_move(Constants.TMP_DOWNLOAD_PATH, Constants.DESTINATION_PATH)
            log('Error: Files left after download failure.')
        return  # Nothing to do.

    try:
        __format_downloaded_file(formatted_file_name)
    except Exception as post_download_exception:
        log('Error: cannot process downloaded files.(%s)' % post_download_exception)


# Process the downloaded file. (Mostly, a zip file or an image)
def __format_downloaded_file(formatted_file_name):
    # Unzip the downloaded file.
    zip_files = glob(Constants.TMP_DOWNLOAD_PATH + '*.zip')
    for zip_file_path in zip_files:
        with zipfile.ZipFile(zip_file_path, 'r') as zip_ref:
            zip_ref.extractall(Constants.TMP_DOWNLOAD_PATH)
        os.remove(zip_file_path)

    # Convert webp files.
    for file_name in os.listdir(Constants.TMP_DOWNLOAD_PATH):  # The file name might have been changed.
        if file_name.endswith('.webp'):
            common.convert_webp_to_png(Constants.TMP_DOWNLOAD_PATH, file_name)

    # Rename files with long names.
    destination_head = Constants.DESTINATION_PATH + formatted_file_name
    char_limit = 40
    for file_name in os.listdir(Constants.TMP_DOWNLOAD_PATH):
        if len(file_name) > char_limit:
            print('Truncated a long file name: %s' % file_name)
            os.rename(Constants.TMP_DOWNLOAD_PATH + file_name, destination_head + file_name[-char_limit:])
        else:
            os.rename(Constants.TMP_DOWNLOAD_PATH + file_name, destination_head + file_name)


def check_auth(url):
    certify_class_name = 'adult_certify'
    if not element_exists_by_class(browser, certify_class_name):
        # Login not required.
        return True  # Good to go.
    else:
        for i in range(2):
            log('Login required to view the article.')
            try:
                login(browser, url)
                if not element_exists_by_class(browser, certify_class_name):
                    log('Login successful.')
                    return True  # Good to go.
            except Exception as login_exception:
                log('Login failed.(%s)' % login_exception)
        else:
            return False  # Cannot proceed.


def click_download_button(url: str, tmp_download_path: str, loading_sec: float) -> bool:
    # The download buttons
    btn_class_name = 'btn_file_dw'
    single_download_btn_xpath_1 = '//*[@id="container"]/section/article[2]/div[1]/div/div[7]/ul/li/a'
    single_download_btn_xpath_2 = '//*[@id="container"]/section/article[2]/div[1]/div/div[6]/ul/li/a'

    for i in range(3):
        try:
            if i > 0:  # Has failed. Refresh the browser.
                log('Download failed with trial #%d.' % i)
                browser.get(url)  # refresh() does not wait the page to be loaded. So, use get(url)  instead.
            browser.find_element(By.CLASS_NAME, btn_class_name).click()
            print('"Download all" button located.')
            successful = downloader.wait_finish_downloading(tmp_download_path, Constants.LOG_PATH, loading_sec, trial=i)
            if successful:  # Without reaching timeout
                break
            # Else, loop again.
        except selenium.common.exceptions.NoSuchElementException:
            try:
                browser.find_element(By.XPATH, single_download_btn_xpath_1).click()
                print('Download button 1 located.')

                # Don't wait as the session has waited long enough.
                successful = downloader.wait_finish_downloading(tmp_download_path, Constants.LOG_PATH,
                                                                loading_sec, trial=i)
                if successful:
                    break
            except selenium.common.exceptions.NoSuchElementException:
                try:
                    browser.find_element(By.XPATH, single_download_btn_xpath_2).click()
                    print('Download button 2 located.')

                    successful = downloader.wait_finish_downloading(tmp_download_path, Constants.LOG_PATH,
                                                                    loading_sec, trial=i)
                    if successful:
                        break
                except selenium.common.exceptions.NoSuchElementException:
                    log('Error: Cannot locate the download button.')
                    return False  # The button cannot be located.
                except Exception as download_btn_2_exception:
                    log('Error: download button 2 raised an exception:(%s)' % download_btn_2_exception, False)
                    return False  # Something went wrong trying 'Download 2'
            except Exception as download_btn_1_exception:
                log('Error: download button 1 raised an exception:(%s)' % download_btn_1_exception, False)
                return False  # Something went wrong trying 'Download 1'
        except Exception as download_btn_exception:
            log('Download button exception: %s' % download_btn_exception)
            return False  # Something went wrong trying 'Download all'
    else:  # The loop terminated without break, which means all the trials failed.
        return False

    # Did not encounter exceptions. Downloaded the file successfully.
    log('Download finished successfully.')
    return True


def __get_no_from_url(url: str) -> str:
    return url.split('no=')[-1].split('&')[0]


def __get_chan_from_url(url: str) -> str:
    return url.split('id=')[-1].split('&')[0]


def qualify_row(row, row_no: int, min_likes: int, ignored_row_types: (), excluding: bool):
    row_type_tag = row.select_one('td.gall_subject')
    if row_type_tag:  # (214, 설문), (23124, 방송), (23125, 코스프), ...
        if row_type_tag.string in ignored_row_types:
            return   # Skip the row.
    else:  # 설문, 공지, 21231, 21232, ...
        article_no = str(row.select_one('td.gall_num').string)
        if not article_no.isdigit():
            return  # Skip the row.
    likes = int(row.select_one('td.gall_recommend').string)

    # 1. Filter by the date.
    tst_str = row.select_one('td.gall_date')['title'].split(' ')[0]  # 2021-09-19 23:47:42
    day_diff = __get_date_difference(tst_str)
    if day_diff:
        if day_diff <= Constants.TOO_YOUNG_DAY:  # Still, not mature: uploaded on the yesterday.
            print('#%02d (%s) \t| Skipping the too young.' % (row_no, likes))
            return  # Move to the next row
        elif day_diff >= Constants.TOO_OLD_DAY:  # Too old.
            print('#%02d (%s) \t| Skipping the too old.' % (row_no, likes))
            return False
        # else, a matured article. Proceed.
    else:  # An exception has been raised. Skip the row.
        return

    # 2. Filter by the title.
    # Retrieve the title.
    try:
        title = row.select_one('td.gall_tit > a').text
    except Exception as title_exception:
        title = '%05d' % random.randint(1, 99999)
        log('Error: cannot retrieve article title of row %d.(%s)' %
            (row_no, title_exception))

    if not excluding:  # Regular subdirectories
        # Check ignored patterns.
        for pattern in common.Constants.IGNORED_TITLE_PATTERNS:
            if pattern in title:
                log('#%02d (%02d) | (ignored) %s' % (row_no, likes, title), False)
                return  # Ignored pattern detected. Skip the row.

        # 3. Filter by likes.
        if likes < min_likes:
            return
    else:  # Worth-scanning only if white-listed or with very large likes
        for whitelist_pattern in Constants.TITLE_WHITELIST:
            if whitelist_pattern in title:
                break
        else:  # Not white-listed
            if likes < min_likes:
                return

    try:
        article_no = row['data-no']
    except Exception as row_link_exception:
        log('Warning: Cannot retrieve article number. Try extracting from url.(%s)' % row_link_exception)
        article_no = __get_no_from_url(row.select_one('td.gall_tit > a')['href'])
    log('#%02d (%02d) \t| %s' % (row_no, likes, title), False)
    return article_no


def get_entries_to_scan(placeholder: str, min_likes: int, scanning_span: int,
                        page: int = 1, excluding: bool = False) -> ():
    max_page = page + scanning_span - 1  # To prevent infinite looping
    to_scan = []
    ignored_row_types = ('공지', '설문')
    prev_url = ''

    while page <= max_page:  # Page-wise
        start_time = datetime.now()  # A timer for monitoring performance
        url = placeholder.replace('%d', str(page))
        browser.get(url)
        check_auth(url)
        soup = BeautifulSoup(browser.page_source, common.Constants.HTML_PARSER)
        rows = soup.select('table.gall_list > tbody > tr.us-post')

        for i, row in enumerate(rows):  # Inspect the rows
            try:
                article_no = qualify_row(row, i + 1, min_likes, ignored_row_types, excluding)
                if article_no is None:  # Unqualified. Skip the row.
                    continue
                if article_no is False:  # Date limit reached. No need of further investigation.
                    log('Page %d took %.2fs. Stop searching for older rows.' %
                        (page, common.get_elapsed_sec(start_time)), False)
                    return to_scan
                else:  # A qualified row, append to the scanning list.
                    to_scan.append(article_no)

            except Exception as row_exception:
                log('Error: cannot process row %d from %s.(%s)' % (i + 1, url, row_exception))
                continue
        if browser.current_url == prev_url:
            log('Page %d does not exists. Skip the following pages.' % page)
            return tuple(to_scan)
        else:
            prev_url = browser.current_url  # Store the url for the next comparison.
        log('Page %d took %.2fs.' % (page, common.get_elapsed_sec(start_time)), False)
        common.pause_briefly(1, 4)
        page += 1
    return tuple(to_scan)


def process_domain(gall: str, min_likes: int, scanning_span: int, starting_page: int = 1, excluding: bool = False):
    try:
        gall_start_time = datetime.now()
        log('Looking up %s' % gall)
        scan_list = get_entries_to_scan(gall, min_likes, scanning_span, starting_page, excluding)
        for i, article_no in enumerate(scan_list):  # [32113, 39213, 123412, ...]
            common.pause_briefly()
            article_url = gall.replace('lists', 'view').replace('page', 'no').replace('%d', str(article_no))
            scan_start_time = datetime.now()
            scan_article(article_url)
            log('Scanned %d/%d articles(%.1f")' %
                (i + 1, len(scan_list), common.get_elapsed_sec(scan_start_time)), False)
        log('Finished scanning %s in %d min.\n' % (gall, int(common.get_elapsed_sec(gall_start_time) / 60)), False)
    except Exception as normal_domain_exception:
        log('[Error] %s\n[Traceback]\n%s' % (normal_domain_exception, traceback.format_exc(),))


browser = initiate_browser()
try:
    for subdirectory, min_likes_str in Constants.SUBDIRECTORIES:
        process_domain(subdirectory, min_likes=int(min_likes_str),
                       scanning_span=Constants.SCANNING_SPAN, starting_page=Constants.STARTING_PAGE)
    for subdirectory, min_likes_str in Constants.SUBDIRECTORIES_CHAOTIC:
        process_domain(subdirectory, min_likes=int(min_likes_str),
                       scanning_span=Constants.SCANNING_SPAN, starting_page=Constants.STARTING_PAGE, excluding=True)
finally:
    browser.quit()
