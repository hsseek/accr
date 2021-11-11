import random
import time
import traceback
from datetime import datetime
import requests
from bs4 import BeautifulSoup
import common
import downloader

HTML_PARSER = 'html.parser'
TITLE_IGNORED_PATTERNS = ('코스프레', '코스어')
TOO_YOUNG_DAY = 1
TOO_OLD_DAY = 3

NORMAL_DOMAIN_INFOS = common.build_tuple_of_tuples('AC_NORMAL_DOMAINS.pv')
PROXY_DOMAIN_INFOS = common.build_tuple_of_tuples('AC_PROXY_DOMAINS.pv')
IGNORED_DOMAINS = common.build_tuple('AC_IGNORED_DOMAINS.pv')


def get_tor_session():
    req = requests.session()
    # Tor uses the 9050 port as the default socks port
    req.proxies = {'http': 'socks5://127.0.0.1:9050',
                   'https': 'socks5://127.0.0.1:9050'}
    return req


def __get_date_difference(tst_str: str) -> int:
    try:
        date = datetime.strptime(tst_str, '%Y.%m.%d')  # 2021.11.07
        now = datetime.now()
        return (now - date).days
    except Exception as e:
        print('(%s) The timestamp did not match the format: %s.' % (e, tst_str))


def __get_local_name(doc_title, url):
    doc_id = url.split('/')[-1].split('?')[0]  # The document id(e.g. '373719')
    try:
        title = doc_title.strip().replace(' ', '-').replace('.', '-').replace('/', '-')
        return title + '-' + doc_id
    except Exception as filename_exception:
        common.log('Error: cannot format filename %s. (%s)' % (doc_title, filename_exception))
        return doc_id


def __get_free_proxies():
    url = "https://free-proxy-list.net/"
    # get the HTTP response and construct soup object
    soup = BeautifulSoup(requests.get(url).content, "html.parser")
    proxies = []
    for row in soup.select('div.fpl-list > table.table > tbody > tr'):
        tds = row.find_all("td")
        try:
            ip = tds[0].text.strip()
            port = tds[1].text.strip()
            host = f"{ip}:{port}"
            proxies.append(host)
        except IndexError:
            continue
    return proxies


def get_proxy_soup(url: str) -> BeautifulSoup:
    free_proxy_list = __get_free_proxies()
    session = requests.session()
    for i, proxy in enumerate(free_proxy_list):
        try:
            session.proxies = {'http': 'http://' + proxy,
                               'https://': 'https://' + proxy}
            soup = BeautifulSoup(session.get(url).text, HTML_PARSER)
            if not soup.select_one('div.article-body > div.text-muted'):
                print('Proxy: %s worked.(trial %d)' % (proxy, i + 1))
                return soup
        except Exception as e:
            print('%s failed.(%s)' % (proxy, e))


def __get_ip(session: requests.Session) -> str:
    return session.get("http://httpbin.org/ip").text.split('"')[-2]


def scan_article(url: str, proxy=False):
    soup = BeautifulSoup(requests.get(url).text, HTML_PARSER) if not proxy else get_proxy_soup(url)
    article_title_long = soup.select_one('head > title').string
    article_title_short = common.split_on_last_pattern(article_title_long, ' - ')[0].strip()
    local_name = __get_local_name(article_title_short, url)
    DOMAIN_TAG = '-ac'
    body_css_selector = 'div.article-content '

    img_source_tags = soup.select(body_css_selector + 'img')
    if img_source_tags:  # Images present
        try:
            downloader.iterate_source_tags(img_source_tags, local_name + DOMAIN_TAG + '-i', url)
        except Exception as img_source_exception:
            common.log('Error: %s\n%s\n[Traceback]\n%s' % (img_source_exception, url, traceback.format_exc()))

    video_source_tags = soup.select(body_css_selector + 'video')
    if video_source_tags:  # Videos present
        try:
            downloader.iterate_source_tags(video_source_tags, local_name + DOMAIN_TAG + '-v', url)
        except Exception as video_source_exception:
            common.log('Error: %s\n%s\n[Traceback]\n%s' % (video_source_exception, url, traceback.format_exc()))

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
            common.log('Error: %s\n%s\n[Traceback]\n%s' % (video_source_exception, url, traceback.format_exc()))


