import random
import time

from PIL import Image
from datetime import datetime
import os
from bs4 import BeautifulSoup
import requests


def log(message: str, path: str, has_tst: bool = True):
    dir_path = split_on_last_pattern(path, '/')[0]
    check_dir_exists(dir_path)

    with open(path, 'a') as f:
        if has_tst:
            message += '\t(%s)' % get_str_time()
        f.write(message + '\n')
    print(message)


def pause_briefly(min_pause=2, max_pause=6):
    pause = random.uniform(min_pause, max_pause)
    print('Pause for %.1f".' % pause)
    time.sleep(pause)


def get_str_time() -> str:
    return str(datetime.now()).split('.')[0]


def check_dir_exists(dir_path: str):
    if not os.path.exists(dir_path):
        os.makedirs(dir_path)
        return False  # Didn't exist, but created one.
    else:
        return True  # Already exists.


def read_from_file(path: str):
    with open(path) as f:
        return f.read().strip('\n')


def get_date_difference(tst_str: str) -> int:
    try:
        date = datetime.strptime(tst_str, '%Y.%m.%d')  # 2021.11.07
        now = datetime.now()
        return (now - date).days
    except Exception as e:
        print('(%s) The timestamp did not match the format: %s.' % (e, tst_str))


def get_free_proxies():
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


def get_proxy_session(sampling_url: str, log_path: str = None):
    timeout = 3
    session = requests.session()
    try:
        code = session.get(sampling_url, timeout=timeout).status_code
        if code == 200:
            print('The url is accessible.')
            return session
        else:
            if log_path:
                log('Error: HTTP response %d.' % code, log_path)
    except requests.exceptions.ReadTimeout:
        free_proxy_list = get_free_proxies()
        for i, proxy in enumerate(free_proxy_list):
            try:
                session.proxies = {'http': 'http://' + proxy,
                                   'https://': 'https://' + proxy}
                if session.get(sampling_url, timeout=timeout).status_code == 200:
                    print('Proxy: %s worked.(trial %d) ' % (proxy, i + 1))
                    return session
            except Exception as e:
                print('%s failed.(%s)' % (proxy, e))
    return requests.session()  # Try again with a normal session.


def get_tor_session():
    req = requests.session()
    # Tor uses the 9050 port as the default socks port
    req.proxies = {'http': 'socks5://127.0.0.1:9050',
                   'https': 'socks5://127.0.0.1:9050'}
    return req


def get_ip(session: requests.Session) -> str:
    return session.get("http://httpbin.org/ip", timeout=1).text.split('"')[-2]


def build_tuple(path: str):
    content = read_from_file(path)
    return tuple(content.split('\n'))


def build_tuple_of_tuples(path: str):
    lines = build_tuple(path)
    info = []
    for line in lines:
        info.append(tuple(line.split(',')))
    return tuple(info)


def get_elapsed_sec(start_time) -> float:
    end_time = datetime.now()
    return (end_time - start_time).total_seconds()


def convert_webp_to_png(stored_dir, filename):
    ext = 'png'
    stored_path = os.path.join(stored_dir, filename)
    img = Image.open(stored_path).convert("RGB")
    new_filename = split_on_last_pattern(filename, '.')[0] + '.' + ext
    new_path = os.path.join(stored_dir, new_filename)
    img.save(new_path, ext)
    os.remove(stored_path)


# Split on the pattern, but always returning a list with length of 2.
def split_on_last_pattern(string: str, pattern: str) -> ():
    last_piece = string.split(pattern)[-1]  # domain.com/image.jpg -> jpg
    leading_chunks = string.split(pattern)[:-1]  # [domain, com/image]
    leading_piece = pattern.join(leading_chunks)  # domain.com/image
    return leading_piece, last_piece  # (domain.com/image, jpg)


class Constants:
    HTML_PARSER = 'html.parser'
    DOWNLOAD_PATH = read_from_file('DOWNLOAD_PATH.pv')
    DRIVER_PATH = read_from_file('DRIVER_PATH.pv')
    DUMP_PATH = read_from_file('DUMP_PATH.pv')
    IGNORED_TITLE_PATTERNS = build_tuple('IGNORED_TITLE_PATTERNS.pv')
    PROHIBITED_CHARS = (' ', '.', '/')
