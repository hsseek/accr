import random
import traceback
from datetime import datetime
import requests
from bs4 import BeautifulSoup
import common
import downloader


class Constants:
    SUBDIRECTORIES = common.build_tuple_of_tuples('AC_SUBDIRECTORIES.pv')
    IGNORED_LINKS = common.build_tuple('AC_IGNORED_LINKS.pv')
    IGNORED_FILE_NAMES = common.build_tuple('AC_IGNORED_FILENAMES.pv')

    TOO_YOUNG_DAY = 1
    TOO_OLD_DAY = 3
    SCANNING_SPAN = 10
    STARTING_PAGE = 1


def log(message: str, has_tst: bool = True):
    path = common.read_from_file('AC_LOG_PATH.pv')
    common.log(message, path, has_tst)


def __get_local_name(article_title: str, url: str, likes: str):
    url_chunks = url.split('?')[0].split('/')
    article_id = url_chunks[-1]
    chan_id = url_chunks[-2]
    formatted_likes = '%03d' % int(likes)
    formatted_title = article_title.strip()
    for prohibited_char in common.Constants.PROHIBITED_CHARS:
        formatted_title = formatted_title.replace(prohibited_char, '_')
    return 'ac-' + chan_id + '-' + formatted_likes + '-' + formatted_title + '-' + article_id


def get_article_soup(url: str) -> BeautifulSoup:
    session = requests.session()
    soup = BeautifulSoup(session.get(url).text, common.Constants.HTML_PARSER)
    if not soup.select_one('div.article-body > div.text-muted'):
        # No need to configure proxy.
        print('Article content accessible. Do not configure proxy.')
        return soup

    free_proxy_list = common.get_free_proxies()
    for i, proxy in enumerate(free_proxy_list):
        try:
            session.proxies = {'http': 'http://' + proxy,
                               'https://': 'https://' + proxy}
            soup = BeautifulSoup(session.get(url).text, common.Constants.HTML_PARSER)
            if not soup.select_one('div.article-body > div.text-muted'):
                print('Proxy: %s worked.(trial %d)' % (proxy, i + 1))
                return soup
        except Exception as e:
            print('%s failed.(%s)' % (proxy, e))


def scan_article(url: str):
    soup = get_article_soup(url)
    # Extract title and likes.
    article_title_long = soup.select_one('head > title').string
    article_title_short = common.split_on_last_pattern(article_title_long, ' - ')[0].strip()
    log('Processing <%s> (%s)' % (article_title_short, url))
    likes = soup.select_one('div.article-head > div.info-row > div.article-info > span.body').string

    local_name = __get_local_name(article_title_short, url, likes)
    body_css_selector = 'div.article-content '

    img_source_tags = soup.select(body_css_selector + 'img')
    if img_source_tags:  # Images present
        try:
            downloader.iterate_source_tags(img_source_tags, local_name + '-i', url, Constants.IGNORED_FILE_NAMES)
        except Exception as img_source_exception:
            log('Error: %s\n%s\n[Traceback]\n%s' % (img_source_exception, url, traceback.format_exc()))

    video_source_tags = soup.select(body_css_selector + 'video')
    if video_source_tags:  # Videos present
        try:
            downloader.iterate_source_tags(video_source_tags, local_name + '-v', url)
        except Exception as video_source_exception:
            log('Error: %s\n%s\n[Traceback]\n%s' % (video_source_exception, url, traceback.format_exc()))

    link_tags = soup.select(body_css_selector + 'a')
    link_attr = 'href'
    external_link_tags = []
    if link_tags:
        for source in link_tags:
            if source.has_attr(link_attr):
                for ignored_url in Constants.IGNORED_LINKS:
                    if ignored_url in source[link_attr]:
                        log('Ignoring based on url: %s\n(Article:%s)' % (source[link_attr], url))
                        break
                else:
                    external_link_tags.append(source)
    if external_link_tags:
        try:
            downloader.iterate_source_tags(external_link_tags, local_name + '-a', url)
        except Exception as video_source_exception:
            log('Error: %s\n%s\n[Traceback]\n%s' % (video_source_exception, url, traceback.format_exc()))


