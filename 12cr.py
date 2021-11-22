import downloader
import common
import random
import traceback
from datetime import datetime
import requests
from bs4 import BeautifulSoup


class Constants:
    EXTENSION_CANDIDATES = ('jpg', 'jpeg', 'png', 'gif', 'jfif', 'webp', 'mp4', 'webm', 'mov')
    ROOT_DOMAIN = common.build_tuple('12_DOMAINS.pv')
    IGNORED_URLS = common.build_tuple('12_IGNORED_URLS.pv')

    TOO_YOUNG_DAY = 0
    TOO_OLD_DAY = 2
    SCANNING_SPAN = 5
    STARTING_PAGE = 1


def log(message: str, has_tst: bool = True):
    path = common.read_from_file('12_LOG_PATH.pv')
    common.log(message, path, has_tst)


def __get_date_difference(tst_str: str) -> int:
    if tst_str:
        tst_str = tst_str.strip()
        now = datetime.now()
        try:
            if len(tst_str.split('.')) < 3:  # 11.07 instead of 2012.11.07
                asserted_tst = str(now.year) + '.' + tst_str
                date = datetime.strptime(asserted_tst, '%Y.%m.%d')  # 11.07
                if (now - date).days < 0:  # 2013.01.02 - 2013.12.31
                    correct_tst = str(now.year - 1) + '.' + tst_str  # It was 2012.12.31
                    date = datetime.strptime(correct_tst, '%Y.%m.%d')
            else:
                date = datetime.strptime(tst_str, '%Y.%m.%d')  # 11.07
            return (now - date).days

        except Exception as e:
            print('(%s) The timestamp did not match the format: %s.' % (e, tst_str))


def __get_local_name(doc_title: str, url: str):
    doc_id = url.split('id=')[-1].split('&')[0]  # The document id(e.g. '373719')
    formatted_title = doc_title.strip()
    for prohibited_char in common.Constants.PROHIBITED_CHARS:
        formatted_title = formatted_title.replace(prohibited_char, '_')
    return formatted_title + '-' + doc_id


# Peculiar urls present. Do not use downloader.iterate_source_tag
def iterate_source_tags(source_tags, file_name, from_article_url):
    attribute = None
    src_attribute = 'src'
    link_attribute = 'href'
    content_type_attribute = 'content-type'
    extension = 'tmp'

    for i, tag in enumerate(source_tags):
        if tag.has_attr(src_attribute):  # e.g. <img src = "...">
            attribute = src_attribute
        elif tag.has_attr(link_attribute):  # e.g. <a href = "...">
            attribute = link_attribute
        if attribute:
            raw_source = tag[attribute].split('?type')[0]
            source_url = Constants.ROOT_DOMAIN[0] + raw_source\
                if raw_source.startswith('/data') else raw_source

            # Check the ignored file name list
            for ignored_pattern in common.Constants.IGNORED_FILE_NAME_PATTERNS:
                if ignored_pattern in source_url:
                    log('Ignored %s.\n(Article: %s)' % (source_url, from_article_url))
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

                if filetype in Constants.EXTENSION_CANDIDATES:
                    extension = filetype
                else:
                    log('Error: unexpected %s/%s\n(Article: %s)\n(Source: %s)' %
                        (category, filetype, from_article_url, source_url))
                    # Try extract the extension from the url. (e.g. https://www.domain.com/video.mp4)
                    chunk = source_url.split('.')[-1]
                    if chunk in Constants.EXTENSION_CANDIDATES:
                        extension = chunk

            if extension == 'tmp':  # After all, the extension has not been updated.
                log('Error: extension cannot be specified.\n(Article: %s)\n(Source: %s)' %
                    (from_article_url, source_url))
            print('%s-*.%s on %s' % (file_name, extension, source_url))
            # Download the file.
            downloader.download(source_url, '%s-%03d.%s' % (file_name, i, extension))
        else:
            log('Error: Tag present, but no source found.\n(Tag: %s)\n(%s: Article)' % (tag, from_article_url))


