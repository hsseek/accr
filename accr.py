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
                              'fc13c25d018ccbde127b02044b6e4de17f28725faf1b891422ba6878e9f')
TITLE_IGNORED_PATTERNS = ('코스프레', '코스어')
PAGE_INDEX = '?cut=1&p='
TOO_YOUNG_DAY = 1
TOO_OLD_DAY = 3


def log(message: str):
    with open(Path.LOG_PATH, 'a') as f:
        f.write(message + '\n')
    print(message)


def read_from_file(path: str):
    with open(path) as f:
        return f.read().strip('\n')


class Path:
    # urls and paths in String
    __domain_str = read_from_file('ROOT_DOMAIN.pv')
    DOMAIN_PLACEHOLDERS = tuple(__domain_str.split('\n'))
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
    try:
        local_name = doc_title.strip().replace(' ', '-').replace('.', '-').replace('/', '-')
    except Exception as filename_exception:
        log('Error: cannot format filename %s. (%s)' % (doc_title, filename_exception))
        doc_id = url.split('/')[-1].split('?')[0]
        local_name = doc_id
    return local_name


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
                    pass  # Skip this source tag.

            # Retrieve the extension.
            header = requests.head(source_url).headers
            if content_type_attribute in header:
                category, filetype = header[content_type_attribute].split('/')
                if filetype == 'quicktime':  # 'video/quicktime' represents a mov file.
                    filetype = 'mov'
                # Check the file type.
                if category == 'text':
                    log('A text link: %s\n(Article: %s)' % (source_url, from_article_url))
                    pass  # Skip this source tag.
                if filetype in EXTENSION_CANDIDATES:
                    extension = filetype
                else:
                    log('Error: unexpected %s/%s\n(Article: %s)\n(Source: %s)' %
                        (category, extension, from_article_url, source_url))
                    # Try extract the extension from the url. (e.g. https://www.domain.com/video.mp4)
                    chunk = source_url.split('.')[-1]
                    if chunk in EXTENSION_CANDIDATES:
                        extension = chunk

            if extension == 'tmp':  # After all, the extension has not been updated.
                log('Error: extension cannot be specified.\n(Article: %s)\n(Source: %s)' %
                    (from_article_url, source_url))
            print('%s.%s on %s' % (file_name, extension, source_url))
            # Download the file.
            if is_numbering:
                download(source_url, '%s-%02d.%s' % (file_name, i, extension))
            else:
                download(source_url, '%s.%s' % (file_name, extension))
        else:
            log('Error: Tag present, but no source found.\n(Tag: %s)\n(%s: Article)' % (tag, from_article_url))


def scan_article(url: str):
    soup = BeautifulSoup(requests.get(url).text, HTML_PARSER)
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


def get_entries_to_scan(placeholder: str, min_likes: int, page: int) -> ():
    MAX_PAGE = 100
    to_scan = []
    has_regular_row = True  # True for the first page

    while page < MAX_PAGE and has_regular_row:  # Page-wise
        start_time = datetime.now()  # A timer for monitoring performance
        url = placeholder + str(page)
        soup = BeautifulSoup(requests.get(url).text, HTML_PARSER)
        rows = soup.select('div.list-table > a.vrow')
        has_regular_row = False

        for i, row in enumerate(rows):  # Inspect the rows
            is_to_scan = False
            likes = row.select_one('div.vrow-bottom > span.col-rate').string
            if not likes.isspace():
                has_regular_row = True
                tst_str = row.select_one('div.vrow-bottom time').string
                if ':' in tst_str:  # Not mature: less than 24 hours.
                    pass  # Move to the next row
                else:
                    day_diff = __get_date_difference(tst_str)
                    # if day_diff <= TOO_YOUNG_DAY:  # Still, not mature: uploaded on the yesterday.
                    if day_diff <= 0:  # Still, not mature: uploaded on the yesterday.
                        pass  # Move to the next row
                    # elif day_diff >= TOO_OLD_DAY:  # Too old.
                    elif day_diff >= 400:  # Too old.
                        # No need to scan older rows.
                        log('Page %d took %.2fs. Stop searching.\n' % (page, __get_elapsed_sec(start_time)))
                        return tuple(to_scan)
                    else:  # Mature
                        is_to_scan = True

                if is_to_scan:  # Based on the uploaded time, worth scanning.
                    if int(likes) >= min_likes:  # Compare likes first: a cheaper process
                        title = row.select_one('div.vrow-top > span.vcol > span.title').string.strip()
                        for pattern in TITLE_IGNORED_PATTERNS:  # Compare the string pattern: the most expensive
                            if pattern in title:
                                log('#%02d (%s)\t| (ignored) %s' % (i + 1, likes, title))
                                break
                        else:
                            to_scan.append(row['href'].split('?')[0].split('/')[-1])
                            log('#%02d (%s)\t| %s' % (i + 1, likes, title))

        log('Page %d took %.2fs.' % (page, __get_elapsed_sec(start_time)))
        page += 1
    return tuple(to_scan)


try:
    for domain_placeholder in Path.DOMAIN_PLACEHOLDERS:
        log('Looking up %s.' % domain_placeholder)
        scan_list = get_entries_to_scan(domain_placeholder + PAGE_INDEX, 1, 1)
        for article_no in scan_list:
            pause = random.uniform(4, 20)
            print('Pause for %.1f.' % pause)
            time.sleep(pause)

            article_url = domain_placeholder + str(article_no)
            scan_article(article_url)
except Exception as e:
    log('[Error] %s\n[Traceback]\n%s' % (e, traceback.format_exc(),))
