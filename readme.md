# DemonSpawn
DemonSpawn is a tool for quickly firing off a large number of regression tests. 

This can be used

* as a benchmarking tool for kernels / micro-apps
* as a stress test doing parametrized runs of a single test
* sanity test: after a system upgrade, see if everything still works.

Basic invocation:

    python3 spawn.py configurationfile
    
Currently it requires python at least 3.8.

Copyright Victor Eijkhout 2020-2021

## Quick example

Example:

    system frontera
    user eijkhout
    account A-ccsc
    modules intel/18.0.2 impi/18.0.2
    let rootdir = /your/dir/ectory
    scriptdir %[rootdir]/paw.scripts
    outputdir %[rootdir]/paw.output
    nodes 4
    suite name:paw-mpi type:mpi dir:/home/me/paw p2p_*

## Introduction

The configuration file is completely keyword based. 
The following keywords are defined:

* system : enforce the system on which a configuration can be run
* user : not used
* account: slurm identification of the account that the parallel run is charged to.
* modules: to be loaded at the start of the job. It is assumed that the testsuite
    is compiled with these modules.
* scriptdir : temporary directory where slurm scripts will go.
* outputdir : directory from which the slurm jobs are launched, and which,
    most likely, will wind up containing generated output.
* nodes : node count for the testsuite, unless the suite itself overrides this.
    node count value can also be a colon-separated list, for scalability studies.

* suite : list of key:value pairs, followed by a list of programs
keys:
  name : for identification purposes
  type : mpi jobs are started with ibrun
  dir  : location of the programs
* programs : specified with wildcards but no path; all programs are assumed to be
    in the "dir" value.