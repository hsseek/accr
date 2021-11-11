import os
import downloader
import common
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
TOO_YOUNG_DAY = 0
TOO_OLD_DAY = 2


def log(message: str, has_tst: bool = True):
    path = common.read_from_file('52_LOG_PATH.pv')
    common.log(message, path, has_tst)


ROOT_DOMAIN = common.build_tuple('52_DOMAINS.pv')
IGNORED_DOMAINS = common.build_tuple('52_IGNORED_DOMAINS.pv')
LOG_PATH = common.read_from_file('52_LOG_PATH.pv')


def convert_webp_to_png(stored_dir, filename):
    ext = 'png'
    stored_path = os.path.join(stored_dir, filename)
    img = Image.open(stored_path).convert("RGB")
    new_filename = __split_on_last_pattern(filename, '.')[0] + '.' + ext
    new_path = os.path.join(stored_dir, new_filename)
    img.save(new_path, ext)
    os.remove(stored_path)


def __get_elapsed_sec(start_time) -> float:
    end_time = datetime.now()
    return (end_time - start_time).total_seconds()


# Split on the pattern, but always returning a list with length of 2.
def __split_on_last_pattern(string: str, pattern: str) -> ():
    last_piece = string.split(pattern)[-1]  # domain.com/image.jpg -> jpg
    leading_chunks = string.split(pattern)[:-1]  # [domain, com/image]
    leading_piece = pattern.join(leading_chunks)  # domain.com/image
    return leading_piece, last_piece  # (domain.com/image, jpg)


def __get_str_time() -> str:
    return str(datetime.now()).split('.')[0]


def __get_date_difference(tst_str: str) -> int:
    try:
        date = datetime.strptime(tst_str, '%Y.%m.%d')  # 2021.11.07
        now = datetime.now()
        return (now - date).days
    except Exception as tst_name_exception:
        print(tst_name_exception)


def __get_local_name(doc_title, url):
    doc_id = url.split('/')[-1].split('?')[0]  # The document id(e.g. '373719')
    try:
        title = doc_title.strip().replace(' ', '-').replace('.', '-').replace('/', '-')
        return title + '-' + doc_id
    except Exception as filename_exception:
        log('Error: cannot format filename %s. (%s)' % (doc_title, filename_exception))
        return doc_id


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
                downloader.download(source_url, '%s-%03d.%s' % (file_name, i, extension))
            else:
                downloader.download(source_url, '%s.%s' % (file_name, extension))
        else:
            log('Error: Tag present, but no source found.\n(Tag: %s)\n(%s: Article)' % (tag, from_article_url))


def scan_article(url: str):
    soup = BeautifulSoup(requests.get(url).text, HTML_PARSER)
    article_title = soup.select_one('h1.ah-title > a').string
    local_name = __get_local_name(article_title, url)
    DOMAIN_TAG = '-52'
    body_css_selector = 'div.article-content '

    img_source_tags = soup.select(body_css_selector + 'img')
    if img_source_tags:  # Images present
        try:
            iterate_source_tags(img_source_tags, local_name + DOMAIN_TAG + '-i', url)
        except Exception as img_source_exception:
            log('Error: %s\n%s\n[Traceback]\n%s' % (img_source_exception, url, traceback.format_exc()))

    video_source_tags = soup.select(body_css_selector + 'video')
    if video_source_tags:  # Videos present
        try:
            iterate_source_tags(video_source_tags, local_name + DOMAIN_TAG + '-v', url)
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
            iterate_source_tags(external_link_tags, local_name + DOMAIN_TAG + '-a', url)
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
            day_diff = __get_date_difference(tst_str)
            if day_diff:
                if day_diff <= TOO_YOUNG_DAY:  # Still, not mature: uploaded on the yesterday.
                    continue  # Move to the next row
                elif day_diff >= TOO_OLD_DAY:  # Too old.
                    # No need to scan older rows.
                    log('Page %d took %.2fs. Stop searching.\n' % (page, __get_elapsed_sec(start_time)), False)
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
        log('Page %d took %.2fs.' % (page, __get_elapsed_sec(start_time)), False)
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
                log('Scanned %d/%d articles(%.1f")' % (i + 1, len(scan_list), __get_elapsed_sec(scan_start_time)))
            log('Finished scanning %s in %d min.' % (url, int(__get_elapsed_sec(domain_start_time) / 60)))
    except Exception as normal_domain_exception:
        log('[Error] %s\n[Traceback]\n%s' % (normal_domain_exception, traceback.format_exc(),))


time.sleep(random.uniform(60, 2100))
process_domain(ROOT_DOMAIN, starting_page=1)
