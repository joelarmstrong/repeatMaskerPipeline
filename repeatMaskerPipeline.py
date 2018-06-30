#!/usr/bin/env python
import os
import shutil
from argparse import ArgumentParser
from glob import glob
from toil.job import Job
from toil.common import Toil
from toil.lib.docker import apiDockerCall
from subprocess import check_call

def run_command(job, command, work_dir, opts):
    if opts.no_docker:
        check_call(command)
    else:
        # Relativize paths
        new_command = [param.replace(work_dir, '/data') for param in command]
        apiDockerCall(job, opts.docker_image, new_command, working_dir='/data',
                      volumes={work_dir: {'bind': '/data', 'mode': 'rw'}},
                      remove=True)

def mask_fasta_job(job, fasta_id, outfile_id, opts):
    temp_dir = job.fileStore.getLocalTempDir()
    input_fasta = os.path.join(temp_dir, 'in.fa')
    job.fileStore.readGlobalFile(fasta_id, input_fasta)
    out_file = os.path.join(temp_dir, 'in.fa.out')
    job.fileStore.readGlobalFile(outfile_id, out_file)
    unmasked_two_bit = os.path.join(temp_dir, 'in.2bit')
    run_command(job, ["faToTwoBit", input_fasta, unmasked_two_bit], temp_dir, opts)
    masked_two_bit = os.path.join(temp_dir, 'out.2bit')
    run_command(job, ["twoBitMask", "-type=.out", unmasked_two_bit, out_file, masked_two_bit], temp_dir, opts)
    masked_fasta = os.path.join(temp_dir, 'out.fa')
    run_command(job, ["twoBitToFa", masked_two_bit, masked_fasta], temp_dir, opts)
    return job.fileStore.writeGlobalFile(masked_fasta)

def concatenate_job(job, fasta_id, input_ids, opts):
    output = os.path.join(job.fileStore.getLocalTempDir(), 'rm.out')
    input_paths = map(job.fileStore.readGlobalFile, input_ids)
    with open(output, 'w') as outfile:
        # Write headers
        outfile.write("""   SW   perc perc perc  query                    position in query     matching       repeat              position in repeat
score   div. del. ins.  sequence                 begin end    (left)   repeat         class/family      begin  end    (left)   ID

""")
        for input_path in input_paths:
            with open(input_path) as f:
                # Remove headers in each split file
                f.readline()
                f.readline()
                f.readline()
                shutil.copyfileobj(f, outfile)
    outfile_id = job.fileStore.writeGlobalFile(output)
    masked_fasta_id = job.addChildJobFn(mask_fasta_job, fasta_id, outfile_id, opts).rv()
    return outfile_id, masked_fasta_id

def repeat_masking_job(job, input_fasta, lift_id, species, opts):
    temp_dir = job.fileStore.getLocalTempDir()
    os.chdir(temp_dir)
    local_fasta = os.path.join(temp_dir, 'input.fa')
    job.fileStore.readGlobalFile(input_fasta, local_fasta, cache=False)
    lift_file = os.path.join(temp_dir, 'lift')
    job.fileStore.readGlobalFile(lift_id, lift_file)
    check_call(["chmod", "a+rw", local_fasta])
    run_command(job, ["RepeatMasker", "-species", species, "-engine", opts.engine, local_fasta], temp_dir, opts)
    output_path = local_fasta + '.out'
    lifted_path = os.path.join(temp_dir, 'lifted.out')
    run_command(job, ["liftUp", "-type=.out", lifted_path, lift_file, "error", output_path], temp_dir, opts)
    masked_out = job.fileStore.writeGlobalFile(lifted_path)
    return masked_out

def split_fasta(job, input_fasta, split_size, work_dir, opts):
    lift_file = os.path.join(work_dir, "lift")
    # Chunk any large sequences in the input into "split_size"-sized
    # chunks, keeping a constant 1kb overlap between chunks. All the
    # chunks get deposited into one file.
    chunks_file = os.path.join(work_dir, "chunks")
    run_command(job, ["faSplit", "size", "-oneFile", "-extra=1000", "-lift=" + lift_file, input_fasta,
                      str(split_size), chunks_file],
                work_dir, opts)
    # Now that there are no large sequences left in the file, we split
    # it by sequence into multiple files, each with about "split_size"
    # bases in them. (This is useful because it avoids creating
    # millions of jobs to process the long tail of very small
    # contigs.)
    run_command(job, ["faSplit", "about", chunks_file + '.fa', str(split_size), os.path.join(work_dir, "out")],
                work_dir, opts)
    return lift_file, glob(os.path.join(work_dir, "out*"))

