#!/usr/bin/env python
#
# Victor Eijkhout
# 2020-03-09

#--------------------------------------------------------------------------------
# System
#from __future__ import print_function
import datetime
from functools import reduce
import io
import os
import re
import sys
import subprocess as sp
import time


def DefaultModules():
  return "intel/18.0.2"

def module_string(txt):
  # make module list from string
  txt = txt.split(" ")
  # slashes -> dashes in each module
  txt = [ re.sub('/','-',m) for m in txt ]
  # join modules with underscore for configuration name
  txt = '_'.join( txt )
  return txt

class Job():
    def __init__(self,**kwargs):
        #default values to be overwritten later
        self.suite = "paw"
        self.queue = "normal"
        self.nodes_cores = 1,10
        self.runtime = "00:05:00"
        self.user = "nosuchuser"
        self.account = "MyAccount"
        self.runner = "./"
        self.benchmark = "echo foo"
        self.trace = False
        self.logfile = None # this is the global log
        self.regressionfile = None
        self.set_has_not_been_submitted()

        tracestring = ""
        for key,val in kwargs.items():
            tracestring += " {}={}".format(key,val)
            self.__dict__[key] = val
        tracestring = f"Creating job <<{self.name()}>> with" + tracestring

        self.nodes,self.ppn = self.nodes_cores
        if not self.logfile: 
            print("Trying to create job without logfile"); sys.exit(1)
        if self.regression and not self.regressionfile:
            print("Trying to create regression job without regressionfile"); sys.exit(1)
        self.CheckValidDir("scriptdir")
        self.CheckValidDir("outputdir")
        self.output_file_name = self.outputdir+"/"+self.name()+".spawnout"
        self.slurm_output_file_name = self.outputdir+"/"+self.name()+".out%j"
        self.script_name = self.scriptdir+"/"+self.name()
        tracestring += f" in file <<{self.script_name}>>"

        if self.trace:
            print(tracestring)
        if self.logfile:
            self.logfile.write(tracestring+"\n")
    def generate_script(self):
        bench_program = self.runner+self.dir+"/"+self.benchmark
        script_content =  \
