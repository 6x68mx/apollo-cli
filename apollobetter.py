from apolloapi import ApolloApi, TorrentCache
import argparse
import configparser
from pathlib import Path
import tempfile
import shutil
import re
import subprocess

CONFIG_PATH = "apollobetter.conf"
ANNOUNCE_URL = "https://mars.apollo.rip/{}/announce"

DESCRIPTION = ("Transcode of [url=https://apollo.rip/torrents.php?torrentid={tid}]https://apollo.rip/torrents.php?torrentid={tid}[/url]\n"
               "\n"
               "This transcoding was done by an autonomous system.")

def get_transcode_dir(flac_dir, output_format):
    output_format = output_format.upper()
    if 'FLAC' in flac_dir.upper():
        transcode_dir = re.sub(re.compile('FLAC', re.I), output_format, flac_dir)
    else:
        transcode_dir = flac_dir + " (" + output_format + ")"
        if output_format != 'FLAC':
            transcode_dir = re.sub(re.compile('FLAC', re.I), '', transcode_dir)
    return transcode_dir

def create_torrent_file(torrent_path, data_path, tracker, passkey, piece_length):
    if torrent_path.exists() or not data_path.exists():
        return False
    
    url = tracker.format(passkey)
    command = ["mktorrent", "-p", "-l", str(piece_length), "-a", url, "-s", "APL", "-o", torrent_path, data_path]
    subprocess.check_output(command, stderr=subprocess.STDOUT)

def main():
    config = configparser.ConfigParser()
    config.read(CONFIG_PATH)

    parser = argparse.ArgumentParser()
    parser.add_argument("--search-dir", help="Where to search for potential uploads", type=Path, required=True)
    parser.add_argument("-o", "--output-dir", help="Destination for converted data", type=Path, required=True)
    parser.add_argument("--torrent-dir", help="Where to put the new *.torrent files", type=Path, required=True)
    #parser.add_argument("--torrent-search-dir", help="Where to search for torrent files", type=Path, required=True)
    parser.add_argument("-l", "--limit", type=int, help="Maximum number of torrents to upload", default=0)
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
    for c in candidates:
        if limit > 0 and nuploaded >= limit:
            break

        print("Processing {} - {} (ID: {}), Needed: {}".format(c["artist"], c["name"], c["torrentid"], ", ".join(c["formats_needed"])))
        
        torrent_response = tc.get(c["torrentid"])
        torrent = torrent_response["response"]["torrent"]

        needed = formats.intersection(c["formats_needed"])
        for output_format in needed:

            # find the torrent data
            transcode_dir = get_transcode_dir(torrent["filePath"], output_format)
            path = args.search_dir / transcode_dir
            if not path.exists():
                #print("\tFiles for \"{}\" not found. Continuing with next Candidate...".format(output_format))
                continue
            print("\tFound {}.".format(path))
            
            # TODO check integrity i.e. if file list in from torrent matches the actuall files on disk

            # find the torrent file
            """
            tfile = args.torrent_search_dir / (transcode_dir + ".torrent")
            if not tfile.exists():
                print("\t\tCouldn't find corresponding torrent file.")
                continue
            print("\t\tFound {}.".format(tfile))
            """

            print("\t\tCreating torrent file...")
            #tfile = args.torrent_dir / (transcode_dir + ".torrent")
            tfile = Path(tmp.name) / (transcode_dir + ".torrent")
            create_torrent_file(tfile, path, ANNOUNCE_URL, api.passkey, 18)

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

    print("\nFinished")
    print("Uploaded {} torrents.".format(nuploaded))

    tc.save(cache_path)

if __name__ == "__main__":
    main()
