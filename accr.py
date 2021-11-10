import os
import random
import time
import traceback
from datetime import datetime
import requests
from bs4 import BeautifulSoup
from PIL import Image

HTML_PARSER = 'html.parser'
EXTENSION_CANDIDATES = ('jpg', 'jpeg', 'png', 'gif', 'jfif', 'webp', 'mp4', 'webm', 'mov')
FILE_NAME_IGNORED_PATTERNS = ('028c715135212dd447915ed16949f7532588d3d95d113cada85703d1ef26',
                              'fc13c25d018ccbde127b02044b6e4de17f28725faf1b891422ba6878e9f',
                              'blocked.png')
TITLE_IGNORED_PATTERNS = ('코스프레', '코스어')
TOO_YOUNG_DAY = 1
TOO_OLD_DAY = 3


def log(message: str):
    with open(Path.LOG_PATH, 'a') as f:
        f.write('%s\t(%s)\n' % (message, __get_str_time()))
    print(message)


def read_from_file(path: str):
    with open(path) as f:
        return f.read().strip('\n')


def build_tuple(path: str):
    with open(path) as f:
        content = f.read().strip('\n')
    lines = content.split('\n')
    info = []
    for line in lines:
        info.append(tuple(line.split(',')))
    return tuple(info)


class Path:
    # urls and paths in String
    NORMAL_DOMAIN_INFOS = build_tuple('NORMAL_DOMAINS.pv')
    PROXY_DOMAIN_INFOS = build_tuple('PROXY_DOMAINS.pv')
    __ignored_domain_str = read_from_file('IGNORED_DOMAINS.pv')
    IGNORED_DOMAINS = tuple(__ignored_domain_str.split('\n'))

    DRIVER_PATH = read_from_file('DRIVER_PATH.pv')
    DOWNLOAD_PATH = read_from_file('DOWNLOAD_PATH.pv')
    LOG_PATH = read_from_file('LOG_PATH.pv')
    DUMP_PATH = read_from_file('DUMP_PATH.pv')


def download(url: str, local_name: str):
    # Set the absolute path to store the downloaded file.
    if not os.path.exists(Path.DOWNLOAD_PATH):
        os.makedirs(Path.DOWNLOAD_PATH)  # create folder if it does not exist

    # Set the download target.
    r = requests.get(url, stream=True)

    file_path = os.path.join(Path.DOWNLOAD_PATH, local_name)
    if r.ok:
        with open(file_path, 'wb') as f:
            for chunk in r.iter_content(chunk_size=1024 * 8):
                if chunk:
                    f.write(chunk)
                    f.flush()
                    os.fsync(f.fileno())
    else:  # HTTP status code 4XX/5XX
        log("Error: Download failed.(status code {}\n{})".format(r.status_code, r.text) + ' (%s)' % __get_str_time)

    if local_name.endswith('webp'):
        convert_webp_to_png(Path.DOWNLOAD_PATH, local_name)


def convert_webp_to_png(stored_dir, filename):
    ext = 'png'
    stored_path = os.path.join(stored_dir, filename)
    img = Image.open(stored_path).convert("RGB")
    new_filename = __split_on_last_pattern(filename, '.')[0] + '.' + ext
    new_path = os.path.join(stored_dir, new_filename)
    img.save(new_path, ext)
    os.remove(stored_path)


def get_tor_session():
    req = requests.session()
    # Tor uses the 9050 port as the default socks port
    req.proxies = {'http': 'socks5://127.0.0.1:9050',
                   'https': 'socks5://127.0.0.1:9050'}
    return req


def __get_elapsed_sec(start_time) -> float:
    end_time = datetime.now()
    return (end_time - start_time).total_seconds()


# Split on the pattern, but always returning a list with length of 2.
def __split_on_last_pattern(string: str, pattern: str) -> ():
    last_piece = string.split(pattern)[-1]  # domain.com/image.jpg -> jpg
    leading_chunks = string.split(pattern)[:-1]  # [domain, com/image]
    leading_piece = pattern.join(leading_chunks)  # domain.com/image
    return leading_piece, last_piece  # (domain.com/image, jpg)


