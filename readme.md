# DemonSpawn
DemonSpawn is a tool for quickly firing off a large number of SLURM jobs. 

This can be used

* as a benchmarking tool for kernels / micro-apps
* as a stress test doing parametrized runs of a single test
* sanity test: after a system upgrade, see if everything still works.

Basic invocation:

    python3 spawn.py configurationfile
    
Currently it requires python version 3.8 or higher.

Copyright Victor Eijkhout 2020-2021

## Quick example

Example configuration file:

    # slurm script parameters
    system frontera
    user eijkhout
    account A-ccsc
    modules intel/18.0.2 impi/18.0.2
    
    # set up directories
    outputdir = /your/dir/ectory/mybenchmark-%[date]
    
    # point-to-point benchmark setup
    queue development
    nodes 2
    ppn 1
    # program to run
    suite name:paw-mpi type:mpi dir:/home/me/paw p2p_*
    
    # collective benchmark setup
    queue normal
    nodes 4,8,12,16
    ppn 1,5,10
    # program to run
    suite name:paw-mpi type:mpi dir:/home/me/paw coll_*
    
## Introduction

The configuration file is completely macro based. A macro is defined in a line

    key value
    
where the value can be one or more words. Macros are evaluated with a `%[macro]` syntax, because why not have yet another sytax? Example:

    key value
    otherkey another-%[key]

Most keywords are a specifier, some have special meanings; see below.

The keyword `suite` triggers the execution of a benchmark suite.
Thus, you can have multiple suites in one configuration file. Each is invoked with the current value of all macros, so you can redefine macros between suite invocations. See the example above, which uses different node and process counts for the point-to-point and collective tests.

A log file will be created in the current directory. It is identifiable by having the current date in the name.

The python script stays active until all submitted SLURM jobs have finished. This is strictly necessary only for handling regression tests after the jobs have finished, but the python script also handles proper closing of files. Thus it is a good idea to 

    nohup python3 spawn.py myconf.txt &
    
Let's talk about the configuration file, which drives everything.

## SLURM macros

Some macros have special meaning for your SLURM script:

* `system` is set to the current hostname. If you specify this macro, it is enforced that this run can only happen on that particular system.
* `account` is used in your slurm script
* `modules` is the list of modules that is loaded at the beginning of your slurm script.
* `queue` is the queue name where the slurm jobs will be submitted. The demonspawn manager will make sure that queue limits are not violated. Queue definitions are currently hard-wired.

## Scaling setup

For an MPI run you want to specify:

* `nodes` : node count for the testsuite, unless the suite itself overrides this. This is either a single number or a colon-separated list, for scalability studies.
* `ppn` : number of processes-per-node. Again, a single number or a colon-separated list.

## Suite setup

The actual test suite is specified by the keyword:

* `suite` : this is followed by a list of key:value pairs, followed by a list of programs, which can use wildcards

Example:

    suite name:paw-mpi-p2p type:mpi dir:%[pawdir] p2p_*

This line defines the suite with the current value of all macros. You can redefine macros for the next suite in the same configuration file.

The available keys are:
 
* `name` : for identification purposes
* `type` : choice of `seq` or `mpi`; MPI jobs are started with ibrun
* `dir`  : location of the programs

After these pairs, the programs are specified with wildcards but no path.

## Directory macros

In order to create a unique output directory, the following macros are useful:

* `pwd` is set to the current working directory where you are running python on the configuration file
* `date` is set to current date-time. 

It is recommended that you define this macro:

* `outputdir` is the directory in which subdirectories `scripts`, `output`, `regression` are created. If you do not specify this, the current directory will be used.

For example:

    outputdir %[pwd]/spawn-mycode-%[date]

## Regression

It is easy to run a regression on all output files of a suite.

    regression grep:Result
    
This will grep through each result file in the suite, leaving the result in

    %[outputdir]/regression-%[suitename].txt
    
Further options:

* `field:5` extract only the 5-th whitespace-separated field


