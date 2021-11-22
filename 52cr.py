import downloader
import common
import random
import traceback
from datetime import datetime
import requests
from bs4 import BeautifulSoup


class Constants:
    EXTENSION_CANDIDATES = ('jpg', 'jpeg', 'png', 'gif', 'jfif', 'webp', 'mp4', 'webm', 'mov')

    ROOT_DOMAIN = common.build_tuple('52_DOMAINS.pv')
    IGNORED_URLS = common.build_tuple('52_IGNORED_URLS.pv')

    TOO_YOUNG_DAY = 0
    TOO_OLD_DAY = 2
    SCANNING_SPAN = 20
    STARTING_PAGE = 1


def log(message: str, has_tst: bool = True):
    path = common.read_from_file('52_LOG_PATH.pv')
    common.log(message, path, has_tst)


def __get_local_name(doc_title, url):
    doc_id = url.split('/')[-1]  # The document id(e.g. '373719')
    formatted_title = doc_title.strip()
    for prohibited_char in common.Constants.PROHIBITED_CHARS:
        formatted_title = formatted_title.replace(prohibited_char, '_')
    return formatted_title + '-' + doc_id


def scan_article(url: str):
    soup = BeautifulSoup(requests.get(url).text, common.Constants.HTML_PARSER)
    article_title = soup.select_one('h1.ah-title > a').string
    local_name = __get_local_name(article_title, url)
    domain_tag = '52'
    body_css_selector = 'div.article-content '

    img_source_tags = soup.select(body_css_selector + 'img')
    if img_source_tags:  # Images present
        try:
            downloader.iterate_source_tags(img_source_tags, '%s-%s-%s' % (domain_tag, local_name, 'i'), url)
        except Exception as img_source_exception:
            log('Error: %s\n%s\n[Traceback]\n%s' % (img_source_exception, url, traceback.format_exc()))

    video_source_tags = soup.select(body_css_selector + 'video')
    if video_source_tags:  # Videos present
        try:
            downloader.iterate_source_tags(video_source_tags, '%s-%s-%s' % (domain_tag, local_name, 'v'), url)
        except Exception as video_source_exception:
            log('Error: %s\n%s\n[Traceback]\n%s' % (video_source_exception, url, traceback.format_exc()))

    link_tags = soup.select(body_css_selector + 'a')
    link_attr = 'href'
    external_link_tags = []
    if link_tags:
        for source in link_tags:
            if source.has_attr(link_attr):
                for ignored_url in Constants.IGNORED_URLS:
                    if ignored_url in source[link_attr]:
                        break
                else:
                    external_link_tags.append(source)
    if external_link_tags:
        try:
            downloader.iterate_source_tags(external_link_tags, '%s-%s-%s' % (domain_tag, local_name, 'a'), url)
        except Exception as video_source_exception:
            log('Error: %s\n%s\n[Traceback]\n%s' % (video_source_exception, url, traceback.format_exc()))


def get_entries_to_scan(placeholder: str, scanning_span: int, page: int = 1) -> ():
    max_page = page + scanning_span - 1  # To prevent infinite looping
    to_scan = []

    while page <= max_page:  # Page-wise
        start_time = datetime.now()  # A timer for monitoring performance
        url = placeholder + str(page)
        soup = BeautifulSoup(requests.get(url).text, common.Constants.HTML_PARSER)
        rows = soup.select('div.ab-webzine > div.wz-item')

        for i, row in enumerate(rows):  # Inspect the rows
            try:
                tst_str = row.select_one('div.wz-item-meta > span > span.date').string
                day_diff = common.get_date_difference(tst_str)
                if day_diff:
                    if day_diff <= Constants.TOO_YOUNG_DAY:  # Still, not mature: uploaded on the yesterday.
                        log('#%02d | Skipping the too young.' % (i + 1), False)
                        continue  # Move to the next row
                    elif day_diff >= Constants.TOO_OLD_DAY:  # Too old.
                        log('#%02d | Skipping the too old.' % (i + 1), False)
                        # No need to scan older rows.
                        log('Page %d took %.1f". Stop searching for older rows.\n'
                            % (page, common.get_elapsed_sec(start_time)), False)
                        return tuple(to_scan)
                    else:  # Mature
                        try:
                            title = row.select_one('div.wz-item-header > a > span.title').contents[0].strip()
                        except Exception as title_exception:
                            title = '%05d' % random.randint(1, 99999)
                            log('Error: cannot retrieve article title of row %d.(%s)\n(%s)' %
                                (i + 1, title_exception, url))
                        for pattern in common.Constants.IGNORED_TITLE_PATTERNS:
                            if pattern in title:
                                log('#%02d | (ignored) %s' % (i + 1, title), False)
                                break
                        else:
                            article_url = row.select_one('a.ab-link')['href'].split('=')[-1]
                            to_scan.append(article_url)
                            log('#%02d | %s' % (i + 1, title), False)
            except Exception as row_exception:
                log('Error: cannot process row %d from %s.(%s)' % (i + 1, url, row_exception))
                continue
        log('Page %d took %.1f".' % (page, common.get_elapsed_sec(start_time)), False)
        common.pause_briefly(0.5, 2.5)
        page += 1
    return tuple(to_scan)


def process_domain(domains: tuple, scanning_span: int, starting_page: int = 1):
    try:
        for domain in domains:
            domain_start_time = datetime.now()
            log('Looking up %s' % domain)
            page_index = 'index.php?mid=post&page='
            scan_list = get_entries_to_scan(domain + page_index, scanning_span, starting_page)
            for i, article_no in enumerate(scan_list):  # [32113, 39213, 123412, ...]
                common.pause_briefly()
                article_url = domain + 'post/' + str(article_no)
                scan_start_time = datetime.now()
                scan_article(article_url)
                log('Scanned %d/%d articles(%.1f")' %
                    (i + 1, len(scan_list), common.get_elapsed_sec(scan_start_time)), False)
            log('Finished scanning %s in %d min.' % (domain, int(common.get_elapsed_sec(domain_start_time) / 60)))
    except Exception as normal_domain_exception:
        log('[Error] %s\n[Traceback]\n%s' % (normal_domain_exception, traceback.format_exc(),))


if __name__ == "__main__":
    process_domain(Constants.ROOT_DOMAIN, scanning_span=Constants.SCANNING_SPAN, starting_page=Constants.STARTING_PAGE)
