import subprocess
import os
import signal
import time

class PipelineResult():
    def __init__(self):
        self.returncodes = []
        self.stdouts = []
        self.stderrs = []
        self.cmds = []

class PipelineError(Exception):
    pass

class ProcessFailedError(PipelineError):
    def __init__(self, cmd, returncode, stdout=None, stderr=None):
        self.cmd = cmd
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr

    def __str__(self):
        return "Process '{}' failed with returncode {}".format(" ".join(map(str,self.cmd)), self.returncode)

class Pipeline:
    """
    A job consisting of multiple commands each having its output piped into
    the next one.

    This is similar to the pipe operator of Unix shells.

    The first process is not supplied with any input on stdin.

    The last process must return last as would be typical for any pipelined
    job.

    The pipeline runs in paralell to the python process in seperate processes.
    This means that you can do other stuff while it runs or even run multiple
    pipelines in paralell without the need for seperate threads.
    """
    def __init__(self, cmds):
        """
        Constructor

        :param cmds: A `list` of commands where each command is a `list` of
                     program arguments.
        """
        self.cmds = cmds
        self.processes = None

    def start(self):
        """
        Start this pipeline.

        Non-Blocking.
        """
        last_stdout = None
        self.processes = []
        for cmd in self.cmds:
            # TODO: handle exceptions raised by Popen
            p = subprocess.Popen(cmd, stdin=last_stdout, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if last_stdout is not None:
                last_stdout.close()
            last_stdout = p.stdout
            self.processes.append(p)

    def abort(self):
        """
        Abort all processes of this pipeline.
        """
        if self.processes is None:
            return

        for p in self.processes:
            if p.poll() is None:
                p.terminate()
                try:
                    p.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    p.kill()
                    # Don't catch the TimeoutExpired exception as
                    # wait should return immediately after the process
                    # was killed. If this wait times out just let
                    # the exception terminate the execution as
                    # something has serriously gone wrong if the\
                    # process is still running.
                    p.wait(timeout=5)

    def check(self):
        """
        Check if the pipeline has finished.

        :returns: Ether `None` if the pipeline is still running or a
                  `PipelineResult` instance if it allready finished.

        :raises PipelineError: If the last process of the pipeline returned
                               but an earlier process is still running.
        """
        if self.processes[-1].poll() is None:
            return None

        result = PipelineResult()
        for p in self.processes:
            if p.poll() is None:
                raise PipelineError("The last process of a pipeline has exited but an earlier process is still running. ({})".format(p.args))
            stderr = None
            stdout = None
            if not p.stdout.closed:
                stdout = p.stdout.read()
                p.stdout.close()
            if not p.stderr.closed:
                stderr = p.stderr.read()
                p.stderr.close()
            result.returncodes.append(p.returncode)
            result.stdouts.append(stdout)
            result.stderrs.append(stderr)
            result.cmds.append(p.args)

        return result

def run_pipelines(pipelines, njobs=None):
    """
    Run multiple pipelines in paralell.

    This function will block till all pipelines have been processes.

    :param pipelines: A sequence of `Pipeline` instances.
    :param njobs: Number of pipelines to run in paralell or `None` to
                  run 1 pipeline per available CPU core.

    :raises PipelineError: If anything went wrong. (e.g. typically a command
                           returned a returncode != 0)
    """
    if njobs is None:
        # set jobs to the number of available cpu cores
        njobs = len(os.sched_getaffinity(0))

    pending = pipelines
    running = []
    njobs = min(njobs, len(pending))
    for i in range(njobs):
        pipeline = pending.pop()
        pipeline.start()
        running.append(pipeline)

    try:
        while running:
            running_new = []
            for pipeline in running:
                r = pipeline.check()
                if r is not None:
                    if r.returncodes[-1] != 0:
                        for rc, cmds, stdout, stderr in zip(r.returncodes,
                                                            r.cmds,
                                                            r.stdouts,
                                                            r.stderrs):
                            if rc != 0:
                                raise ProcessFailedError(cmds, rc, stdout, stderr) 
                    elif pending:
                        new_pipeline = pending.pop()
                        new_pipeline.start()
                        running_new.append(new_pipeline)
                else:
                    running_new.append(pipeline)
            running = running_new
            time.sleep(0.1)
    except:
        for pipeline in running:
            pipeline.abort()
        raise
