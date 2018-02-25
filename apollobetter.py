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

CONFIG_PATH = "apollobetter.conf"
ANNOUNCE_URL = "https://mars.apollo.rip/{}/announce"

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

    target_formats = set()
    if args.format_v2:
        target_formats.add(formats.FormatV2)
    if args.format_v0:
        target_formats.add(formats.FormatV0)
    if args.format_320:
        target_formats.add(formats.Format320)
    if not target_formats:
        target_formats = formats.FORMATS

    cache_path = config["DEFAULT"]["torrent_cache"]

    print("Logging in...")
    username = config["apollo"]["username"]
    password = config["apollo"]["password"]
    api = ApolloApi(cache_path)
    if not api.login(username, password):
        print("Error: Can't login to apollo.rip")
        return

    print("Fetching potential upload candidates from apollo...")
    candidates = api.get_better_snatched()

    candidates = [c for c in candidates if any(f in c["formats_needed"] for f in target_formats)]

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

            print("Processing {} - {} (ID: {}), Needed: {}".format(
                c["artist"],
                c["name"],
                c["torrentid"],
                ", ".join(f.NAME for f in c["formats_needed"])))
            
            torrent = api.get_torrent(c["torrentid"])
            if torrent is None:
                print("\tError: Requesting torrent info failed.")
                continue

            needed = target_formats.intersection(c["formats_needed"])
            if not needed:
                continue

            path = util.find_dir(torrent["torrent"]["filePath"], args.search_dir)
            if path is None:
                continue
            print("\tFound {}.".format(path))

            if args.unique_groups:
                group = api.get_group(torrent["group"]["id"])
                if any(t["username"] == api.username for t in group["torrents"]):
                    print("\tYou already own a torrent in this group, skipping... (--unique-groups)")
                    continue

            # check integrity i.e. if file list in from torrent matches the actuall files on disk
            if not util.check_dir(path, util.parse_file_list(torrent["torrent"]["fileList"])):
                print("\tDirectory doesn't match the torrents file list. Skipping...")
                continue

            for output_format in needed:
                if limit > 0 and nuploaded >= limit:
                    break

                print("\tProcessing Format {}:".format(output_format.NAME))

                transcode_dir = util.generate_transcode_name(torrent, output_format)
                dst_path = args.output_dir / transcode_dir

                print("\t\tTranscoding...")
                try:
                    transcode(path, dst_path, output_format)
                except TranscodeError as e:
                    print("Error: ", e)
                    continue

                print("\t\tCreating torrent file...")
                tfile = Path(tmp.name) / (transcode_dir + ".torrent")
                util.create_torrent_file(tfile, dst_path, ANNOUNCE_URL, api.passkey, "APL")

                print("\t\tUploading torrent...")
                description = util.generate_description(
                        torrent["torrent"]["id"],
                        sorted(path.glob("**/*" + formats.FormatFlac.SUFFIX))[0],
                        output_format)
                r = api.add_format(torrent, output_format, tfile, description)
                if not r:
                    print("Error on upload. Aborting everything!")
                    # TODO exit

                print("\t\tMoving torrent file...")
                tfile_new = args.torrent_dir / tfile.name
                if tfile_new.exists():
                    print("\t\tError, {} allready exists.".format(tfile_new))
                    # TODO exit
                else:
                    shutil.copyfile(tfile, tfile_new)

                print("\t\tDone.")

                nuploaded += 1
    finally:
        api.cache.save(cache_path)

    print("\nFinished")
    print("Uploaded {} torrents.".format(nuploaded))

if __name__ == "__main__":
    main()
