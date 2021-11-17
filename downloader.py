import os
import time
from glob import glob
import common
import requests


EXTENSION_CANDIDATES = ('jpg', 'jpeg', 'png', 'gif', 'jfif', 'webp', 'mp4', 'webm', 'mov')


def log(message: str, has_tst: bool = True):
    path = common.read_from_file('DL_LOG_PATH.pv')
    common.log(message, path, has_tst)


def iterate_source_tags(source_tags, file_name, from_article_url):
    src_attribute = 'src'
    link_attribute = 'href'
    source_tag = 'source'
    content_type_attribute = 'content-type'
    extension = 'tmp'

    for i, tag in enumerate(source_tags):
        raw_sources = []  # All the sources included in the tag
        if tag.has_attr(src_attribute):  # e.g. <img src = "...">
            raw_sources.append(tag[src_attribute].split('?type')[0])
        elif tag.has_attr(link_attribute):  # e.g. <a href = "...">
            raw_sources.append(tag[link_attribute].split('?type')[0])
        elif tag.select(source_tag):  # e.g. <video ...><source src = "...">...</source></video>
            for source in tag.select(source_tag):
                if source.has_attr(src_attribute):
                    raw_sources.append(source[src_attribute].split('?type')[0])

        # Now process the collected sources.
        if len(raw_sources) == 0:
            log('Error: Tag present, but no source found.\n(Tag: %s)\n(%s: Article)' % (tag, from_article_url))
        for raw_source in raw_sources:
            source_url = 'https:' + raw_source if raw_source.startswith('//') else raw_source
            # Check the ignored file name list
            for ignored_pattern in common.Constants.IGNORED_FILE_NAME_PATTERNS:
                if ignored_pattern in source_url:
                    log('Ignoring based on file name pattern: %s.\n(Article: %s' % (source_url, from_article_url))
                    break  # Skip this source tag.
            else:  # Retrieve the extension.
                try:
                    header = requests.head(source_url).headers
                    if content_type_attribute in header:
                        header = header[content_type_attribute]
                        try:
                            category, filetype = header.split('/')
                        except ValueError:
                            filetype = header
                            category = None
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
                except Exception as header_exception:
                    log('Error: cannot process the header.(%s)\n(Tag: %s)\n(%s: Article)' %
                        (header_exception, tag, from_article_url))

                if extension == 'tmp':  # After all, the extension has not been updated.
                    # Try extract the extension from the url. (e.g. https://www.domain.com/video.mp4)
                    chunk = source_url.split('.')[-1]
                    if chunk in EXTENSION_CANDIDATES:
                        extension = chunk
                    else:
                        log('Error: extension cannot be specified.\n(Article: %s)\n(Source: %s)' %
                            (from_article_url, source_url))
                print('%s-*.%s on %s' % (file_name, extension, source_url))
                # Download the file.
                download(source_url, '%s-%03d.%s' % (file_name, i, extension))


def wait_finish_downloading(temp_dir_path: str, log_path: str, loading_sec: float, trial: int = 0,
                            is_logged: bool = True):
    seconds = 0
    check_interval = 1
    timeout_multiplier = (trial + 1) ** 4 + 1  # 2, 17, 82, ...
    max_timeout = 480

    # The timeout: 10 ~ 480
    timeout = max(10 * (trial + 1), int(loading_sec * timeout_multiplier))
    if timeout > max_timeout:
        timeout = max_timeout
    if is_logged:
        common.log('Trial: %d / Timeout: %d(<-%.1f)' % (trial + 1, timeout, loading_sec), log_path, False)

    last_size = 0
    while seconds <= timeout:
        current_size = sum(os.path.getsize(f) for f in glob(temp_dir_path + '*') if os.path.isfile(f))
        if current_size == last_size and last_size > 0:
            return True
        print('Waiting to finish downloading. (%d/%d)' % (seconds, timeout))
        # Report
        if current_size != last_size:
            print('%.1f -> %.1f MB' % (last_size / 1000000, current_size / 1000000))
        # Wait
        time.sleep(check_interval)
        seconds += check_interval
        last_size = current_size
    print('Download timeout reached.')
    return False  # Timeout


def download(url: str, local_name: str):
    # Set the absolute path to store the downloaded file.
    common.check_dir_exists(common.Constants.DOWNLOAD_PATH)

    # Set the download target.
    r = requests.get(url, stream=True)

    file_path = os.path.join(common.Constants.DOWNLOAD_PATH, local_name)
    if r.ok:
        with open(file_path, 'wb') as f:
            for chunk in r.iter_content(chunk_size=1024 * 8):
                if chunk:
                    f.write(chunk)
                    f.flush()
                    os.fsync(f.fileno())
    else:  # HTTP status code 4XX/5XX
        log("Error: Download failed.(%s)" % url, False)

    if local_name.endswith('webp'):
        common.convert_webp_to_png(common.Constants.DOWNLOAD_PATH, local_name)