def get_entries_to_scan(placeholder: str, min_likes: int, scanning_span: int, page: int = 1) -> ():
    max_page = page + scanning_span - 1  # To prevent infinite looping
    to_scan = []
    has_regular_row = True  # True for the first page

    while page <= max_page and has_regular_row:  # Page-wise
        start_time = datetime.now()  # A timer for monitoring performance
        url = placeholder + str(page)
        soup = BeautifulSoup(requests.get(url).text, common.Constants.HTML_PARSER)
        rows = soup.select('div.list-table > a.vrow')
        has_regular_row = False

        for i, row in enumerate(rows):  # Inspect the rows
            try:
                likes_tag = row.select_one('div.vrow-bottom > span.col-rate')
                if not likes_tag:  # Unified notices or other irregular rows.
                    continue
                likes = row.select_one('div.vrow-bottom > span.col-rate').string
                if not likes.isspace():
                    has_regular_row = True
                    tst_str = row.select_one('div.vrow-bottom time').string
                    if ':' in tst_str:  # Not mature: less than 24 hours.
                        continue  # Move to the next row
                    else:
                        day_diff = common.get_date_difference(tst_str)
                        if day_diff <= Constants.TOO_YOUNG_DAY:  # Still, not mature: uploaded on the yesterday.
                            print('#%02d (%s) \t| Skipping the too young.' % (i + 1, likes))
                            continue  # Move to the next row
                        elif day_diff >= Constants.TOO_OLD_DAY:  # Too old.
                            print('#%02d (%s) \t| Skipping the too old.' % (i + 1, likes))
                            # No need to scan older rows.
                            log('Page %d took %.1f". Stop searching for older rows.\n' %
                                (page, common.get_elapsed_sec(start_time)), False)
                            return tuple(to_scan)
                        else:  # Mature
                            if int(likes) >= min_likes:  # Compare likes first: a cheaper process
                                try:
                                    title = row.select_one('div.vrow-top > span.vcol > span.title').string.strip()
                                except Exception as title_exception:
                                    title = '%05d' % random.randint(1, 99999)
                                    log('Error: cannot retrieve article title of row %d.(%s)\n(%s)' %
                                        (i + 1, title_exception, url))
                                for pattern in common.Constants.IGNORED_TITLE_PATTERNS:
                                    if pattern in title:
                                        log('#%02d (%s) \t| (ignored) %s' % (i + 1, likes, title), False)
                                        break
                                else:
                                    to_scan.append(row['href'].split('?')[0].split('/')[-1])
                                    log('#%02d (%s) \t| %s' % (i + 1, likes, title))
            except Exception as row_exception:
                log('Error: cannot process row %d from %s.(%s)' % (i + 1, url, row_exception))
                continue
        log('Page %d took %.1f".' % (page, common.get_elapsed_sec(start_time)), False)
        common.pause_briefly()
        page += 1
    return tuple(to_scan)


def process_domain(domains: tuple, scanning_span: int, starting_page: int = 1):
    try:
        for domain_info in domains:
            domain_start_time = datetime.now()
            url = domain_info[0]
            min_likes = int(domain_info[1])
            log('Looking up %s' % url)
            page_index = '?cut=%d&p=' % min_likes
            scan_list = get_entries_to_scan(url + page_index, min_likes, scanning_span, starting_page)
            for i, article_no in enumerate(scan_list):  # [32113, 39213, 123412, ...]
                common.pause_briefly()
                article_url = url + str(article_no)
                scan_start_time = datetime.now()
                scan_article(article_url)
                log('Scanned %d/%d articles(%.1f")' %
                    (i + 1, len(scan_list), common.get_elapsed_sec(scan_start_time)), False)
            log('Finished scanning %s in %d min.\n' %
                (url, int(common.get_elapsed_sec(domain_start_time) / 60)), False)
    except Exception as normal_domain_exception:
        log('[Error] %s\n[Traceback]\n%s' % (normal_domain_exception, traceback.format_exc(),))


if __name__ == "__main__":
    process_domain(Constants.SUBDIRECTORIES, Constants.SCANNING_SPAN, Constants.STARTING_PAGE)
    log("Script finished.")
