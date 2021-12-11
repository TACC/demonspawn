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

##
## files may not be unique per job
## so we need central bookkeeping
## this is a singleton class
##
class SpawnFiles():
  instance = None
  class __spawnfiles():
    def __init__(self):
      self.files = {}
      self.outputdir = None
      self.debug = False
    def setoutputdir(self,dir):
      try:
        os.mkdir(dir)
      except:
        raise Exception(f"Could not make dir <<{dir}>>") 
      self.outputdir = dir
    def ensurefiledir(self,dir=None,subdir=None):
      if dir:
        filedir = dir
      else:
        filedir = self.outputdir
      if not filedir:
        raise Exception("No output dir specified, in call or configuration")
      if subdir: filedir=f"{filedir}/{subdir}"
      try :
        os.mkdir( filedir )
        if self.debug: print(f"Making dir <<{filedir}>>")
      except FileExistsError :
        if self.debug: print(f"Directory <<{filedir}>> already exists")
        pass
      return filedir
    def open(self,fil,key=None,dir=None,subdir=None,new=False):
      print(f"Open <{fil}>> at <<{dir}/{subdir}>> new: <<{new}>>")
      filedir = self.ensurefiledir(dir,subdir)
      filename = fil
      if not key: key = filename
      if self.debug: print(f"Opening dir={filedir} file={filename} key={key}")
      fullname = f"{filedir}/{filename}"
      if key not in self.files.keys():
        h = open(fullname,"w")
        self.files[key] = h
        return h,filedir,filename
      elif new:
        raise Exception(f"Key <<{key}>> File <<{fullname}>> already exists")
      else:
        return self.files[key],filedir,filename
    def open_new(self,fil,key=None,dir=None,subdir=None):
      if self.debug: print(f"Open new <{fil}>> at <<{dir}/{subdir}>>")
      return self.open(fil,key=key,dir=dir,subdir=subdir,new=True)
    def set(self,id,fil,dir=None):
      raise Exception("do not call set method")
      h,_ = self.open(fil,dir)
      self.files[id] = h
    def get(self,id):
      return self.files[id]
    def __del__(self):
      for f in self.files.keys():
        if self.debug: print(f"closing file: {f}")
        self.files[f].close()
  def __new__(cls):
    if not SpawnFiles.instance:
      SpawnFiles.instance = SpawnFiles.__spawnfiles()
    return SpawnFiles.instance
  def __getattr__(self,attr):
    return self.instance.__getattr__(attr)

class Job():
    def __init__(self,**kwargs):
        #default values to be overwritten later
        self.suite = "paw"
        self.queue = "normal"
        self.nodes = 1; self.cores = 10; self.threads = 0
        self.runtime = "00:05:00"
        self.user = "nosuchuser"
        self.account = "MyAccount"
        self.runner = "./"
        self.benchmark = "bench"
        self.trace = False; self.debug = False
        self.logfile,_,_ = SpawnFiles().open("logfile")
        self.regressionfile = None
        self.set_has_not_been_submitted()

        tracestring = ""
        for key,val in kwargs.items():
          if key in ["logfile"] :
            raise Exception(f"Forbidden keyword <<{key}>>")
          tracestring += " {}={}".format(key,val)
          self.__dict__[key] = val
        tracestring = f"Creating job <<{self.name()}>> with <<{tracestring}>>"

        script_file_name = f"{self.name()}.script"
        print(f"script file name: {script_file_name}")
        script_file_handle,scriptdir,script_file_name \
          = SpawnFiles().open_new( script_file_name,subdir="scripts" )
        self.script_file_name = f"{scriptdir}/{script_file_name}"
        # we are assuming that the files wind up in a unique directory
        # so we don't need the job number in the name
        self.outputdir = SpawnFiles().ensurefiledir(subdir="output")
        self.slurm_output_file_name = f"{self.outputdir}/{self.name()}.out" # .out%j"
        script_file_handle.write(self.script_contents()+"\n")
        script_file_handle.close()
        self.logfile.write(f"""
%%%%%%%%%%%%%%%%
{self.count:3}: script={self.script_file_name}
 logout={self.slurm_output_file_name}
""")
        if self.trace:
            print(f"Written job file <<{self.script_file_name}>> for <<{self.benchmark}>>")
        if self.regression and not self.regressionfile:
            print("Trying to create regression job without regressionfile"); sys.exit(1)
        if self.trace: print(tracestring)
        if self.logfile: self.logfile.write(tracestring+"\n")
    def script_contents(self):
        bench_program = self.runner+self.programdir+"/"+self.benchmark
        if self.modules!="default":
          moduleset = f"""## custom modules
module reset
module load {self.modules}
"""
        else: moduleset = ""
        if self.threads!=0:
          if self.threads>0:
            threadcount = self.threads
          else:
            threadcount = "$(( SLURM_CPUS_ON_NODE / SLURM_NTASKS * SLURM_NNODES ))"
          threadset = f"""## OpenMP thread specification
threadcount={threadcount}
if [ $threadcount -lt 1 ] ; then threadcount=1 ; fi
export OMP_NUM_THREADS=$threadcount
export OMP_PROC_BIND=true
"""
        else: threadset = ""
        return  \
