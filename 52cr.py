import downloader
import common
import random
import time
import traceback
from datetime import datetime
import requests
from bs4 import BeautifulSoup

HTML_PARSER = 'html.parser'
EXTENSION_CANDIDATES = ('jpg', 'jpeg', 'png', 'gif', 'jfif', 'webp', 'mp4', 'webm', 'mov')
FILE_NAME_IGNORED_PATTERNS = ('028c715135212dd447915ed16949f7532588d3d95d113cada85703d1ef26',
                              'fc13c25d018ccbde127b02044b6e4de17f28725faf1b891422ba6878e9f',
                              'blocked.png')
TITLE_IGNORED_PATTERNS = ('코스프레', '코스어')
TOO_YOUNG_DAY = 0
TOO_OLD_DAY = 2


def log(message: str, has_tst: bool = True):
    path = common.read_from_file('52_LOG_PATH.pv')
    common.log(message, path, has_tst)


ROOT_DOMAIN = common.build_tuple('52_DOMAINS.pv')
IGNORED_DOMAINS = common.build_tuple('52_IGNORED_DOMAINS.pv')
LOG_PATH = common.read_from_file('52_LOG_PATH.pv')


def __get_local_name(doc_title, url):
    doc_id = url.split('srl=')[-1]  # The document id(e.g. '373719')
    try:
        title = doc_title.strip().replace(' ', '-').replace('.', '-').replace('/', '-')
        return title + '-' + doc_id
    except Exception as filename_exception:
        log('Error: cannot format filename %s. (%s)' % (doc_title, filename_exception))
        return doc_id


def scan_article(url: str):
    soup = BeautifulSoup(requests.get(url).text, HTML_PARSER)
    article_title = soup.select_one('h1.ah-title > a').string
    local_name = __get_local_name(article_title, url)
    DOMAIN_TAG = '-52'
    body_css_selector = 'div.article-content '

    img_source_tags = soup.select(body_css_selector + 'img')
    if img_source_tags:  # Images present
        try:
            downloader.iterate_source_tags(img_source_tags, local_name + DOMAIN_TAG + '-i', url)
        except Exception as img_source_exception:
            log('Error: %s\n%s\n[Traceback]\n%s' % (img_source_exception, url, traceback.format_exc()))

    video_source_tags = soup.select(body_css_selector + 'video')
    if video_source_tags:  # Videos present
        try:
            downloader.iterate_source_tags(video_source_tags, local_name + DOMAIN_TAG + '-v', url)
        except Exception as video_source_exception:
            log('Error: %s\n%s\n[Traceback]\n%s' % (video_source_exception, url, traceback.format_exc()))

    link_tags = soup.select(body_css_selector + 'a')
    link_attr = 'href'
    external_link_tags = []
    if link_tags:
        for source in link_tags:
            if source.has_attr(link_attr):
                for ignored_url in IGNORED_DOMAINS:
                    if ignored_url in source[link_attr]:
                        break
                else:
                    external_link_tags.append(source)
    if external_link_tags:
        try:
            downloader.iterate_source_tags(external_link_tags, local_name + DOMAIN_TAG + '-a', url)
        except Exception as video_source_exception:
            log('Error: %s\n%s\n[Traceback]\n%s' % (video_source_exception, url, traceback.format_exc()))


def get_entries_to_scan(placeholder: str, page: int = 1) -> ():
    pages_to_scan = 4
    max_page = page + pages_to_scan - 1  # To prevent infinite looping
    to_scan = []

    while page <= max_page:  # Page-wise
        start_time = datetime.now()  # A timer for monitoring performance
        url = placeholder + str(page)
        soup = BeautifulSoup(requests.get(url).text, HTML_PARSER)
        rows = soup.select('div.ab-webzine > div.wz-item')

        for i, row in enumerate(rows):  # Inspect the rows
            tst_str = row.select_one('div.wz-item-meta > span > span.date').string
            day_diff = common.get_date_difference(tst_str)
            if day_diff:
                if day_diff <= TOO_YOUNG_DAY:  # Still, not mature: uploaded on the yesterday.
                    continue  # Move to the next row
                elif day_diff >= TOO_OLD_DAY:  # Too old.
                    # No need to scan older rows.
                    log('Page %d took %.2fs. Stop searching.\n' % (page, common.get_elapsed_sec(start_time)), False)
                    return tuple(to_scan)
                else:  # Mature
                    try:
                        title = row.select_one('div.wz-item-header > a > span.title').contents[0].strip()
                    except Exception as title_exception:
                        title = '%05d' % random.randint(1, 99999)
                        log('Error: cannot retrieve article title of row %d.(%s)\n(%s)' %
                            (i + 1, title_exception, url))
                    for pattern in TITLE_IGNORED_PATTERNS:  # Compare the string pattern: the most expensive
                        if pattern in title:
                            log('#%02d | (ignored) %s' % (i + 1, title), False)
                            break
                    else:
                        article_url = row.select_one('a.ab-link')['href'].split('=')[-1]
                        to_scan.append(article_url)
                        log('#%02d | %s' % (i + 1, title), False)
        log('Page %d took %.2fs.' % (page, common.get_elapsed_sec(start_time)), False)
        time.sleep(random.uniform(0.5, 2.5))
        page += 1
    return tuple(to_scan)


def process_domain(domains: tuple, starting_page: int = 1):
    try:
        for domain in domains:
            domain_start_time = datetime.now()
            url = domain
            log('Looking up %s.' % url)
            page_index = 'index.php?mid=post&page='
            scan_list = get_entries_to_scan(url + page_index, starting_page)
            for i, article_no in enumerate(scan_list):  # [32113, 39213, 123412, ...]
                pause = random.uniform(3, 6)
                print('Pause for %.1f.' % pause)
                time.sleep(pause)

                article_url = url + 'post/' + str(article_no)
                scan_start_time = datetime.now()
                scan_article(article_url)
                log('Scanned %d/%d articles(%.1f")' % (i + 1, len(scan_list), common.get_elapsed_sec(scan_start_time)))
            log('Finished scanning %s in %d min.' % (url, int(common.get_elapsed_sec(domain_start_time) / 60)))
    except Exception as normal_domain_exception:
        log('[Error] %s\n[Traceback]\n%s' % (normal_domain_exception, traceback.format_exc(),))


# time.sleep(random.uniform(60, 2100))
# process_domain(ROOT_DOMAIN, starting_page=1)
scan_article('http://www.red52.kr/index.php?mid=post&page=2&document_srl=29478')