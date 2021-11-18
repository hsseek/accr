import random
import time
import traceback
from datetime import datetime

import requests
import selenium.common.exceptions
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions
from bs4 import BeautifulSoup

import common
import downloader


class Constants:
    # Scanning variables
    TOO_YOUNG_DATE = 1
    TOO_OLD_DATE = 3
    SCANNING_SPAN = 15
    STARTING_PAGE = 1
    IS_START_POSTPONED = True

    # urls and paths in String
    ROOT_DOMAIN = common.read_from_file('GG_ROOT_DOMAIN.pv')
    PAGE_PLACEHOLDER = ROOT_DOMAIN + '/index.php?mid=%s&page='
    BOARDS = common.build_tuple_of_tuples('GG_SUBDIRECTORIES.pv')

    # Parsing and file processing
    HTML_PARSER = 'html.parser'
    EXTENSION_CANDIDATES = ('jpg', 'jpeg', 'png', 'gif', 'jfif', 'mp4', 'webp', 'webm')
    VIDEO_SOURCE_CANDIDATES = ('gfycat', 'redgifs')
    LOG_PATH = common.read_from_file('GG_LOG_PATH.pv')


def log(message: str, has_tst: bool = True):
    path = Constants.LOG_PATH
    common.log(message, path, has_tst)


def initiate_browser():
    # A chrome web driver with headless option
    service = Service(common.Constants.DRIVER_PATH)
    options = webdriver.ChromeOptions()
    options.add_argument('headless')
    options.add_argument('disable-gpu')
    # options.add_experimental_option("detach", True)
    driver = webdriver.Chrome(service=service, options=options)
    return driver


def remove_extension(string: str) -> str:
    return common.split_on_last_pattern(string, '.')[0]


def __get_date_difference(tst_str: str) -> int:
    date = datetime.strptime(tst_str, '%Y.%m.%d')  # 2021.11.07
    now = datetime.now()
    return (now - date).days


def get_entries_to_scan(placeholder: str, extensions: (), min_likes: int, scanning_span: int, page: int = 1) -> ():
    max_page = page + scanning_span - 1  # To prevent infinite looping
    log('Scanning pages on %s' % placeholder + str(page))
    tst_attribute = 'title'
    prev_row_date = None
    to_scan = []

    while page <= max_page:  # Page-wise
        start_time = datetime.now()  # A timer for monitoring performance
        url = placeholder + str(page)
        browser.get(url)
        rows = BeautifulSoup(browser.page_source, Constants.HTML_PARSER).select('table.bd_lst > tbody > tr')

        for i, row in enumerate(rows):  # Inspect the rows
            tst_tag = row.select_one('td.time')
            if not tst_tag or not tst_tag.has_attr(tst_attribute):  # Non-regular rows, e.g. notices
                continue
            else:  # Not a notice, a regular row. Determine if worth scanning.
                if ':' not in tst_tag[tst_attribute]:  # Not mature: less than 24 hours.
                    continue  # Move to the next row
                elif prev_row_date is None:  # Not mature: uploaded on the yesterday for sure.
                    prev_row_date = tst_tag.string  # Just update for the next comparison loop.
                    continue  # Move to the next row
                else:
                    row_date = tst_tag.string
                    day_diff = __get_date_difference(row_date)
                    if day_diff <= Constants.TOO_YOUNG_DATE:  # Still, not mature: uploaded on the yesterday.
                        log('#%02d\t\t| Skipping the too young.' % (i + 1))
                        continue  # Move to the next row
                    elif day_diff >= Constants.TOO_OLD_DATE:  # Too old.
                        # No need to scan older rows.
                        log('#%02d\t\t| Skipping the too old.' % (i + 1))
                        log('Page %d took %.2fs. Stop searching for older rows.\n' %
                            (page, common.get_elapsed_sec(start_time)), has_tst=False)
                        return tuple(to_scan)

            # Based on the uploaded time, worth scanning.
            likes_tag = row.select_one('td.m_no > span')
            likes = int(likes_tag.string) if likes_tag else 0
            if likes >= min_likes:  # Compare likes first: a cheaper process
                cate = row.select_one('td.cate').string
                if cate in extensions:  # Compare cate then: a more expensive process
                    title = row.select_one('td.title > a.hx').string.strip()
                    for pattern in common.Constants.IGNORED_TITLE_PATTERNS:  # The most expensive comparison
                        if pattern in title:
                            log('#%02d (%s) %s \t| (ignored) %s' % (i + 1, likes, cate, title))
                            break
                    else:
                        to_scan.append(row.select_one('td.title > a.hx')['href'].split('srl=')[-1])
                        log('#%02d (%s) %s \t| %s' % (i + 1, likes, cate, title))

        log('Page %d took %.2fs.' % (page, common.get_elapsed_sec(start_time)))
        page += 1
    return tuple(to_scan)