def scan_article(url: str):
    soup = BeautifulSoup(requests.get(url).text, common.Constants.HTML_PARSER)
    article_title = soup.select_one('div.view-wrap h1')['content']
    local_name = __get_local_name(article_title, url)
    domain_tag = '12'
    body_css_selector = 'div.view-content '

    img_source_tags = soup.select(body_css_selector + 'img')
    if img_source_tags:  # Images present
        try:
            iterate_source_tags(img_source_tags, '%s-%s-%s' % (domain_tag, local_name, 'i'), url)
        except Exception as img_source_exception:
            log('Error: %s\n%s\n[Traceback]\n%s' % (img_source_exception, url, traceback.format_exc()))

    video_source_tags = soup.select(body_css_selector + 'video')
    if video_source_tags:  # Videos present
        try:
            iterate_source_tags(video_source_tags, '%s-%s-%s' % (domain_tag, local_name, 'v'), url)
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
            iterate_source_tags(external_link_tags, '%s-%s-%s' % (domain_tag, local_name, 'a'), url)
        except Exception as video_source_exception:
            log('Error: %s\n%s\n[Traceback]\n%s' % (video_source_exception, url, traceback.format_exc()))


def get_entries_to_scan(placeholder: str, scanning_span: int, page: int = 1) -> ():
    max_page = page + scanning_span - 1  # To prevent infinite looping
    to_scan = []

    while page <= max_page:  # Page-wise
        start_time = datetime.now()  # A timer for monitoring performance
        url = placeholder + str(page)
        soup = BeautifulSoup(requests.get(url).text, common.Constants.HTML_PARSER)
        rows = soup.select('div.list-board > ul.list-body > li.list-item')

        for i, row in enumerate(rows):  # Inspect the rows
            try:
                tst_str = row.select_one('div.wr-date').string
                day_diff = __get_date_difference(tst_str)
                if day_diff:
                    if day_diff <= Constants.TOO_YOUNG_DAY:  # Still, not mature: uploaded on the yesterday.
                        log('#%02d | Skipping the too young.', False)
                        continue  # Move to the next row
                    elif day_diff >= Constants.TOO_OLD_DAY:  # Too old.
                        # No need to scan older rows.
                        log('#%02d | Skipping the too old.' % (i + 1), False)
                        log('Page %d took %.1f". Stop searching for older rows.\n'
                            % (page, common.get_elapsed_sec(start_time)), False)
                        return tuple(to_scan)
                    else:  # Mature
                        try:
                            title = row.select_one('div.wr-subject > a > span.wr-num').next_sibling.strip()
                        except Exception as title_exception:
                            title = '%05d' % random.randint(1, 99999)
                            log('Error: cannot retrieve article title of row %d.(%s)\n(%s)' %
                                (i + 1, title_exception, url))
                        for pattern in common.Constants.IGNORED_TITLE_PATTERNS:
                            if pattern in title:
                                log('#%02d | (ignored) %s' % (i + 1, title), False)
                                break
                        else:
                            article_url = row.select_one('div.wr-subject > a')['href'].split('id=')[-1].split('&')[0]
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
            page_index = '/bbs/board.php?bo_table=gal01&page='
            log('Looking up %s' % domain + page_index)
            scan_list = get_entries_to_scan(domain + page_index, scanning_span, starting_page)
            for i, article_no in enumerate(scan_list):  # [32113, 39213, 123412, ...]
                common.pause_briefly()
                article_url = domain + '/bbs/board.php?bo_table=gal01&wr_id=' + str(article_no)
                scan_start_time = datetime.now()
                scan_article(article_url)
                log('Scanned %d/%d articles(%.1f")' %
                    (i + 1, len(scan_list), common.get_elapsed_sec(scan_start_time)), False)
            log('Finished scanning %s in %d min.' % (domain, int(common.get_elapsed_sec(domain_start_time) / 60)))
    except Exception as normal_domain_exception:
        log('[Error] %s\n[Traceback]\n%s' % (normal_domain_exception, traceback.format_exc(),))


if __name__ == "__main__":
    process_domain(Constants.ROOT_DOMAIN, scanning_span=Constants.SCANNING_SPAN, starting_page=Constants.STARTING_PAGE)