f"""#!/bin/bash
#SBATCH -J {self.name()}
#SBATCH -o {self.slurm_output_file_name}
#SBATCH -e {self.slurm_output_file_name}
#SBATCH -p {self.queue}
#SBATCH -t {self.runtime}
#SBATCH -N {self.nodes}
#SBATCH --tasks-per-node {self.ppn}
#SBATCH -A {self.account}

module reset
module load {self.modules}

cd {self.outputdir}
{bench_program} | tee {self.output_file_name}
"""
        with open( self.script_name,"w" ) as batch_file:
            batch_file.write(script_content)
        if self.trace:
            print("Written job file <<{}>>".format(self.script_name))
        return self.script_name
    def CheckValidDir(self,dirname):
        if dirname not in self.__dict__.keys() or self.__dict__[dirname] is None:
            print("No {} supplied to job".format(dirname)); raise
        dir = self.__dict__[dirname] 
        if not os.path.exists(dir):
            print("dirname <<{}>> does not exist".format(dir)); raise
    def name(self):
        return re.sub(" ","_",
                      re.sub("/","",
                             re.sub(".*/","",self.benchmark) \
                             +"-"+ \
                             module_string(self.modules) \
                             +"-N"+str(self.nodes)+"-n"+str(self.ppn) \
                         ) \
                  )
    def __str__(self):
        return f"{self.benchmark} N={self.nodes} ppn={self.cores} regression={self.regression}"
    def submit(self,logfile=None):
        p = sp.Popen(["sbatch",self.script_name],stdout=sp.PIPE)
        submitted = False
        for line in io.TextIOWrapper(p.stdout, encoding="utf-8"):
            line = line.strip()
            if self.trace:
                print( line )
            if self.logfile is not None:
                self.logfile.write(line+"\n")
            submitted = re.search("(Submitted.* )([0-9]+)",line)
            if submitted:
                id = submitted.groups()[1]
                self.set_has_been_submitted(id)
                return self.jobid
        if not submitted:
            raise Exception("Failure to submit")
        return 0
    def set_has_not_been_submitted(self):
        self.jobid = "1"; self.status = "PRE"
    def get_has_been_submitted(self):
        # meaning: submitted or running or finished
        return self.status!="PRE"
    def set_has_been_submitted(self,id):
        self.status = "PD"; self.jobid = id
        self.logfile.write(f"Status to pending, id={id}")
        if re.search("%j",self.slurm_output_file_name):
            self.slurm_output_file_name = re.sub("%j",self.jobid,self.slurm_output_file_name)
            self.logfile.write(f", output file name set to {self.output_file_name}")
        self.logfile.write("\n")
    def status_update(self,status):
        if status!="NS":
            # job was found in slurm, status is PD or R or CG
            self.status = status 
        else:
            # job not found in slurm: either not scheduled, or already finished
            if self.jobid!="1":
                # it has an actual id
                if self.status!="POST":
                  self.status = "POST" # done running
                  if self.logfile:
                    self.logfile.write(f"Doing regression <<{self.regression}>> on job {self.name()}\n")
                  if self.regression:
                    self.do_regression()
                    if self.logfile: self.logfile.write(f".. done regression\n")
    def is_running(self):
        return self.jobid!="1" and self.status=="R"
    def is_pending(self):
        return self.jobid!="1" and self.status=="PD"
    def get_done_running(self):
        return self.status=="POST"
    def get_status(self):
        id = self.jobid
        # squeue -j 6137988 -h -o "%t"
        p = sp.Popen(["squeue","-j",id,"-h","-o","%t"],stdout=sp.PIPE)
        status = "CD"
        for status in io.TextIOWrapper(p.stdout, encoding="utf-8"):
            status = status.strip()
        return status
    def do_regression(self):
        print(f"Doing regression on {self.output_file_name}")
        rtest = {}
        for kv in self.regression.split():
            if not re.search(":",kv):
                print(f"ill-formed regression clause <<{kv}>>")
                continue
            k,v = kv.split(":")
            rtest[k] = v
        v = rtest["grep"]
        with open(self.output_file_name,"r") as output_file:
          for line in output_file:
            line = line.strip()
            if re.search(v,line):
              print(line)
              self.logfile.write(line+"\n")
              self.regressionfile.write(self.name()+":"+line+"\n")
def parse_suite(suite_option_list):
  suite = { "name" : "unknown", "runner" : "", "dir" : "./", "apps" : [] }
  for opt in suite_option_list:
    if re.search(":",opt):
      key,val = opt.split(":")
      #print("benchmark suite option {}={}".format(key,val))
      if key=="type":
        if  val=="mpi":
          suite["runner"] = "ibrun "
      else:
        suite[key] = val
    else:
      #print("benchmark suite app {}".format(opt))
      if re.search(r'\*',opt):
        dir = suite["dir"]
        if not os.path.exists(dir) or not os.path.isdir(dir):
          raise Exception("No such directory: <<{}>>".format(dir))
        p = sp.Popen( "cd {} ; ls {}".format( dir,opt ),\
                      stdout=sp.PIPE,shell=True )
        out,err = p.communicate()
        for a in out.split():
          suite["apps"].append(a.decode("utf-8"))
        print("application wildcards gives apps <<{}>>".format(suite["apps"]))
      else:
        suite["apps"].append(opt)
  return suite