def scan_article(url: str):
    browser.get(url)
    soup = BeautifulSoup(browser.page_source, Constants.HTML_PARSER)

    # Retrieve the title.
    article_title_tag = soup.select_one('div.main > div.content div.top_area > h1')
    if article_title_tag:
        article_title = article_title_tag.string
    else:
        log('Error: cannot retrieve the title %s' % url)
        article_title = url.split('/')[-1]

    log('Processing %s <%s>' % (url, article_title,))

    # Retrieve likes.
    likes_tag = soup.select_one('div.btm_area > div.fr > span:nth-child(2) > b')
    if likes_tag:
        likes = likes_tag.string
    else:
        likes = '0'
        log('Error: Cannot retrieve likes from %s' % url)

    # For images
    img_source_tags = soup.select('div#article_1 > div img')
    img_filename_tag = '-i'
    if img_source_tags:
        # Retrieve the file name.
        try:
            local_name = __get_local_name(article_title, url, likes)
            found_img_source = iterate_img_source_tags(img_source_tags, local_name + img_filename_tag)
            if not found_img_source:
                log('Error: <img> tag present, but no source found.\n(%s)' % url)
        except Exception as img_source_err:
            log('Error: %s\n%s\n[Traceback]\n%s' % (img_source_err, url, traceback.format_exc()))

    # For videos
    cate_tag = soup.select_one('strong.cate')
    video_filename_tag = '-v'
    if cate_tag and (cate_tag.string == 'avi' or cate_tag.string == 'jpgif'):
        try:
            WebDriverWait(browser, 12).until(
                expected_conditions.visibility_of_all_elements_located((By.CLASS_NAME, 'gfycatWrap')))
            video_source_tags = soup.select('iframe')
            if video_source_tags:
                local_name = __get_local_name(article_title, url, likes)
                found_video_source = iterate_video_source_tags(video_source_tags, local_name + video_filename_tag)
                if not found_video_source:
                    log('Error: <video> tag present, but no source found.\n(%s)' % url)
        except selenium.common.exceptions.TimeoutException:
            # Usual gfycatWrap not present: check unusual sources present.
            if soup.select('video'):
                video_source_tags = soup.select('video')
                local_name = __get_local_name(article_title, url, likes)
                found_video_source = iterate_video_source_tags(video_source_tags, local_name + video_filename_tag)
                if not found_video_source:
                    log('Error: <video> tag present, but no source found.\n(%s)' % url)
            elif soup.select('iframe'):
                iframe_source_tags = soup.select('iframe')
                # Remove ad sources
                source_attr = 'src'
                ad_source = 'ad.linkprice'
                source_tags_no_ads = []
                for tag in iframe_source_tags:
                    if not (tag.has_attr(source_attr) and ad_source in tag[source_attr]):
                        source_tags_no_ads.append(tag)
                local_name = __get_local_name(article_title, url, likes)
                if source_tags_no_ads:
                    found_video_source = iterate_video_source_tags(source_tags_no_ads, local_name + video_filename_tag)
                    if not found_video_source:
                        log('Error: <video> tag present, but no source found.\n(%s)' % url)
            else:
                log('Video player not found.\n(%s).' % url)
        except Exception as video_source_err:
            log('Error: %s\n(%s)\n[Traceback]\n%s' % (video_source_err, url, traceback.format_exc()))


