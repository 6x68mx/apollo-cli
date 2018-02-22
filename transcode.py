#from formats import FORMATS
from pipeline import Pipeline, run_pipelines, PipelineError

import mutagen.flac
import formats
import subprocess
import os
import signal
import shutil

ALLOWED_EXTENSIONS = (
    '.cue',
    '.gif',
    '.jpeg',
    '.jpg',
    '.log',
    '.md5',
    '.nfo',
    '.pdf',
    '.png',
    '.sfv',
    '.txt',
)

def check_tags(flacs):
    pass

def check_flacs(flacs):
    pass

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
    if not dst_dir.is_dir()
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

def copy_tags(flac, transcode):
    pass

class TranscodeException(Exception):
    pass

def transcode(src, dst, target_format, njobs=None):
    """
    Transcode a release.

    Transcodes all FLAC files in a directory and copies other files.

    :param: src Path object to the source directory
    :param: dst Path object to the target directory.
            This directory must not yet exist but it's parent must exist.
    :param: target_format The format to which FLAC files in `src` should be
            transcoded. See `formats.py`.
    :param: njobs Number of transcodes to run in parallel. If `None` it will
            default to the number of available CPU cores.

    :return: A tuple in the form (sucess, error_msg). error_msg will be None
             on success or a string explaining the error otherwise.
    """
    if dst.exists():
        raise TranscodeException("Destination directory ({}) allready exists".format(dst))
    if not dst.parent.is_dir():
        raise TranscodeException("Parent of destination ({}) does not exist or isn't a directory".format(dst.parent))

    files = list(src.glob("**/*.{}".format(formats.FormatFlac.FILE_EXT)))
    
    flacs = [mutagen.flac.FLAC(f) for f in files]

    if any(flac.info.channels > 2 for flac in flacs):
        raise TranscodeException("More than 2 channels are not supported.")

    bits = flacs[0].info.bits_per_sample
    rate = flacs[0].info.sample_rate
    if any((flac.info.bits_per_sample != bits
            or flac.info.sample_rate != rate)
            for flac in flacs):
        raise TranscodeException("Inconsistent sample rate or bit depth")

    if bits > 16 or not (rate == 44100 or rate == 48000):
        resample = compute_downsample_rate(rate)
        if resample == None:
            raise TranscodeException("Unsupported Rate: {}Hz. Only multiples of 44.1 or 48 kHz are supported".format(rate))
    else:
        resample = None

    try:
        dst.mkdir()
    except PermissionError:
        raise TranscodeException("You do not have permission to write to the destination directory ({})".format(dst))

    jobs = []
    for f in files:
        cmds = generate_transcode_cmds(
            f,
            dst / f.relative_to(src).with_suffix("." + target_format.FILE_EXT),
            target_format,
            resample)
        jobs.append(Pipeline(cmds))

    try:
        run_pipelines(jobs)
    except PipelineError as e:
        shutil.rmtree(dst)
        raise TranscodeException("Transcode failed: " + str(e))
    except:
        shutil.rmtree(dst)
        raise

    try:
        copy_files(src, dst, ALLOWED_EXTENSIONS)
    except:
        shutil.rmtree(dst)
        raise