f"""#!/bin/bash
#SBATCH -J {self.name()}
#SBATCH -o {self.slurm_output_file_name}
#SBATCH -e {self.slurm_output_file_name}
#SBATCH -p {self.queue}
#SBATCH -t {self.runtime}
#SBATCH -N {self.nodes}
#SBATCH --tasks-per-node {self.cores}
#SBATCH -A {self.account}

{moduleset}{threadset}
cd {self.outputdir}
program={self.programdir}/{self.benchmark}
if [ ! -f "$program" ] ; then 
  echo "Program does not exist: $program"
  exit 1
fi
{self.runner}$program
"""
    def nodespec(self):
        if self.threads>0:
          thread_spec = f"-t{self.threads}"
        elif self.threads<0:
          thread_spec = f"-tx"
        else:
          thread_spec = ""
        return f"N{self.nodes}-ppn{self.cores}{thread_spec}"
    def name(self):
        return f"{self.benchmark}-{self.nodespec()}"
    def __str__(self):
        return f"{self.benchmark} N={self.nodes} cores={self.cores} threads={self.threads} regression={self.regression}"
    def submit(self):
        if self.trace:
            print(f"sbatch: {self.script_file_name}")
        p = sp.Popen(["sbatch",self.script_file_name],stdout=sp.PIPE)
        submitted = False
        for line in io.TextIOWrapper(p.stdout, encoding="utf-8"):
            line = line.strip()
            if self.trace or self.debug:
                print( line )
            self.logfile.write(line+"\n")
            submitted = re.search("(Submitted.* )([0-9]+)",line)
            if submitted:
                id = submitted.groups()[1]
                self.set_has_been_submitted(id)
                return self.jobid
        if not submitted:
          raise Exception(f"Failure to submit <<{self.script_file_name}>>")
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
            self.logfile.write(f", output file name set to {self.slurm_output_file_name}")
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
                  if self.regression:
                    if self.logfile:
                      self.logfile.write(f"Doing regression <<{self.regression}>> on job {self.name()} to <<{self.slurm_output_file_name}>> and general regression file\n")
                    self.do_regression(self.slurm_output_file_name)
                    self.logfile.write(f".. done regression\n")
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
    def do_regression(self,filename):
        print(f"Doing regression on {filename}")
        rtest = {}
        for kv in self.regression.split():
            if not re.search(":",kv):
                print(f"ill-formed regression clause <<{kv}>>")
                continue
            k,v = kv.split(":")
            rtest[k] = v
        if "grep" in rtest.keys():
          greptext = re.sub("_"," ",rtest["grep"])
          try:
            with open(filename,"r") as output_file:
              found = False
              for line in output_file:
                line = line.strip()
                if re.search(greptext,line):
                  found = True
                  if "field" in rtest.keys():
                    fields = line.split(); field = fields[ int(rtest["field"])-1 ]
                    self.logfile.write(f"File: {self.name()}\n{field}\n")
                    self.regressionfile.write(f"File: {self.name()}\n{field}\n")
                  else:
                    self.logfile.write(f"File: {self.name()}\n{line}\n")
                    self.regressionfile.write(f"File: {self.name()}\n{line}\n")
              if not found:
                self.logfile.write\
                  (f"{self.name()}: regression failed to find <<{greptext}>>\n")
                self.regressionfile.write\
                  (f"{self.name()}: regression failed to find <<{greptext}>>\n")
          except FileNotFoundError as e :
            print(f"Could not open file for regression: <<{e}>>")
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
def nodes_cores_threads_values(configuration):
  def str2set(s):
    if re.search(",",s):
      s = [ int(p) for p in s.split(",") ]
    elif re.search(":",s):
      print("colon notation not yet supported"); raise Exception()
    else:
      s = [ int(s) ]
    return s    
  nodes = configuration.get("nodes","1")
  cores = configuration.get("cores",None)
  if not cores is None:
    print("Cores keyword not supported"); raise Exception()
  ppn   = configuration.get("ppn","1")
  threads = configuration.get("threads","0")

  ## nodes
  print(f"""Parallel configuration:
nodes: {nodes}
ppn: {ppn}
threads: {threads}
""")
  nodes = str2set(nodes); ppn = str2set(ppn); threads = str2set(threads)
  
  ##
  ## node/core combinations
  ##
  nodes_cores_threads = [ [ [ [n,p,t] 
                      for n in nodes ] 
                    for p in ppn ] 
                  for t in threads ]
  nodes_cores_threads = [ n for npt in nodes_cores_threads
                          for np in npt for n in np ] 
  print("nodes_cores_threads:",nodes_cores_threads)
  return nodes_cores_threads

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
        self.name = name; self.jobs = []; self.set_limit(limit); self.debug = False
    def set_limit(self,limit):
        self.limit = limit
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
        if self.debug: 
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
    instance = None
    class __queues():
        def __init__(self,**kwargs):
            self.queues = {}
            self.testing = kwargs.get("testing",False)
            self.debug = False
            self.logprinter = kwargs.get( "logprinter",lambda x:print("log message:",x) )
        def add_queue(self,name,limit):
            self.queues[name] = Queue(name,limit)
        def set_limit(self,name,limit):
            self.queues[name].set_limit(limit)
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
                    time.sleep(10)
                self.logprinter("Done all jobs")
        def update_jobs_status(self):
            #
            # ids of all jobs; ids may be 1 if not started, or valid but already finished
            #
            ids = reduce( lambda x,y:x+y,
                          [ q.ids() for q in self.queues.values() ] )
            #print("All ids: <<{}>>".format(ids))
            id_string = ",".join( ids )
            if self.debug: print("Getting status for",id_string)
            #
            # get the status for all jobs. some of them may not yet be running, or finished
            #
            p = sp.Popen(["squeue","-j",id_string,"-h","-o","%A %t"],stdout=sp.PIPE)
            status_dict = { id:"NS" for id in ids }; running = []; pending = []
            for status in io.TextIOWrapper(p.stdout, encoding="utf-8"):
                id,stat = status.strip().split()
                if self.debug: print("Job {} status {}".format(id,stat))
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
    def __new__(cls):
      if not Queues.instance:
        Queues.instance = Queues.__queues()
      return Queues.instance
    def __getattr__(self,attr):
      return self.instance.__getattr__(attr)