def __get_local_name(article_title: str, url: str, likes: str):
    article_id = url.split('/')[-1]
    channel_id = url.split('/')[-2]
    domain_tag = 'gg'
    formatted_likes = '%03d' % int(likes)

    formatted_title = article_title.strip()
    for prohibited_char in common.Constants.PROHIBITED_CHARS:
        formatted_title = formatted_title.replace(prohibited_char, '_')
    return '%s-%s-%s-%s-%s' % (domain_tag, channel_id, formatted_likes, formatted_title, article_id)


def iterate_img_source_tags(source_tags, file_name) -> bool:
    has_source = False
    src_attribute = 'src'
    content_type_attribute = 'content-type'
    extension = 'tmp'

    for i, tag in enumerate(source_tags):
        if tag.has_attr(src_attribute):
            if not has_source:
                has_source = True
            source_url = tag[src_attribute]

            # Retrieve the extension.
            chunk = source_url.split('.')[-1]
            if chunk in Constants.EXTENSION_CANDIDATES:
                extension = chunk
            else:
                header = requests.head(source_url).headers
                if content_type_attribute in header:
                    category, extension = header[content_type_attribute].split('/')
                    if extension not in Constants.EXTENSION_CANDIDATES:
                        log('Error: unexpected %s/%s\n(%s)' % (category, extension, source_url))

            if extension == 'tmp':  # The extension not updated.
                log('Error: extension cannot be specified.\n(%s)' % source_url)

            # Download the file.
            downloader.download(source_url, '%s-%02d.%s' % (file_name, i, extension))
    return has_source


def iterate_video_source_tags(source_tags, file_name) -> bool:
    has_source = False
    src_attribute = 'src'
    extension = 'mp4'
    raw_sources = []
    is_numbering = True if len(source_tags) > 1 else False
    for i, tag in enumerate(source_tags):  # Extract source urls from tags
        if tag.has_attr(src_attribute):
            for candidate in Constants.VIDEO_SOURCE_CANDIDATES:
                if candidate in tag[src_attribute]:
                    if not has_source:
                        has_source = True
                    raw_sources.append(tag[src_attribute])
        elif tag.select('source'):  # <tag><source src="https://...">
            for source in tag.select('source'):
                if source.has_attr(src_attribute):
                    if not has_source:
                        has_source = True
                    raw_sources.append(source[src_attribute])

        if has_source:
            for raw_source in raw_sources:  # ['https://gfycat.com/xxx', ...]
                chunk = raw_source.split('.')[-1]
                if len(chunk) <= 4 and chunk in Constants.EXTENSION_CANDIDATES:  # The url directs exactly to the file.
                    source_url = raw_source
                    extension = chunk
                else:  # The url directs to a wrapper. Guess the file name and extension.
                    if Constants.VIDEO_SOURCE_CANDIDATES[0] in raw_source:
                        video_name = raw_source.split('/')[-1]
                        source_url = 'https://thumbs.gfycat.com/%s-mobile.mp4' % video_name
                    else:
                        source_url = raw_source
                # Download the file.
                if is_numbering:
                    downloader.download(source_url, '%s-%02d.%s' % (file_name, i, extension))
                else:
                    downloader.download(source_url, '%s.%s' % (file_name, extension))
    return has_source


if Constants.IS_START_POSTPONED:
    time.sleep(random.uniform(120, 3600))
browser = initiate_browser()
try:
    for board_name, board_min_likes, extension_str in Constants.BOARDS:
        board_start_time = datetime.now()
        target_extensions = tuple(extension_str.split('-'))
        board = Constants.PAGE_PLACEHOLDER.replace('%s', board_name.strip('/'))
        scan_list = get_entries_to_scan(board, target_extensions, int(board_min_likes),
                                        Constants.SCANNING_SPAN, Constants.STARTING_PAGE)
        for article_no in scan_list:
            article_url = Constants.ROOT_DOMAIN + board_name + article_no
            scan_article(article_url)
        log('Finished scanning %s in %d min.\n' %
            (board + str(Constants.STARTING_PAGE), int(common.get_elapsed_sec(board_start_time) / 60)), False)

except Exception as e:
    log('[Error] %s\n[Traceback]\n%s' % (e, traceback.format_exc()))
finally:
    browser.quit()