def remove_extension(string: str) -> str:
    return __split_on_last_pattern(string, '.')[0]


def __get_str_time() -> str:
    return str(datetime.now()).split('.')[0]


def __get_date_difference(tst_str: str) -> int:
    date = datetime.strptime(tst_str, '%Y.%m.%d')  # 2021.11.07
    now = datetime.now()
    return (now - date).days


def __get_local_name(doc_title, url):
    doc_id = url.split('/')[-1].split('?')[0]  # The document id(e.g. '373719')
    try:
        title = doc_title.strip().replace(' ', '-').replace('.', '-').replace('/', '-')
        return title + '-' + doc_id
    except Exception as filename_exception:
        log('Error: cannot format filename %s. (%s)' % (doc_title, filename_exception))
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


def iterate_source_tags(source_tags, file_name, from_article_url):
    attribute = None
    src_attribute = 'src'
    link_attribute = 'href'
    content_type_attribute = 'content-type'
    extension = 'tmp'

    is_numbering = True if len(source_tags) > 1 else False
    for i, tag in enumerate(source_tags):
        if tag.has_attr(src_attribute):  # e.g. <img src = "...">
            attribute = src_attribute
        elif tag.has_attr(link_attribute):  # e.g. <a href = "...">
            attribute = link_attribute
        if attribute:
            raw_source = tag[attribute].split('?type')[0]
            source_url = 'https:' + raw_source if raw_source.startswith('//') else raw_source
            # Check the ignored file name list
            for ignored_pattern in FILE_NAME_IGNORED_PATTERNS:
                if ignored_pattern in source_url:
                    log('Ignored %s.\n(Article: %s' % (source_url, from_article_url))
                    continue  # Skip this source tag.

            # Retrieve the extension.
            header = requests.head(source_url).headers
            if content_type_attribute in header:
                category, filetype = header[content_type_attribute].split('/')
                if filetype == 'quicktime':  # 'video/quicktime' represents a mov file.
                    filetype = 'mov'
                # Check the file type.
                if category == 'text':
                    log('A text link: %s\n(Article: %s)' % (source_url, from_article_url))
                    continue  # Skip this source tag.

                if filetype in EXTENSION_CANDIDATES:
                    extension = filetype
                else:
                    log('Error: unexpected %s/%s\n(Article: %s)\n(Source: %s)' %
                        (category, filetype, from_article_url, source_url))
                    # Try extract the extension from the url. (e.g. https://www.domain.com/video.mp4)
                    chunk = source_url.split('.')[-1]
                    if chunk in EXTENSION_CANDIDATES:
                        extension = chunk

            if extension == 'tmp':  # After all, the extension has not been updated.
                log('Error: extension cannot be specified.\n(Article: %s)\n(Source: %s)' %
                    (from_article_url, source_url))
            print('%s-*.%s on %s' % (file_name, extension, source_url))
            # Download the file.
            if is_numbering:
                download(source_url, '%s-%03d.%s' % (file_name, i, extension))
            else:
                download(source_url, '%s.%s' % (file_name, extension))
        else:
            log('Error: Tag present, but no source found.\n(Tag: %s)\n(%s: Article)' % (tag, from_article_url))


