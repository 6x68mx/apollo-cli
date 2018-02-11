from apolloapi import ApolloApi, TorrentCache
import argparse
import configparser
from pathlib import Path
import tempfile
import shutil
import re
import subprocess
import errno
import util

CONFIG_PATH = "apollobetter.conf"
ANNOUNCE_URL = "https://mars.apollo.rip/{}/announce"

DESCRIPTION = ("Transcode of [url=https://apollo.rip/torrents.php?torrentid={tid}]https://apollo.rip/torrents.php?torrentid={tid}[/url]\n"
               "\n"
               "This transcoding was done by an autonomous system.")

def main():
    config = configparser.ConfigParser()
    config.read(CONFIG_PATH)

    parser = argparse.ArgumentParser()
    parser.add_argument("--search-dir", help="Where to search for potential uploads", type=Path, required=True, action="append")
    parser.add_argument("-o", "--output-dir", help="Destination for converted data", type=Path, required=True)
    parser.add_argument("--torrent-dir", help="Where to put the new *.torrent files", type=Path, required=True)
    parser.add_argument("-l", "--limit", type=int, help="Maximum number of torrents to upload", default=0)
    parser.add_argument("-u", "--unique-groups", action="store_true", help="Upload only into groups you do not yet have a single torrent in.")
    parser.add_argument("-v2", "--format-v2", action="store_true")
    parser.add_argument("-v0", "--format-v0", action="store_true")
    parser.add_argument("-320", "--format-320", action="store_true")
    args = parser.parse_args()

    formats = []
    if args.format_v2:
        formats.append("v2")
    if args.format_v0:
        formats.append("v0")
    if args.format_320:
        formats.append("320")
    if formats:
        formats = set(formats)
    else:
        formats = {"v2", "v0", "320"}

    print("Logging in...")
    username = config["apollo"]["username"]
    password = config["apollo"]["password"]
    api = ApolloApi()
    if not api.login(username, password):
        print("Error: Can't login to apollo.rip")
        return

    cache_path = config["DEFAULT"]["torrent_cache"]
    tc = TorrentCache(api, cache_path)

    print("Fetching potential upload candidates from apollo...")
    candidates = api.get_better_snatched()

    candidates = [c for c in candidates if any(f in c["formats_needed"] for f in formats)]

    if not candidates:
        print("Their are no candidates for conversion. Nothing to do, exiting...")
    else:
        print("Found {} potential candidates.".format(len(candidates)))

    print()

    tmp = tempfile.TemporaryDirectory()

    nuploaded = 0
    limit = args.limit
    try:
        for c in candidates:
            if limit > 0 and nuploaded >= limit:
                break

            print("Processing {} - {} (ID: {}), Needed: {}".format(c["artist"], c["name"], c["torrentid"], ", ".join(c["formats_needed"])))
            
            torrent_response = tc.get(c["torrentid"])
            torrent = torrent_response["response"]["torrent"]

            needed = formats.intersection(c["formats_needed"])
            for output_format in needed:

                # find allready encoded data directory
                """
                transcode_dir = util.get_transcode_dir(torrent["filePath"], output_format)
                path = util.find_dir(transcode_dir, args.search_dir)
                if path is None:
                    continue
                print("\tFound {}.".format(path))
                """

                path = util.find_dir(torrent["filePath"], args.search_dir)
                if path is None:
                    continue
                print("\tFound {}.".format(path))

                if args.unique_groups:
                    group = api.get_group(torrent_response["response"]["group"]["id"])
                    if any(t["username"] == api.username for t in group["torrents"]):
                        print("\tYou already own a torrent in this group, skipping... (--unique-groups)")
                        break # skip all formats of this release
                
                # TODO check integrity i.e. if file list in from torrent matches the actuall files on disk
                if not util.check_dir(path, util.parse_file_list(torrent["fileList"])):
                    print("\tDirectory doesn't match the torrents file list. Skipping...")
                    continue
                print("\tdir check OK")

                print("\t\tCreating torrent file...")
                tfile = Path(tmp.name) / (transcode_dir + ".torrent")
                util.create_torrent_file(tfile, path, ANNOUNCE_URL, api.passkey, "APL")

                print("\t\tUploading torrent...")
                r = api.add_format(torrent_response["response"], output_format, tfile, DESCRIPTION.format(tid=torrent["id"]))
                if not r:
                    print("Error on upload. Aborting everything!")
                    # TODO exit

                print("\t\tMoving files...")
                tfile_new = args.torrent_dir / tfile.name
                path_new = args.output_dir / path.name
                if tfile_new.exists() or path_new.exists():
                    if tfile_new.exists():
                        print("\t\tError, {} allready exists.".format(tfile_new))
                    if path_new.exists():
                        print("\t\tError, {} allready exists.".format(path_new))
                    # TODO exit
                else:
                    path.rename(path_new)
                    shutil.copyfile(tfile, tfile_new)

                print("\t\tDone.")

                nuploaded += 1
    except:
        tc.save(cache_path)
        raise

    print("\nFinished")
    print("Uploaded {} torrents.".format(nuploaded))

    tc.save(cache_path)

if __name__ == "__main__":
    main()
