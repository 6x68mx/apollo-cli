from apolloapi import ApolloApi, TorrentCache
from transcode import transcode, TranscodeError
import formats
import util

import argparse
import configparser
from pathlib import Path
import tempfile
import shutil
import re
import subprocess
import errno
import os

CONFIG_PATH = "apollobetter.conf"
ANNOUNCE_URL = "https://mars.apollo.rip/{}/announce"

class ApolloBetter:
    def __init__(self, username, password, search_dirs, output_dir, torrent_dir, unique_groups, cache_path=None):
        self.tmp = tempfile.TemporaryDirectory()
        self.nuploaded = 0
        self.search_dirs = search_dirs
        self.output_dir = output_dir
        self.torrent_dir = torrent_dir
        self.unique_groups = unique_groups
        self.api = ApolloApi(cache_path)

        print("Logging in...")
        if not self.api.login(username, password):
            print("Error: Can't login to apollo.rip")

    def run(self, tids=None, limit=None, allowed_formats=formats.FORMATS):
        """
        Fetch transcode candidates, transcode and upload them.

        :param tids: Don't fetch candidates from apollo but try to transcode
                     this `list` of torrent IDs. NOT IMPLEMENTED! Currently
                     this argument is ignored.
        :param limit: Maximumg number of torrents to upload.
        :param allowed_formats: Transcode only to those formats. Other needed
                                formats are ignored.

        :returns: The number of torrents that where actually uploaded.
        """
        print("Fetching potential upload candidates from apollo...")
        candidates = self.api.get_better_snatched()

        candidates = [c for c in candidates if any(f in c["formats_needed"] for f in allowed_formats)]

        if not candidates:
            print("Their are no candidates for conversion. Nothing to do, exiting...")
        else:
            print("Found {} potential candidates.".format(len(candidates)))

        print()

        try:
            nuploaded = 0
            for c in candidates:
                if limit is not None and nuploaded >= limit:
                    break
                nuploaded += self.process_release(
                        c["torrentid"],
                        allowed_formats.intersection(c["formats_needed"]),
                        limit - nuploaded if limit is not None else None)
        finally:
            self.api.cache.save()

        return nuploaded

    def process_release(self, tid, oformats, limit=None):
        """
        Transcode and upload multiple formats for a single release group.

        :param tid: ID of the source flac torrent.
        :param oformats: Output formats wich will be generated and uploaded.
        :param limit: Maximum number of torrents to upload.

        :returns: The number of torrents that where actually uploaded.
        """
        torrent = self.api.get_torrent(tid)
        if torrent is None:
            print("\tError: Requesting torrent info for {} failed.".format(tid))
            return 0

        print("Processing {} - {} (ID: {}), Needed: {}".format(
            util.get_artist_name(torrent),
            torrent["group"]["name"],
            tid,
            ", ".join(f.NAME for f in oformats)))

        path = util.find_dir(torrent["torrent"]["filePath"], self.search_dirs)
        if path is None:
            return 0
        print("\tFound {}.".format(path))

        if (torrent["torrent"]["hasLog"]
                and (torrent["torrent"]["logScore"] != 100
                        or torrent["torrent"]["logChecksum"] != 1)):
            print("\tTorrent has a log file but its score is below 100 or it has a invalid checksum. Skipping...")
            return 0

        if self.unique_groups:
            group = self.api.get_group(torrent["group"]["id"])
            if any(t["username"] == self.api.username for t in group["torrents"]):
                print("\tYou already own a torrent in this group, skipping... (--unique-groups)")
                return 0

        # check integrity i.e. if file list in from torrent matches the actuall files on disk
        if not util.check_dir(path, util.parse_file_list(torrent["torrent"]["fileList"])):
            print("\tDirectory doesn't match the torrents file list. Skipping...")
            return 0

        nuploaded = 0
        for oformat in oformats:
            if limit is not None and nuploaded >= limit:
                break

            if self.process_format(torrent, path, oformat):
                nuploaded += 1

        return nuploaded

    def process_format(self, torrent, path, oformat):
        """
        Transcode and upload a single format.

        :param torrent: A `dict` as returned by `api.get_torrent`.
        :param path: A `Path` to the directory containing the source flac files.
        :param oformat: The output format.

        :returns: `True` on success, `False` otherwise.
        """
        print("\tProcessing Format {}:".format(oformat.NAME))

        transcode_dir = util.generate_transcode_name(torrent, oformat)
        dst_path = self.output_dir / transcode_dir
        tfile = Path(self.tmp.name) / (transcode_dir + ".torrent")

        tfile_new = self.torrent_dir / tfile.name
        if tfile_new.exists():
            print("\t\tError, {} allready exists.".format(tfile_new))

        print("\t\tTranscoding...")
        try:
            transcode(path, dst_path, oformat)
        except TranscodeError as e:
            print("\t\tError: ", e)
            return False # TODO we probably want to throw an exception here and abort alltogether

        print("\t\tCreating torrent file...")
        util.create_torrent_file(tfile, dst_path, ANNOUNCE_URL, self.api.passkey, "APL")

        print("\t\tUploading torrent...")
        description = util.generate_description(
                torrent["torrent"]["id"],
                sorted(path.glob("**/*" + formats.FormatFlac.SUFFIX))[0],
                oformat)
        r = self.api.add_format(torrent, oformat, tfile, description)
        if not r:
            print("Error on upload. Aborting everything!")
            shutil.rmtree(dst_path)
            os.remove(tfile)
            return False
            # TODO exit

        print("\t\tMoving torrent file...")
        shutil.copyfile(tfile, tfile_new)

        print("\t\tDone.")
        return True

def main():
    config = configparser.ConfigParser()
    config.read(CONFIG_PATH)

    parser = argparse.ArgumentParser()
    parser.add_argument("--search-dir", help="Where to search for potential uploads", type=Path, required=True, action="append")
    parser.add_argument("-o", "--output-dir", help="Destination for converted data", type=Path, required=True)
    parser.add_argument("--torrent-dir", help="Where to put the new *.torrent files", type=Path, required=True)
    parser.add_argument("-l", "--limit", type=int, help="Maximum number of torrents to upload")
    parser.add_argument("-u", "--unique-groups", action="store_true", help="Upload only into groups you do not yet have a single torrent in.")
    parser.add_argument("-v2", "--format-v2", action="store_true")
    parser.add_argument("-v0", "--format-v0", action="store_true")
    parser.add_argument("-320", "--format-320", action="store_true")
    args = parser.parse_args()

    allowed_formats = set()
    if args.format_v2:
        allowed_formats.add(formats.FormatV2)
    if args.format_v0:
        allowed_formats.add(formats.FormatV0)
    if args.format_320:
        allowed_formats.add(formats.Format320)
    if not allowed_formats:
        allowed_formats = formats.FORMATS

    better = ApolloBetter(
        config["apollo"]["username"],
        config["apollo"]["password"],
        args.search_dir,
        args.output_dir,
        args.torrent_dir,
        args.unique_groups,
        config["DEFAULT"]["torrent_cache"])

    nuploaded = better.run(allowed_formats=allowed_formats, limit=args.limit)

    print("\nFinished")
    print("Uploaded {} torrents.".format(nuploaded))

if __name__ == "__main__":
    main()
