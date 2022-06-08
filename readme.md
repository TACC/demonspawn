# DemonSpawn
DemonSpawn is a tool for quickly firing off a large number of SLURM jobs. 

This can be used

* as a benchmarking tool for kernels / micro-apps
* as a stress test doing parametrized runs of a single test
* sanity test: after a system upgrade, see if everything still works.

Copyright Victor Eijkhout 2020-2022

For questions and problems, please submit a github issue.

## Quick example

Example configuration file:

    # slurm script parameters
    system frontera
    user eijkhout
    account A-ccsc
    modules intel/18.0.2 impi/18.0.2
    
    # point-to-point benchmark setup
    queue development
    nodes 2
    ppn 1
    # program to run
    suite name:paw-ptp type:mpi dir:/home/me/paw p2p_*
    
    # collective benchmark setup
    queue normal
    nodes 4,8,12,16
    ppn 1,5,10
    # program to run
    suite name:paw-col type:mpi dir:/home/me/paw coll_*
    
## Introduction

Demonspawn is a script that schedules SLURM job. Invocation:

    python3 spawn.py [ options ] configurationfile

Option flags:

* `-h --help` : print help and quit.
* `-d --debug` : lots of debug output.
* `-f --filesonly` : generate all script files, but do not submit.
* `-o --outputdir` + `dir` : specify output directory; omitting this gives a standard output name that includes the current date.
* `-r --regression` + `dir` : only run the regression tests on output generated in a previous run.
* `-c --compare` + `dir` : compare regression results in current output directory, and one generated in a previous run.

The python script stays active until all submitted SLURM jobs have finished. This is strictly necessary only for handling regression tests after the jobs have finished, but the python script also handles proper closing of files. Thus it is a good idea to 

    nohup python3 spawn.py myconf.txt &
    
The configuration is specified split over the file on the commandline, and a `.spawnrc` file, which can be used for common options, such as your username, and the slurm account to bill your runs to. Since they have the exact same syntax, we will not distinguish between them, and mostly discuss the configuration file.

### Macros

The configuration, specified in the file given on the commandline, is completely macro based. A macro is defined in a line

    key value
    
where the value can be one or more words. Macros are evaluated with a `%[macro]` syntax, because why not have yet another sytax? Example:

    key value
    otherkey another-%[key]

Most keywords are a specifier, some have special meanings; see below.

The keyword `suite` triggers the execution of a benchmark suite.
Thus, you can have multiple suites in one configuration file. Each is invoked with the current value of all macros, so you can redefine macros between suite invocations. See the example above, which uses different node and process counts for the point-to-point and collective tests.

### File structure

Demonspawn generates output:

* A single log file for the full configuration will be created in the current directory. It is identifiable by having the current date in the name.
* An output directory is generated based on the required `outputdir` key. This will contain subdirectories `scripts` and `output` with the SLURM scripts and their standard out/err respectively.
* If you do regression, the output directory will also contain a single regression file for each `suite` line.

## SLURM macros

Some macros have special meaning for your SLURM script:

* `system` is set to the current hostname. If you specify this macro, it is enforced that this run can only happen on that particular system.
* `account` is used in your slurm script as the value of the `-A` or `--account` flag.
* `modules` is the list of modules that is loaded at the beginning of your slurm script. The value of `%[modules]` has all spaces stripped. Special case: `modules restore foo` will cause the saveset `foo` to be restored.
* `queue` is the value of the slurm `-p` flag: the partition, or queue, name where the jobs of the next suite will be submitted. The demonspawn manager will make sure that queue limits are not violated. The queue name has optional limits on the number of simultaneous jobs:

    `queue somequeue limit:2`

   Suggestion: specify queue limits in the `.spawnrc` file. The last specified queue will be used as the default, or you can explicitly choose a queue in the configuration file.
    
* `time` is a `hh:mm:ss` specification for the slurm `-t` flag.