##
## return nodes and cores as list of equal length
##
def nodes_cores_values(configuration):
  nodes = configuration.get("nodes",None)
  if nodes is None:
    print("Node specification always needed"); raise Exception()
  cores = configuration.get("cores",None)
  if not cores is None:
    print("Cores keyword not supported"); raise Exception()
  ppn   = configuration.get("ppn",None)
  if ppn is None:
    print("ppn specification always needed"); raise Exception()
  if cores is None and ppn is None:
    print("Configuration needs to specify `cores' or `ppn'")
    raise Exception()
  if not isinstance(nodes,list):
    nodes = [ nodes ]
  if not isinstance(ppn,list):
    ppn = [ ppn ]
  nodes_cores = [ [ [n,p] for n in nodes ] for p in ppn ]
  nodes_cores = [ np for sub in nodes_cores for np in sub ] 
  print("nodes_cores:",nodes_cores)
  return nodes_cores

def running_jobids(qname,user):
    ids = []
    p = sp.Popen(["squeue","-u",user,"-p",qname,"-h","-o","%A %t"],stdout=sp.PIPE)
    for status in io.TextIOWrapper(p.stdout, encoding="utf-8"):
        status = status.strip() # print("job status line <<{}>>".format(status))
        id,stat = status.split()
        ids.append(id)
    print("Running jobs for user={} on queue={}: {}".format(user,qname,ids))
    return ids

class Queue():
    def __init__(self,name,limit=1):
        self.name = name; self.limit = limit; self.jobs = []
    def enqueue(self,j):
        self.jobs.append(j)
        qrunning = running_jobids(self.name,j.user)
        if len(qrunning)<self.limit:
            jobid = j.submit()
    def status_update(self,status_dict):
        #
        # use the squeue output
        #
        for j in self.jobs:
            if j.jobid in status_dict.keys():
                j.status_update(status_dict[j.jobid])
            else:
                j.status_update("NS") # not found in slurm
        nrunning = sum( [ 1 for j in self.jobs if j.is_running() ] ) \
                   + sum( [ 1 for j in self.jobs if j.is_pending() ] )
        nslots = self.limit-nrunning
        print(f"Queue {self.name} has #in queue={nrunning}, space for: {nslots}")
        for j in self.jobs:
            if nslots==0: break
            if not j.get_has_been_submitted():
                j.submit()
                nslots -= 1
    def how_many_unfinished(self):
        return sum( [ 1 for j in self.jobs if not j.get_done_running() ] )
    def ids(self):
        return [ j.jobid for j in self.jobs if j.jobid!="1" ]

class Queues():
    def __init__(self,**kwargs):
        self.queues = {}
        self.testing = kwargs.get("testing",False)
        self.logprinter = kwargs.get( "logprinter",lambda x:print("log message:",x) )
    def add_queue(self,name,limit):
        self.queues[name] = Queue(name,limit)
    def enqueue(self,j):
        qname = j.queue
        if not qname in self.queues.keys():
            raise Exception("No such queue: {}".format(qname))
        else:
            queue = self.queues[qname]
            if self.testing:
                print("test run: no actual submit")
            else:
                jobid = queue.enqueue(j)
    def wait_for_jobs(self):
        if self.testing:
            print("Done, since this was only a test")
        else:
            while True:
                njobs_to_go = self.update_jobs_status()
                if njobs_to_go==0: break
                time.sleep(1)
            self.logprinter("Done all jobs")
    def update_jobs_status(self):
        #
        # ids of all jobs; ids may be 1 if not started, or valid but already finished
        #
        ids = reduce( lambda x,y:x+y,
                      [ q.ids() for q in self.queues.values() ] )
        #print("All ids: <<{}>>".format(ids))
        id_string = ",".join( ids )
        print("Getting status for",id_string)
        #
        # get the status for all jobs. some of them may not yet be running, or finished
        #
        p = sp.Popen(["squeue","-j",id_string,"-h","-o","%A %t"],stdout=sp.PIPE)
        status_dict = { id:"NS" for id in ids }; running = []; pending = []
        for status in io.TextIOWrapper(p.stdout, encoding="utf-8"):
            id,stat = status.strip().split()
            print("Job {} status {}".format(id,stat))
            status_dict[id] = stat
            if stat=="R":
                running.append(id)
            elif stat=="PD":
                pending.append(id)
        for q in self.queues.values():
            q.status_update(status_dict)
        nrunning = len(running); npending = len(pending)
        ntogo = sum( [ q.how_many_unfinished() for q in self.queues.values() ] )
        print("Jobs unfinished: {}, running: {}, pending in queue: {}".\
              format(ntogo,len(running),len(pending)))
        return ntogo

