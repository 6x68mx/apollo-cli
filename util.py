from pathlib import Path

def get_transcode_dir(flac_dir, output_format):
    """
    Generate the name of the output directory for the given flac directory and format.

    The code for this function is a slightly modified version of a similar
    function in xanaxbetter so it should generate the same names.

    :param: flac_dir Name of the original FLAC dir. (ONLY name not full path!)
    :param: output_format Name of the output format as string.
    """
    output_format = output_format.upper()
    if 'FLAC' in flac_dir.upper():
        transcode_dir = re.sub(re.compile('FLAC', re.I), output_format, flac_dir)
    else:
        transcode_dir = flac_dir + " (" + output_format + ")"
        if output_format != 'FLAC':
            transcode_dir = re.sub(re.compile('FLAC', re.I), '', transcode_dir)
    return transcode_dir

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
    while len(dirs) > 0:
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
