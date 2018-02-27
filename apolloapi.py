import formats

import requests
from bs4 import BeautifulSoup
import re
import time
import json
import html

SITE_URL = "https://apollo.rip"

# No idea if we really need to spoof our user agent for apollo.rip
# but xanaxbetter does it so at least for now we use the same useragent
USER_AGENT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_7_3)"
              "AppleWebKit/535.11 (KHTML, like Gecko) Chrome/17.0.963.79"
              "Safari/535.11")

class ApiError(Exception):
    pass

class ApolloApi:
    def __init__(self, cache_path=None):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})
        self.authenticated = False
        self.rate_limit = 2 # minimum time between two requests in seconds
        self.last_request = time.time()
        self.cache = TorrentCache(self, cache_path)

    def login(self, username, password):
        """
        Authenticate with the apollo server.

        :raises ApiError: If the login failed.
        """
        r = self.session.post(SITE_URL + "/login.php",
                              data={"username": username,
                                    "password": password,
                                    "login": "Log in"},
                              allow_redirects=False)
        if r.status_code == 302 and r.headers["location"] != "login.php":
            r = self.get_index()
            if r is not None:
                self.username = r["username"]
                self.uid = r["id"]
                self.authkey = r["authkey"]
                self.passkey = r["passkey"]
                self.authenticated = True
                return

        raise ApiError("Login failed.")

    def _api_request(self, action, **kwargs):
        while time.time() - self.last_request < self.rate_limit:
            time.sleep(0.1)
        self.last_request = time.time()

        params = {"action": action}
        params.update(kwargs)
        r = self.session.get(SITE_URL + "/ajax.php", params=params)
        if r.status_code == 200:
            r = r.json()
            if r.get("status", "") == "success":
                return unescape(r["response"])
            elif r.get("status", "") == "failure" and "error" in r:
                raise ApiError("API request failed. Error: '{}'".format(r["error"]))
            else:
                raise ApiError("API request failed. ({})".format(str(r)))
        else:
            raise ApiError("API request failed with status code {}".format(r.status_code))
            

    def get_better_snatched(self):
        if not self.authenticated:
            return

        re_artist = re.compile(r"artist\.php\?id=(?P<artistid>[0-9]+)")
        re_torrent = re.compile(r"torrents\.php\?id=(?P<groupid>[0-9]+)&torrentid=(?P<torrentid>[0-9]+)")

        r = self.session.get(SITE_URL + "/better.php?method=snatch")

        if r.status_code != 200:
            raise ApiError("Couldn't fetch better snatched. (Statuscode: {})".format(r.status_code))

        soup = BeautifulSoup(r.content, "lxml")

        torrents = []
        for entry in soup.find_all("tr", class_="torrent_row"):
            t = {}

            artist = entry.find("a", href=re_artist)
            if artist:
                t["artist"] = artist.string
                t["artistid"] = re_artist.search(artist.get("href"))["artistid"]
            else:
                t["artist"] = "Various Artists"

            torrent = entry.find("a", href=re_torrent)
            t["name"] = torrent.string
            r = re_torrent.search(torrent.get("href"))
            t["groupid"] = r["groupid"]
            t["torrentid"] = r["torrentid"]

            needed = []
            v2 = entry.td.find_next_sibling("td")
            if v2.string == "NO":
                needed.append(formats.FormatV2)
            v0 = v2.find_next_sibling("td")
            if v0.string == "NO":
                needed.append(formats.FormatV0)
            f320 = v0.find_next_sibling("td")
            if f320.string == "NO":
                needed.append(formats.Format320)
            t["formats_needed"] = needed

            torrents.append(t)

        return torrents

    def get_torrent(self, tid, caching=True):
        if caching:
            return self.cache.get(tid)
        else:
            return self._api_request("torrent", id=tid)

    def get_group(self, gid):
        return self._api_request("torrentgroup", id=gid)

    def get_index(self):
        return self._api_request("index")
    
    def add_format(self, torrent, format, tfile, description=""):
        if format not in formats.FORMATS:
            return False # TODO indicate "not a valid format" error

        gid = torrent["group"]["id"]
        torrent = torrent["torrent"]

        data = {
            "submit": "true",
            "auth": self.authkey,
            "groupid": str(gid),
            "type": 0,
            "format": format.FORMAT,
            "bitrate": format.BITRATE,
            "media": torrent["media"],
            "release_desc": description
        }

        if torrent["remastered"]:
            data["remaster"] = "on"
            data["remaster_year"] = str(torrent["remasterYear"])
            data["remaster_title"] = torrent["remasterTitle"]
            data["remaster_record_label"] = torrent["remasterRecordLabel"]
            data["remaster_catalogue_number"] = torrent["remasterCatalogueNumber"]
            

        files = {"file_input": (tfile.name, tfile.open("rb"), "application/x-bittorrent")}

        # urllib3 (and therefore requests) incorrectly encodes utf-8 file names
        # The commented-out code is the normal code that we can use once
        # urllib3 fixes this bug.
        """
        r = self.session.post(SITE_URL + "/upload.php",
                              params={"groupid": gid},
                              data=data,
                              files=files,
                              allow_redirects=False)
        """
        # workaround from
        # http://linuxonly.nl/docs/68/167_Uploading_files_with_non_ASCII_filenames_using_Python_requests.html
        def rewrite_request(prepped):
            filename = tfile.name.encode("utf-8")
            prepped.body = re.sub(b"filename\*=.*",
                                  b'filename="' + filename + b'"',
                                  prepped.body)
            return prepped

        r = self.session.post(SITE_URL + "/upload.php",
                              params={"groupid": gid},
                              data=data,
                              files=files,
                              allow_redirects=False,
                              auth=rewrite_request)

        if r.status_code != 302:
            raise ApiError("Couldn't add format. (Status code: {})".format(r.status_code))

def unescape(obj):
    """
    Unescape all html entities in all strings of a json data structure.
    """
    if isinstance(obj, str):
        return html.unescape(obj)
    elif isinstance(obj, list):
        return [unescape(x) for x in obj]
    elif isinstance(obj, dict):
        return {unescape(k): unescape(v) for k, v in obj.items()}
    else:
        return obj

class TorrentCache:
    """
    Caches access to the torrent API endpoint.
    """
    def __init__(self, api, path=None):
        self.api = api
        self.clear()
        if path:
            self.load(path)
            self.path = path
        
    def clear(self):
        self.torrents = {}

    def load(self, path):
        try:
            with open(path, "r") as f:
                self.torrents.update(json.load(f))
        except FileNotFoundError:
            pass

    def save(self, path=None):
        if path is None and self.path is not None:
            path = self.path
        with open(path, "w") as f:
            json.dump(self.torrents, f)

    def get(self, tid):
        if tid in self.torrents:
            return self.torrents[tid]
        else:
            t = self.api.get_torrent(tid, caching=False)
            if t:
                self.torrents.update({tid: t})
            return t