It is possible to add custom `#SBATCH foo=bar` lines to a script. For this, put one or more lines

    sbatch foo=bar

in the configuration. This the only option that is cumulative: these options are gathered up and used for each script. Thus they can not be reset between `suite` lines.

## Scaling setup

For an MPI run you want to specify:

* `nodes` : node count for the testsuite, unless the suite itself overrides this. This is either a single number or a comma-separated list, for scalability studies.
* `ppn` : number of processes-per-node. A single number or a comma-separated list.
* `threads` : OpenMP thread count. Single number or comma-separated list. A negative value indicates a thread count such that the product of MPI processes and OpenMP threads equals `SLURM_CPUS_ON_NODE`. (A zero value means that no threading is used; this value is ignored.)

## Suite setup

Some macros related to running the benchmark programs.

* `jobname` : this is by default "`spawn`". It is used for the name of the logfile. You can only once define this in your configuration. The logfile, by the way, has as time stamp, in case you re-use the output directory.
* `env` : this is used to specify environment variables. At the moment this is strictly additive: each suite is started with the sum total of specified options at that point. Example:

    `env PETSC_OPTIONS -ksp_max_it 100 -ksp_monitor`

You can have multiple test suites. A test suite is specified by the keyword:

* `suite` : this is followed by a list of key:value pairs, followed by a list of programs, which can use wildcards

Example:

    suite name:paw-mpi-p2p type:mpi dir:%[pawdir] p2p_*

This line defines the suite with the current value of all macros. 

If there is more than one suite in a configuration file, each suite is fully finished before the next one is started. This is convenient if the suite runs a shell script that does a custom recompilation. You can redefine macros for the next suite in the same configuration file.

The available keys are:
 
* `name` : for identification purposes
* `type` : choice of `seq` or `mpi`; MPI jobs are started with ibrun
* `dir`  : location of the programs

After these pairs, the programs are specified with wildcards but no path.

## Directory macros

It is required that you define this macro:

* `outputdir` is the directory in which subdirectories `scripts`, `output`, `regression` are created.

In order to create a unique output directory, the following macros are useful:

* `pwd` is set to the current working directory where you are running python on the configuration file
* `date` is set to current date-time.
* `mpi` is set to `LMOD_FAMILY_COMPILER`.

For example:

    outputdir %[pwd]/spawn-mycode-%[mpi]-%[date]

## Regression

It is easy to run a regression on all output files of a suite by specifying the `regression` key. You can specify what to regress on:

    regression grep:Result
    
This will grep through each result file in the suite. You can also

    regression line:last

with possible options `first`, `last`.

Regression results are written to a single file

    %[outputdir]/regression-%[suitename].txt
    
Additionally, each job regression goes into a separate file

    %[outputdir]/regression/<jobname>.out
    
Note: the regression specification is part of the suite definition, so it needs to come *before* the `suite` line.

Further options:

* `field:5` extract only the 5-th whitespace-separated field; this numbering is 1-based
* `label:abcd` put a label in front of the regression line. This can be a literal string, or a macro. If multiple `label` options are given, they are all used, in the sequence specified, separated by a space character.

If you want to run a regression on already generated output, run the configuration again, but with the `-r` or `--regression` flag.

You can compare the regressions of two runs by using the `-c old_output_dir` option. This will compare the files in the `regression` subdirectory, leaving the results in a file `regression_compare`. 

Normally, regression comparison results in both values being written to the `regression_compare` file. However, numerical comparison is enabled by having an option `margin:10percent` in the `regression` line.

## Limitations

* Currently the software requires python version 3.8 or higher.
* The `system` keyword only works at TACC
* The `mpi` keyword depends on Lmod.

## Changelog

0.1 somewhere around `2021/12/01`: posted on reddit

0.2 `2022/02/15`: adding module restore, `regressiononly` option

0.3 logfile now goes into output dir, regression flag is now `regression`

0.4 regressions go into separate files, new flag for regression comparing