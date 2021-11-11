import os
from PIL import Image
import common
import requests


EXTENSION_CANDIDATES = ('jpg', 'jpeg', 'png', 'gif', 'jfif', 'webp', 'mp4', 'webm', 'mov')
FILE_NAME_IGNORED_PATTERNS = ('028c715135212dd447915ed16949f7532588d3d95d113cada85703d1ef26',
                              'fc13c25d018ccbde127b02044b6e4de17f28725faf1b891422ba6878e9f',
                              'blocked.png')


def log(message: str, has_tst: bool = True):
    path = common.read_from_file('DL_LOG_PATH.pv')
    common.log(message, path, has_tst)


def convert_webp_to_png(stored_dir, filename):
    ext = 'png'
    stored_path = os.path.join(stored_dir, filename)
    img = Image.open(stored_path).convert("RGB")
    new_filename = common.split_on_last_pattern(filename, '.')[0] + '.' + ext
    new_path = os.path.join(stored_dir, new_filename)
    img.save(new_path, ext)
    os.remove(stored_path)


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
            for ignored_pattern in FILE_NAME_IGNORED_PATTERNS:
                if ignored_pattern in source_url:
                    log('Ignored %s.\n(Article: %s' % (source_url, from_article_url))
                    continue  # Skip this source tag.

            # Retrieve the extension.
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
            else:
                # Try extract the extension from the url. (e.g. https://www.domain.com/video.mp4)
                chunk = source_url.split('.')[-1]
                if chunk in EXTENSION_CANDIDATES:
                    extension = chunk

            if extension == 'tmp':  # After all, the extension has not been updated.
                log('Error: extension cannot be specified.\n(Article: %s)\n(Source: %s)' %
                    (from_article_url, source_url))
            print('%s-*.%s on %s' % (file_name, extension, source_url))
            # Download the file.
            download(source_url, '%s-%03d.%s' % (file_name, i, extension))


def download(url: str, local_name: str):
    # Set the absolute path to store the downloaded file.
    if not os.path.exists(common.DOWNLOAD_PATH):
        os.makedirs(common.DOWNLOAD_PATH)  # create folder if it does not exist

    # Set the download target.
    r = requests.get(url, stream=True)

    file_path = os.path.join(common.DOWNLOAD_PATH, local_name)
    if r.ok:
        with open(file_path, 'wb') as f:
            for chunk in r.iter_content(chunk_size=1024 * 8):
                if chunk:
                    f.write(chunk)
                    f.flush()
                    os.fsync(f.fileno())
    else:  # HTTP status code 4XX/5XX
        log("Error: Download failed.(status code {}\n{})".format(r.status_code, r.text), True)

    if local_name.endswith('webp'):
        convert_webp_to_png(common.DOWNLOAD_PATH, local_name)
