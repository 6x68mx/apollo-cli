import requests
from bs4 import BeautifulSoup
import re
import time
import json

SITE_URL = "https://apollo.rip"

USER_AGENT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_7_3)"
              "AppleWebKit/535.11 (KHTML, like Gecko) Chrome/17.0.963.79"
              "Safari/535.11")

FORMATS = {
    "flac": {
        "format": "FLAC",
        "bitrate": "Lossless"
    },
    "320": {
        "format": "MP3",
        "bitrate": "320"
    },
    "v0": {
        "format": "MP3",
        "bitrate": "V0 (VBR)"
    },
    "v2": {
        "format": "MP3",
        "bitrate": "V2 (VBR)"
    }
}

class ApolloApi:
    def __init__(self, username=None, password=None):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})
        self.authenticated = False
        self.rate_limit = 2
        self.last_request = time.time()

    def login(self, username, password):
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
                return True

        return False

    def _api_request(self, action, **kwargs):
        while time.time() - self.last_request < self.rate_limit:
            time.sleep(0.1)
        self.last_request = time.time()

        params = {"action": action}
        params.update(kwargs)
        r = self.session.get(SITE_URL + "/ajax.php", params=params)
        if r.status_code == 200:
            return r.json()
        else:
            return None

    def get_better_snatched(self):
        if not self.authenticated:
            return

        re_artist = re.compile(r"artist\.php\?id=(?P<artistid>[0-9]+)")
        re_torrent = re.compile(r"torrents\.php\?id=(?P<groupid>[0-9]+)&torrentid=(?P<torrentid>[0-9]+)")

        r = self.session.get(SITE_URL + "/better.php?method=snatch")

        if r.status_code != 200:
            return

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
                needed.append("v2")
            v0 = v2.find_next_sibling("td")
            if v0.string == "NO":
                needed.append("v0")
            f320 = v0.find_next_sibling("td")
            if f320.string == "NO":
                needed.append("320")
            t["formats_needed"] = needed

            torrents.append(t)

        return torrents

    def get_torrent(self, tid):
        return self._api_request("torrent", id=tid)

    def get_group(self, gid):
        r = self._api_request("torrentgroup", id=gid)
        if r is not None and r.get("status", "") == "success":
            return r["response"]
        else:
            return None

    def get_index(self):
        r = self._api_request("index")
        if r is not None and r.get("status", "") == "success":
            return r["response"]
        else:
            return None
    
    def add_format(self, torrent, format, tfile, description=""):
        if format not in FORMATS:
            return False # TODO indicate "not a valid format" error

        gid = torrent["group"]["id"]
        torrent = torrent["torrent"]

        data = {
            "submit": "true",
            "auth": self.authkey,
            "groupid": str(gid),
            "type": 0,
            "format": FORMATS[format]["format"],
            "bitrate": FORMATS[format]["bitrate"],
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

        r = self.session.post(SITE_URL + "/upload.php",
                              params={"groupid": gid},
                              data=data,
                              files=files,
                              allow_redirects=False)

        if r.status_code == 302:
            return True
        else:
            return False

class TorrentCache:
    def __init__(self, api, path=None):
        self.api = api
        self.clear()
        if path:
            self.load(path)
        
    def clear(self):
        self.torrents = {}

    def load(self, path):
        try:
            with open(path, "r") as f:
                self.torrents.update(json.load(f))
        except FileNotFoundError:
            pass

    def save(self, path):
        with open(path, "w") as f:
            json.dump(self.torrents, f)

    def get(self, tid, caching=True):
        if tid in self.torrents:
            return self.torrents[tid]
        else:
            t = self.api.get_torrent(tid)
            if t and "status" in t and t["status"] == "success":
                self.torrents.update({tid: t})
                return t
            else:
                return None