class TestSuite():
  def __init__(self,suite,configuration):
    ## this needs to come from the `suite' list
    self.name = configuration.pop("name","testsuite")
    self.configuration = configuration
    self.testing = self.configuration.get("testing",False)
    self.modules = self.configuration.get( "modules","intel" )
    self.regression = self.configuration.get("regression",False)
    print(f"Test suite with modules {self.modules}")

    self.nodes_cores = nodes_cores_values(self.configuration)
    self.suites = [ parse_suite( suite ) ]
    # scripts
    dirname = "scriptdir"
    dirpath = self.configuration.get(dirname,os.getcwd()+"/dir."+dirname)
    self.SetSuiteDir(dirname,dirpath)
    with open(self.scriptdir+"/README","w") as readme:
      readme.write("This directory contains automatically generated slurm scripts\n")
    # outputs
    dirname = "outputdir"
    dirpath = self.configuration.get(dirname,os.getcwd()+"/dir."+dirname)
    self.SetSuiteDir(dirname,dirpath)

    print("{}".format(str(self)))
  def SetSuiteDir(self,dirname,dirpath):
    if dirpath[0]!="/":
      print("Directory name for <<{}>> needs to be absolute, not {}"\
            .format(dirname,dirpath))
      raise
    self.__dict__[dirname] = dirpath
    try :
      os.mkdir(dirpath)
      print("first make {}: {}",dirname,dirpath)
    except FileExistsError :
      print("already exists {}: {}",dirname,dirpath)
      pass
  def __str__(self):
    description = f"""
################################################################
Test suite: {self.name}
modules: {self.modules}
nodes/cores: {self.nodes_cores}
regression: {self.regression}
suites: {self.suites}
################################################################
""" 
    return description
  def run(self,testing=False):
      starttime = datetime.date.today()
      logfilename = self.outputdir+"/log-%s.txt" % starttime
      logfile = open(logfilename,"a")
      logfile.write(str(self))
      logfile.write("Test suite run at {}".format(starttime))
      if self.regression:
          regressionfilename = self.outputdir+"/regression-%s.txt" % starttime
          regressionfile = open(regressionfilename,"a")
      else: regressionfile = None
      count = 1
      jobs = []; jobids = []
      queues = Queues(testing=testing,
                      logprinter=lambda x:logfile.write(x+"\n")) ## should probaby be global
      queues.add_queue("development",1)
      queues.add_queue("normal",10)
      queues.add_queue("rtx",4)
      for suite in self.suites:
          for benchmark in suite["apps"]:
              suitename = suite["name"]
              print("="*16,f"{count}: submitting suite={suitename} benchmark={benchmark} at {datetime.datetime.now()}")
              for nnodes,ppn in self.nodes_cores:
                print(".. on %d nodes" % nnodes)
                job = Job(scriptdir=self.scriptdir,outputdir=self.outputdir,
                          nodes=nnodes,ppn=ppn,
                          queue=self.configuration["queue"],
                          dir=suite["dir"],
                          benchmark=benchmark,modules=self.modules,
                          regression=self.regression,regressionfile=regressionfile,
                          runner=suite["runner"],
                          account=self.configuration["account"],user=self.configuration["user"],
                          logfile=logfile,
                          trace=True)
                script_file_name = job.generate_script()
                output_file_name = job.output_file_name

                logfile.write(f"""
%%%%%%%%%%%%%%%%
{count:3}: script={script_file_name}
 logout={output_file_name}
""")
                queues.enqueue(job)
                count += 1
      print(f"See log file: {logfilename}")
      queues.wait_for_jobs()
      print(f"See log file: {logfilename}")
      if self.regression:
          print(f"See regression file: {regressionfilename}")