def split_fasta_job(job, input_fasta, opts):
    work_dir = job.fileStore.getLocalTempDir()
    local_fasta = os.path.join(work_dir, 'in.fa')
    job.fileStore.readGlobalFile(input_fasta, local_fasta)
    lift_file, split_fastas = split_fasta(job, local_fasta, opts.split_size, work_dir, opts)
    split_fasta_ids = [job.fileStore.writeGlobalFile(f) for f in split_fastas]
    lift_id = job.fileStore.writeGlobalFile(lift_file)
    repeat_masked = [job.addChildJobFn(repeat_masking_job, id, lift_id, opts.species, opts).rv() for id in split_fasta_ids]
    return job.addFollowOnJobFn(concatenate_job, input_fasta, repeat_masked, opts).rv()

def convert_to_fasta(job, type, input_file, opts):
    local_file = job.fileStore.readGlobalFile(input_file)
    if type == "gzip":
        with open(local_file) as gzipped, job.fileStore.writeGlobalFileStream() as (uncompressed, uncompressed_fileID):
            check_call(["gzip", "-d", "-c"], stdin=gzipped, stdout=uncompressed)
    else:
        raise RuntimeError("unknown compressed file type")
    return job.addChildJobFn(split_fasta_job, uncompressed_fileID, opts).rv()

def launch_parallel(job, inputs, types, basenames, opts):
    fasta_ids = []
    outfile_ids = []
    for input, type in zip(inputs, types):
        if type != "fasta":
            child_job = Job.wrapJobFn(convert_to_fasta, type, input, opts)
        else:
            child_job = Job.wrapJobFn(split_fasta_job, input, opts)
        job.addChild(child_job)
        fasta_ids.append(child_job.rv(0))
        outfile_ids.append(child_job.rv(1))
    return fasta_ids, outfile_ids, basenames

def makeURL(path):
    if not (path.startswith("file:") or path.startswith("s3:") or path.startswith("http:") \
            or path.startswith("https:")):
        return "file://" + os.path.abspath(path)
    else:
        return path

def parse_args():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('species')
    parser.add_argument('output_path')
    parser.add_argument('input_sequences', help="FASTA or gzipped-FASTA file(s)",
                        nargs="+")
    parser.add_argument('--engine', default='ncbi')
    parser.add_argument('--split_size', type=int, default=200000)
    parser.add_argument('--no-docker', action='store_true')
    parser.add_argument('--docker-image', default='quay.io/joelarmstrong/repeatmasker')
    Job.Runner.addToilOptions(parser)
    return parser.parse_args()

def main():
    opts = parse_args()
    with Toil(opts) as toil:
        if opts.restart:
            outfile_ids, fasta_ids, basenames = toil.restart()
        else:
            input_ids = []
            input_types = []
            input_basenames = []
            for input_sequence in opts.input_sequences:
                input_sequence_id = toil.importFile(makeURL(input_sequence))
                if input_sequence.endswith(".gz") or input_sequence.endswith(".gzip"):
                    type = "gzip"
                else:
                    type = "fasta"
                input_ids.append(input_sequence_id)
                input_types.append(type)

                basename = os.path.basename(input_sequence)
                if basename in input_basenames:
                    raise RuntimeError("Inputs must have unique filenames.")
                input_basenames.append(basename)
            outfile_ids, fasta_ids, basenames = toil.start(Job.wrapJobFn(launch_parallel, input_ids, input_types, input_basenames, opts))
        for outfile_id, fasta_id, basename in zip(outfile_ids, fasta_ids, basenames):
            toil.exportFile(fasta_id, makeURL(os.path.join(opts.output_path, basename + '.masked')))
            toil.exportFile(outfile_id, makeURL(os.path.join(opts.output_path, basename + '.out')))

if __name__ == '__main__':
    main()
