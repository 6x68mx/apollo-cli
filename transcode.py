#from formats import FORMATS

import mutagen.flac
import formats
import subprocess
import os
import signal
import shutil

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

def start_cmd_pipeline(cmds):
    last_stdout = None
    processes = []
    for cmd in cmds:
        p = subprocess.Popen(cmd, stdin=last_stdout, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if last_stdout is not None:
            last_stdout.close()
        last_stdout = p.stdout
        processes.append(p)
    return processes

def abort_all_jobs(jobs):
    for j in jobs:
        for p in j:
            if p.poll() is None:
                p.terminate()
                try:
                    p.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    p.kill()
                    p.wait(timeout=5)

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

    if njobs is None:
        # set jobs to the number of available cpu cores
        njobs = len(os.sched_getaffinity(0))

    pending = list(files)
    running_jobs = []
    njobs = min(njobs, len(pending))
    for i in range(njobs):
        f = pending.pop()
        running_jobs.append(
            start_cmd_pipeline(
                generate_transcode_cmds(
                    f,
                    dst / f.relative_to(src).with_suffix("." + target_format.FILE_EXT),
                    target_format,
                    resample)))

    while running_jobs:
        running_jobs_new = []
        for job in running_jobs:
            if job[-1].poll() is not None:
                for p in reversed(job):
                    try:
                        if p.returncode:
                            stdout = ""
                            stderr = ""
                            if not p.stdout.closed:
                                stdout = p.stdout.read()
                            if not p.stderr.closed:
                                stderr = p.stderr.read()
                            abort_all_jobs(running_jobs)
                            shutil.rmtree(dst)
                            if p.returncode == -signal.SIGPIPE:
                                raise TranscodeException("Error: process exited with SIGPIPE\ncmd: {}\nstdout:\n{}\nstderr:\n{}".format(" ".join(p.args), stdout, stderr))
                            else:
                                raise TranscodeException("Error: process exited with returncode {}cmd: \n{}\nstdout:\n{}\nstderr:\n{}".format(p.returncode, " ".join(p.args), stdout, stderr))
                    except subprocess.TimeoutExpired as e:
                        # This should never happen as we know that the last
                        # process in the pipeline has finished and therefore
                        # all previous processes should have finished as well.
                        # This means that at least one of the earlier steps in the
                        # pipeline probably hangs.
                        # TODO: kill hanging process, abort all transcodes,
                        #       clean up and return with error
                        abort_all_jobs(running_jobs)
                        shutil.rmtree(dst)
                        raise TranscodeException("Error: The last process of a pipeline has exited but an earlier process is still running. This should not happen!\ncmd: {}".format(" ".join(p.args)))
                
                if pending:
                    f = pending.pop()
                    cmds = generate_transcode_cmds(
                            f,
                            dst / f.relative_to(src).with_suffix("." + target_format.FILE_EXT),
                            target_format,
                            resample)
                    running_jobs_new.append(start_cmd_pipeline(cmds))
            else:
                running_jobs_new.append(job)
        running_jobs = running_jobs_new
    
    """
    for f in files:
        cmds = generate_transcode_cmds(f, dst / f.relative_to(src), target_format, resample)
    """

