#!/usr/bin/env python
import time
import os
import subprocess
from argparse import ArgumentParser
from glob import glob
from toil.job import Job
from toil.common import Toil
from subprocess import check_call

# There are 3 phases to the process: splitting the input, running
# repeatmasker, and concatenation of the repeat-masked pieces.

def concatenate_job(job, input_ids):
    output = os.path.join(job.fileStore.getLocalTempDir(), 'rm.out')
    input_paths = map(job.fileStore.readGlobalFile, input_ids)
    cat = subprocess.Popen("xargs -0 cat >> {output}".format(output=output),
                           stdin=subprocess.PIPE, shell=True)
    cat.communicate("\0".join(input_paths))
    return job.fileStore.writeGlobalFile(output)

def repeat_masking_job(job, input_fasta, lift_id, species):
    temp_dir = job.fileStore.getLocalTempDir()
    os.chdir(temp_dir)
    local_fasta = os.path.join(temp_dir, 'input.fa')
    job.fileStore.readGlobalFile(input_fasta, local_fasta, cache=False)
    lift_file = job.fileStore.readGlobalFile(lift_id)
    check_call(["chmod", "a+rw", local_fasta])
    check_call(["RepeatMasker", "-species", species, local_fasta])
    output_path = local_fasta + '.out'
    lifted_path = os.path.join(temp_dir, 'lifted.out')
    check_call(["liftUp", "-type=.out", lifted_path, lift_file, "error", output_path])
    masked_out = job.fileStore.writeGlobalFile(lifted_path)
    return masked_out

def split_fasta(input_fasta, split_size, work_dir):
    lift_file = os.path.join(work_dir, "lift")
    # Chunk any large sequences in the input into "split_size"-sized
    # chunks, keeping a constant 1kb overlap between chunks. All the
    # chunks get deposited into one file.
    chunks_file = os.path.join(work_dir, "chunks")
    check_call(["faSplit", "size", "-oneFile", "-extra=1000", "-lift=" + lift_file, input_fasta,
                str(split_size), chunks_file])
    # Now that there are no large sequences left in the file, we split
    # it by sequence into multiple files, each with about "split_size"
    # bases in them. (This is useful because it avoids creating
    # millions of jobs to process the long tail of very small
    # contigs.)
    check_call(["faSplit", "about", chunks_file + '.fa', str(split_size), os.path.join(work_dir, "out")])
    return lift_file, glob(os.path.join(work_dir, "out*"))

def split_fasta_job(job, input_fasta, opts):
    work_dir = job.fileStore.getLocalTempDir()
    local_fasta = os.path.join(work_dir, 'in.fa')
    job.fileStore.readGlobalFile(input_fasta, local_fasta)
    lift_file, split_fastas = split_fasta(local_fasta, opts.split_size, work_dir)
    split_fasta_ids = [job.fileStore.writeGlobalFile(f) for f in split_fastas]
    lift_id = job.fileStore.writeGlobalFile(lift_file)
    repeat_masked = [job.addChildJobFn(repeat_masking_job, id, lift_id, opts.species).rv() for id in split_fasta_ids]
    return job.addFollowOnJobFn(concatenate_job, repeat_masked).rv()

def parse_args():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('input_fasta')
    parser.add_argument('species')
    parser.add_argument('split_size', type=int, default=200000)
    parser.add_argument('output')
    Job.Runner.addToilOptions(parser)
    return parser.parse_args()

def main():
    opts = parse_args()
    with Toil(opts) as toil:
        if opts.restart:
            result_id = toil.restart()
        else:
            input_fasta_id = toil.importFile('file://' + os.path.abspath(opts.input_fasta))
            job = Job.wrapJobFn(split_fasta_job, input_fasta_id, opts)
            result_id = toil.start(job)
        toil.exportFile(result_id, 'file://' + os.path.abspath(opts.output))

if __name__ == '__main__':
    main()
