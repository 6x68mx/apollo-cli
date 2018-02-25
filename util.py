from pathlib import Path
import subprocess
import locale
import transcode
import mutagen.flac

def generate_transcode_name(torrent, output_format):
    """Generate the name for the output directory."""
    t = torrent["torrent"]
    g = torrent["group"]

    if t["remastered"]:
        title = (t["remasterTitle"] if t["remasterTitle"] else "remaster")
        additional_info = "{} - {}".format(title, t["remasterYear"])
        if t["remasterRecordLabel"]:
            additional_info += " - {}".format(t["remasterRecordLabel"])
    else:
        additional_info = g["year"]

    if len(g["musicInfo"]["artists"]) == 1:
        artist = g["musicInfo"]["artists"][0]["name"]
    else:
        artist = "Various Artists"

    return "{} - {} ({}) - {} [{}]".format(artist,
                                           g["name"],
                                           additional_info,
                                           t["media"],
                                           output_format.NAME)


def create_torrent_file(torrent_path, data_path, tracker, passkey=None, source=None, piece_length=18):
    """
    Creates a torrentfile using ``mktorrent``

    :param: torrent_path Full path of the torrent file that will be created.
    :param: data_path Path to the file/directory from which to create the torrent.
    :param: tracker URL of the tracker, if `passkey` is specified this should contain "{}" which will be replaced with the passkey.
    :param: passkey A passkey to insert into the tracker URL. (Needed for private trackers)
    :param: piece_length The piece length in 2^n bytes.
    """
    if torrent_path.exists() or not data_path.exists():
        return False

    if passkey is not None:
        url = tracker.format(passkey)
    else:
        url = passkey

    command = ["mktorrent", "-p", "-l", str(piece_length), "-a", url, "-o", torrent_path]
    if source:
        command.extend(["-s", source])
    command.append(data_path)
    #command = ["mktorrent", "-p", "-l", str(piece_length), "-a", url, "-s", "APL", "-o", torrent_path, data_path]
    subprocess.check_output(command, stderr=subprocess.STDOUT)

def parse_file_list(data):
    """
    Parse the file list contained in the torrent dict from the Gazelle API.

    :param: data The string to parse

    :return: A dict. The keys are the relative paths of the files and the
             values are the size of the file in bytes.
    """
    files = {}
    for x in data.split("|||"):
        name, size = x.split("{{{")
        size = int(size[:-3])
        files[name] = size
    return files

def check_dir(path, files, names_only=False):
    """
    Check if a local directory matches the file list of a torrent.

    :param: path Local directory to compare. Must be a Path like object.
    :param: files A dict as returned by `parse_file_list`.
    :param: names_only Check only if the filenames match. (Ignore size)

    :return: `True` if the contents of `path` match exactly the files listed
             in `files` and `False` otherwise or if `path` is not a directory.
    """
    if not path.is_dir():
        return False

    files = dict(files)
    dirs = [path]
    while dirs:
        for x in dirs.pop().iterdir():
            if x.is_dir():
                dirs.append(x)
            elif x.is_file():
                name = str(x.relative_to(path))
                if (name in files
                        and (names_only
                             or x.stat().st_size == files[name])):
                    files.pop(name)
                else:
                    return False

    if files:
        return False

    return True

def find_dir(name, search_dirs):
    """
    Search for a directory in multiple parent directories.

    :param: name The directory you want to find.
    :param: search_dirs List of `Path` objects in which to search for `name`.

    :return: A `Path` object to the directory if it was found, otherwise `None`.
    """
    for d in search_dirs:
        path = d / name
        try:
            if path.is_dir():
                return path
        except OSError as e:
            # Under certain conditions the generated filename could be
            # too long for the filesystem. In this case we know that
            # this path couldn't exist anyway an can can skip it.
            if e.errno == errno.ENAMETOOLONG:
                continue
            else:
                raise

def get_flac_version():
    if not hasattr(get_flac_version, "version"):
        cp = subprocess.run(["flac", "--version"],
                            stdout=subprocess.PIPE,
                            encoding=locale.getpreferredencoding(False))
        get_flac_version.version = cp.stdout.strip()
    return get_flac_version.version

def get_sox_version():
    if not hasattr(get_sox_version, "version"):
        cp = subprocess.run(["sox", "--version"],
                            stdout=subprocess.PIPE,
                            encoding=locale.getpreferredencoding(False))
        get_sox_version.version = cp.stdout.split(":")[1].strip()
    return get_sox_version.version

def get_lame_version():
    if not hasattr(get_lame_version, "version"):
        cp = subprocess.run(["lame", "--version"],
                            stdout=subprocess.PIPE,
                            encoding=locale.getpreferredencoding(False))
        get_lame_version.version = cp.stdout.splitlines()[0].strip()
    return get_lame_version.version

def generate_description(tid, src_path, target_format):
    """
    Generate a release description for apollo.rip.

    :param tid: ID of the source torrent.
    :param src_path: `Path` to a flac file of the source.
    :param target_format: The format of the transcode. (see `formats`)

    :returns: The description as string.
    """
    flac = mutagen.flac.FLAC(src_path)
    cmds = transcode.generate_transcode_cmds(
            src_path.name,
            src_path.with_suffix(target_format.SUFFIX).name,
            target_format,
            transcode.compute_resample(flac))

    process = " | ".join(" ".join(cmd) for cmd in cmds)
    return ("Transcode of [url=https://apollo.rip/torrents.php?torrentid={tid}]https://apollo.rip/torrents.php?torrentid={tid}[/url].\n"
            "\n"
            "Process used:\n"
            "[code]{process}[/code]\n"
            "\n"
            "Tool versions:\n"
            "[code]{flac}\n"
            "{sox}\n"
            "{lame}[/code]\n"
            "\n"
            "Created with apollo-cli.\n"
            "This transcode was performed by an autonomous system. Please contact me (the uploader) if it made a mistake."
           ).format(
               tid=tid,
               process=process,
               flac=get_flac_version(),
               sox=get_sox_version(),
               lame=get_lame_version()
           )