def get_entries_to_scan(placeholder: str, min_likes: int, page: int = 1) -> ():
    pages_to_scan = min_likes * 2 + 3
    max_page = page + pages_to_scan - 1  # To prevent infinite looping
    to_scan = []
    has_regular_row = True  # True for the first page

    while page <= max_page and has_regular_row:  # Page-wise
        start_time = datetime.now()  # A timer for monitoring performance
        url = placeholder + str(page)
        soup = BeautifulSoup(requests.get(url).text, HTML_PARSER)
        rows = soup.select('div.list-table > a.vrow')
        has_regular_row = False

        for i, row in enumerate(rows):  # Inspect the rows
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
                    day_diff = __get_date_difference(tst_str)
                    if day_diff <= TOO_YOUNG_DAY:  # Still, not mature: uploaded on the yesterday.
                        continue  # Move to the next row
                    elif day_diff >= TOO_OLD_DAY:  # Too old.
                        # No need to scan older rows.
                        common.log('Page %d took %.2fs. Stop searching.\n' %
                                   (page, common.get_elapsed_sec(start_time)), False)
                        return tuple(to_scan)
                    else:  # Mature
                        if int(likes) >= min_likes:  # Compare likes first: a cheaper process
                            try:
                                title = row.select_one('div.vrow-top > span.vcol > span.title').contents[0].strip()
                            except Exception as title_exception:
                                title = '%05d' % random.randint(1, 99999)
                                common.log('Error: cannot retrieve article title of row %d.(%s)\n(%s)' %
                                    (i + 1, title_exception, url))
                            for pattern in TITLE_IGNORED_PATTERNS:  # Compare the string pattern: the most expensive
                                if pattern in title:
                                    common.log('#%02d (%s)\t| (ignored) %s' % (i + 1, likes, title), False)
                                    break
                            else:
                                to_scan.append(row['href'].split('?')[0].split('/')[-1])
                                common.log('#%02d (%s)\t| %s' % (i + 1, likes, title))
        common.log('Page %d took %.2fs.' % (page, common.get_elapsed_sec(start_time)), False)
        time.sleep(random.uniform(0.5, 2.5))
        page += 1
    return tuple(to_scan)


def process_domain(domain_infos: tuple, page: int = 1):
    try:
        for domain_info in domain_infos:
            domain_start_time = datetime.now()
            url = domain_info[0]
            min_likes = int(domain_info[1])
            common.log('Looking up %s.' % url)
            page_index = '?cut=%d&p=' % min_likes
            scan_list = get_entries_to_scan(url + page_index, min_likes, page)
            for i, article_no in enumerate(scan_list):  # [32113, 39213, 123412, ...]
                pause = random.uniform(3, 6)
                print('Pause for %.1f.' % pause)
                time.sleep(pause)

                article_url = url + str(article_no)
                scan_start_time = datetime.now()
                scan_article(article_url)
                common.log('Scanned %d/%d articles(%.1f")' %
                           (i + 1, len(scan_list), common.get_elapsed_sec(scan_start_time)))
            common.log('Finished scanning %s in %d min.' %
                       (url, int(common.get_elapsed_sec(domain_start_time) / 60)))
    except Exception as normal_domain_exception:
        common.log('[Error] %s\n[Traceback]\n%s' % (normal_domain_exception, traceback.format_exc(),))


time.sleep(random.uniform(60, 2100))
process_domain(NORMAL_DOMAIN_INFOS)
time.sleep(random.uniform(30, 180))
process_domain(PROXY_DOMAIN_INFOS)