class TestSuite():
  def __init__(self,suite,configuration):
    ## this needs to come from the `suite' list
    self.logfile        = SpawnFiles().get("logfile")
    self.starttime      = configuration.get("date","00-00-00")

    self.name = configuration.pop("name","testsuite")
    self.regression = configuration.get( "regression",False )

    self.configuration = configuration
    self.testing = self.configuration.get( "testing",False )
    self.modules = self.configuration.get( "modules",None )
    print(f"Test suite with modules {self.modules}")

    self.nodes_cores_threads = nodes_cores_threads_values(self.configuration)
    self.suites = [ parse_suite( suite ) ]
    print("{}".format(str(self)))
  def __str__(self):
    description = f"""
################################################################
Test suite: {self.name}
modules: {self.modules}
nodes/cores/threads: {self.nodes_cores_threads}
regression: {self.regression}
suites: {self.suites}
################################################################
""" 
    return description
  def type_dir(self,typ,dir=None):
    if dir:
      return f"{typ}-{dir}"
    else:
      return f"{typ}"
  def run(self,**kwargs):
      testing = kwargs.get("testing",False)
      debug = kwargs.get("debug",False)
      submit = kwargs.get("submit",True)

      count = 1
      jobs = []; jobids = []
      # should queues be global?
      queuespec = self.configuration["queue"].split()
      jobqueue = queuespec[0]
      if len(queuespec)>1:
        queuespec = queuespec[1:]      
        if limit:=re.match(r'limit:([0-9]+)',queuespec[0]):
          limit = int( limit.groups()[0] )
          Queues().set_limit(jobqueue,limit)
      for suite in self.suites:
          suitename = suite["name"]
          print(f"Suitename: {suitename}")
          if self.regression:
            regressionfile,_,_ \
              = SpawnFiles().open_new( f"regression-{suitename}.txt" )
          self.logfile.write(f"Test suite {self.name} run at {self.starttime}\n")
          self.logfile.write(str(self))
          for benchmark in suite["apps"]:
              print("="*16,f"{count}: submitting suite={suitename} benchmark={benchmark} at {datetime.datetime.now()}")
              self.logfile.write(f"{count}: submitting suite={suitename} benchmark={benchmark}")
              for nodes,cores,threads in self.nodes_cores_threads:
                print(".. on %d nodes" % nodes)
                self.logfile.write(f".. N={nodes} ppn={cores} threads={threads}")
                job = Job(benchmark=benchmark,
                          nodes=nodes,cores=cores,threads=threads,
                          queue=jobqueue,
                          programdir=suite["dir"],
                          modules=self.modules,
                          regression=self.regression,regressionfile=regressionfile,
                          runner=suite["runner"],
                          account=self.configuration["account"],user=self.configuration["user"],
                          count=count,trace=True)
                if submit:
                  Queues().enqueue(job)
                count += 1
      if submit:
        Queues().wait_for_jobs()
