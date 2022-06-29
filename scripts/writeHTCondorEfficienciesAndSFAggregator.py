
import sys
sys.path.append("..")

import os
import argparse

from utils.utils import (
    build_prog_path,
    join_name_trigger_intersection as joinNTC,
    join_strings,
    set_pure_input_namespace,
)
from scripts.jobWriter import JobWriter

@set_pure_input_namespace
def writeHTCondorEfficienciesAndSFAggregator_outputs(args):
    job_f, subm_f, check_f = JobWriter.define_output( localdir=args.localdir,
                                                      data_folders='EffAndSFAgg',
                                                      tag=args.tag )
    return job_f[0], subm_f[0], check_f[0]

@set_pure_input_namespace
def writeHTCondorEfficienciesAndSFAggregator(args):
    prog = build_prog_path(args.localdir, 'aggregateEfficienciesAndScaleFactors.py')
    outs_job, outs_submit, outs_check = writeHTCondorEfficienciesAndSFAggregator_outputs(args)
    jw = JobWriter()

    #### Write shell executable (python scripts must be wrapped in shell files to run on HTCondor)
    command = join_strings( '{} '.format(prog),
                            '--indir {} '.format(indir),
                            '--outdir {} '.format(outdir),
                            '--channel ${1} ',
                            '--file_prefix {} '.format(args.file_prefix),
                            '--variables {} '.format(' '.join(args.variables,)),
                            '--subtag {} '.format(subtag=args.subtag) )

    if args.debug:
        command += '--debug '

    jw.write_init(outs_job, command, args.localdir)
    jw.add_string('echo "aggregateEfficienciesAndScaleFactors done."')

    #### Write submission file
    jw.write_init( filename=outs_submit,
                   executable=outs_job,
                   outfile=outs_check,
                   queue='short' )

    qlines = []
    for chn in args.channels:
        qlines.append('  {}'.format(chn))

    jw.write_queue( qvars=('channel',),
                    qlines=qlines )