def scan_article(url: str, proxy=False):
    soup = BeautifulSoup(requests.get(url).text, HTML_PARSER) if not proxy else get_proxy_soup(url)
    doc_title_long = soup.select_one('head > title').string
    doc_title_short = __split_on_last_pattern(doc_title_long, ' - ')[0].strip()
    local_name = __get_local_name(doc_title_short, url)

    img_source_tags = soup.select('div.article-content img')
    if img_source_tags:  # Images present
        try:
            iterate_source_tags(img_source_tags, local_name + '-i', url)
        except Exception as img_source_exception:
            log('Error: %s\n%s\n[Traceback]\n%s' % (img_source_exception, url, traceback.format_exc()))

    video_source_tags = soup.select('div.article-content video')
    if video_source_tags:  # Videos present
        try:
            iterate_source_tags(video_source_tags, local_name + '-v', url)
        except Exception as video_source_exception:
            log('Error: %s\n%s\n[Traceback]\n%s' % (video_source_exception, url, traceback.format_exc()))

    link_tags = soup.select('div.article-content a')
    link_attr = 'href'
    external_link_tags = []
    if link_tags:
        for source in link_tags:
            if source.has_attr(link_attr):
                for ignored_url in Path.IGNORED_DOMAINS:
                    if ignored_url in source[link_attr]:
                        break
                else:
                    external_link_tags.append(source)
    if external_link_tags:
        try:
            iterate_source_tags(external_link_tags, local_name + '-a', url)
        except Exception as video_source_exception:
            log('Error: %s\n%s\n[Traceback]\n%s' % (video_source_exception, url, traceback.format_exc()))


def get_entries_to_scan(placeholder: str, min_likes: int, page: int = 1) -> ():
    max_page = page + min_likes * 3 + 3  # To prevent infinite while looping
    to_scan = []
    has_regular_row = True  # True for the first page

    while page <= max_page and has_regular_row:  # Page-wise
        start_time = datetime.now()  # A timer for monitoring performance
        url = placeholder + str(page)
        soup = BeautifulSoup(requests.get(url).text, HTML_PARSER)
        rows = soup.select('div.list-table > a.vrow')
        has_regular_row = False

        for i, row in enumerate(rows):  # Inspect the rows
            is_to_scan = False
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
                        log('Page %d took %.2fs. Stop searching.\n' % (page, __get_elapsed_sec(start_time)))
                        return tuple(to_scan)
                    else:  # Mature
                        is_to_scan = True

                if is_to_scan:  # Based on the uploaded time, worth scanning.
                    if int(likes) >= min_likes:  # Compare likes first: a cheaper process
                        try:
                            title = row.select_one('div.vrow-top > span.vcol > span.title').contents[0].strip()
                        except Exception as title_exception:
                            title = '%04d' % random.randint(1, 9999)
                            log('Error: cannot retrieve article title of row %d.(%s)\n(%s)' %
                                (i + 1, title_exception, url))
                        for pattern in TITLE_IGNORED_PATTERNS:  # Compare the string pattern: the most expensive
                            if pattern in title:
                                log('#%02d (%s)\t| (ignored) %s' % (i + 1, likes, title))
                                break
                        else:
                            to_scan.append(row['href'].split('?')[0].split('/')[-1])
                            log('#%02d (%s)\t| %s' % (i + 1, likes, title))

        log('Page %d took %.2fs.' % (page, __get_elapsed_sec(start_time)))
        time.sleep(random.uniform(0.5, 2.5))
        page += 1
    return tuple(to_scan)


def process_domain(domain_infos: tuple, page: int = 1):
    try:
        for domain_info in domain_infos:
            url = domain_info[0]
            min_likes = int(domain_info[1])
            log('Looking up %s.' % url)
            page_index = '?cut=%d&p=' % min_likes
            scan_list = get_entries_to_scan(url + page_index, min_likes, page)
            for i, article_no in enumerate(scan_list):  # [32113, 39213, 123412, ...]
                pause = random.uniform(3, 6)
                print('Pause for %.1f.' % pause)
                time.sleep(pause)

                article_url = url + str(article_no)
                scan_start_time = datetime.now()
                scan_article(article_url)
                log('Scanned %d/%d articles(%.1f")' % (i, len(scan_list), __get_elapsed_sec(scan_start_time)))
    except Exception as normal_domain_exception:
        log('[Error] %s\n[Traceback]\n%s' % (normal_domain_exception, traceback.format_exc(),))


time.sleep(random.uniform(60, 2100))
process_domain(Path.NORMAL_DOMAIN_INFOS)
time.sleep(random.uniform(30, 180))
process_domain(Path.PROXY_DOMAIN_INFOS)
