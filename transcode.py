from pipeline import Pipeline, run_pipelines, PipelineError
import formats

import mutagen.flac
import mutagen.mp3
from mutagen.easyid3 import EasyID3

import subprocess
import os
import signal
import shutil

ALLOWED_EXTENSIONS = (
    ".cue",
    ".gif",
    ".jpeg",
    ".jpg",
    ".log",
    ".md5",
    ".nfo",
    ".pdf",
    ".png",
    ".sfv",
    ".txt",
)

REQUIRED_TAGS = (
    "title",
    "tracknumber",
    "artist",
    "album",
)

def check_tags(files):
    """
    Check if files containe all required tags.

    :param files: A `list` of `mutagen.FileType` objects.

    :returns: `True` if all files contain the required tags, `False` if not.
    """
    for f in files:
        if any(tag not in f or f[tag] == [""] for tag in REQUIRED_TAGS):
            return False
    return True

def check_flacs(flacs):
    """
    Check if the given flacs are suitable for transcoding.

    :param flacs: A `list` of `mutagen.flac.FLAC` objects.

    :returns: ``(sucess, msg)`` where ``sucess`` states if the files
              are suitable and ``msg`` contains a description of the
              problem if not.
    """
    if any(flac.info.channels > 2 for flac in flacs):
        return (False, "More than 2 channels are not supported.")

    bits = flacs[0].info.bits_per_sample
    rate = flacs[0].info.sample_rate
    if any((flac.info.bits_per_sample != bits
            or flac.info.sample_rate != rate)
            for flac in flacs):
        return (False, "Inconsistent sample rate or bit depth")

    if bits > 16 or not (rate == 44100 or rate == 48000):
        resample = compute_downsample_rate(rate)
        if resample == None:
            return (False, "Unsupported Rate: {}Hz. Only multiples of 44.1 or 48 kHz are supported".format(rate))

    if not check_tags(flacs):
        return (False, "One or more required tags are missing.")

    return (True, None)

def compute_downsample_rate(rate):
    if rate % 44100 == 0:
        return 44100
    elif rate % 48000 == 0:
        return 48000
    else:
        return None

def generate_transcode_cmds(src, dst, target_format, resample=None):
    cmds = []
    if resample is not None:
        cmds.append(["sox", src, "-G", "-b", "16", "-t", "wav", "-", "rate", "-v", "-L", resample, "dither"])
    else:
        cmds.append(["flac", "-dcs", "--", src])

    cmds.append(target_format.encode_cmd(dst))

    return cmds

def copy_files(src_dir, dst_dir, suffixes=None):
    """
    Recursively copy files from `src_dir` to `dst_dir`.

    :param src_dir: Path like object to the source directory.
    :param dst_dir: Path like object to the destination directory.
    :param suffixes: Ether `None`, in this case all files will be copied
                     or a `set` of suffixes in which case only files with one
                     of those suffixes will be copied.
    """
    if not dst_dir.is_dir():
        return

    dirs = [src_dir]
    while dirs:
        for x in dirs.pop().iterdir():
            if x.is_dir():
                dirs.append(x)
            elif suffixes is None or x.suffix in suffixes:
                d = dst_dir / x.relative_to(src_dir)
                d.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(x, d)
                try:
                    shutil.copystat(x, d)
                except PermissionError:
                    # copystat sometimes failes even if copyfile worked
                    # happens mainly with some special filesystems (cifs/samba, ...)
                    # or strange permissions.
                    # Not really a big problem, let's just emit a warning.
                    print("Waring: No permission to write file metadata to {}".format(d))

def copy_tags(src, dst):
    """
    Copy all tags from `src` to `dst` and saves `dst`.

    Both `src` and `dst` must be `mutagen.FileType` objects.
    """
    if type(dst) == mutagen.mp3.EasyMP3:
        valid_tag_fn = lambda k: k in EasyID3.valid_keys.keys()
    else:
        valid_tag_fn = lambda k: True

    for tag in filter(valid_tag_fn, src):
        value = src[tag]
        if value != "":
            dst[tag] = value
    dst.save()

class TranscodeError(Exception):
    pass

def transcode(src, dst, target_format, njobs=None):
    """
    Transcode a release.

    Transcodes all FLAC files in a directory and copies other files.

    :param src: Path object to the source directory
    :param dst: Path object to the target directory.
                This directory must not yet exist but it's parent must exist.
    :param target_format: The format to which FLAC files in `src` should be
                          transcoded. See `formats.py`.
    :param njobs: Number of transcodes to run in parallel. If `None` it will
                  default to the number of available CPU cores.

    :raises TranscodeError:
    """
    if dst.exists():
        raise TranscodeError("Destination directory ({}) allready exists".format(dst))
    if not dst.parent.is_dir():
        raise TranscodeError("Parent of destination ({}) does not exist or isn't a directory".format(dst.parent))

    files = list(src.glob("**/*.{}".format(formats.FormatFlac.FILE_EXT)))
    transcoded_files = [dst / f.relative_to(src).with_suffix("." + target_format.FILE_EXT) for f in files]
    
    flacs = [mutagen.flac.FLAC(f) for f in files]

    success, msg = check_flacs(flacs)
    if not success:
        raise TranscodeError(msg)

    bits = flacs[0].info.bits_per_sample
    rate = flacs[0].info.sample_rate
    if bits > 16 or not (rate == 44100 or rate == 48000):
        resample = compute_downsample_rate(rate)
    else:
        resample = None

    try:
        dst.mkdir()
    except PermissionError:
        raise TranscodeError("You do not have permission to write to the destination directory ({})".format(dst))

    jobs = []
    for f_src, f_dst in zip(files, transcoded_files):
        cmds = generate_transcode_cmds(
            f_src,
            f_dst,
            target_format,
            str(resample))
        jobs.append(Pipeline(cmds))

    try:
        run_pipelines(jobs)

        for flac, transcode in zip(flacs, transcoded_files):
            copy_tags(flac, mutagen.mp3.EasyMP3(transcode))

        copy_files(src, dst, ALLOWED_EXTENSIONS)
    except PipelineError as e:
        shutil.rmtree(dst)
        raise TranscodeError("Transcode failed: " + str(e))
    except:
        shutil.rmtree(dst)
        raise



# EasyID3 extensions:

for key, frameid in {
            "albumartist": "TPE2",
            "album artist": "TPE2",
            "grouping": "TIT1",
            "content group": "TIT1",
        }.items():
    EasyID3.RegisterTextKey(key, frameid)

def comment_get(id3, _):
    return [comment.text for comment in id3["COMM"].text]

def comment_set(id3, _, value):
    id3.add(mutagen.id3.COMM(encoding=3, lang="eng", desc="", text=value))

def originaldate_get(id3, _):
    return [stamp.text for stamp in id3["TDOR"].text]

def originaldate_set(id3, _, value):
    id3.add(mutagen.id3.TDOR(encoding=3, text=value))

EasyID3.RegisterKey("comment", comment_get, comment_set)
EasyID3.RegisterKey("description", comment_get, comment_set)
EasyID3.RegisterKey("originaldate", originaldate_get, originaldate_set)
EasyID3.RegisterKey("original release date", originaldate_get, originaldate_set)
