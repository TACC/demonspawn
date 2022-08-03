#!/usr/bin/env python
#
# Demonspawn
# a utility for quickly generating a slew of batch jobs
# good for benchmarking, regression testing, and such
#
# Victor Eijkhout
# copyright 2020-2022
#
# version 0.4, see the Readme for details
#
# jobsuite.py : classes for suites and jobs
#

import copy
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

def macro_value( m,macros ):
    if m in macros.keys():
        return str(macros[m])
    elif m in os.environ.keys():
        return os.environ[m]
    else:
        return m

def macros_substitute(line,macros):
    print(f"macro substitution in <<{line}>>")
    subline = line
    while True:
        if m_match := re.search(r'\%\[([^[]+)\]',subline):
            macro = m_match.groups()[0]
            print(f".. found macro <<{macro}>>")
            value = macro_value(macro,macros)
            subline = re.sub(r'\%\['+macro+r'\]',value,subline)
            print(f".. giving <<{subline}>>")
        else: break
    # for m in macros.keys():
    #     m_search = r'\%\[{}\]'.format(m)
    #     if re.search(m_search,line):
    #         replacement_text = macro_value( m,macros )
    #         if m=="modules":
    #             replacement_text = module_string(replacement_text)
    #         subline = re.sub( m_search, replacement_text, subline )
    return subline

##
## files may not be unique per job
## so we need central bookkeeping
## this is a singleton class
##
class SpawnFiles():
  instance = None
  class __spawnfiles():
    def __init__(self):
      self.file_handles = {}; self.file_names = {}
      self.outputdir = None
      self.debug = False
    def debug_print(self,msg):
      if self.debug:
        print(msg)
        if logfile := self.get_by_key("logfile"):
          logfile.write(msg+"\n")
    def setoutputdir(self,dir):
      if not os.path.exists(dir):
        self.debug_print(f"Creating output directory <<{dir}>>")
        os.mkdir(dir)
      else:
        self.debug_print(f"Re-using old output directory <<{dir}>>")
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
        self.debug_print(f"Making dir <<{filedir}>>")
      except FileExistsError :
        self.debug_print(f"Directory <<{filedir}>> already exists")
        pass
      return filedir
    def open(self,fil,key=None,dir=None,subdir=None,new=False):
      ### return handle, dirname, filename, key
      filedir = self.ensurefiledir(dir,subdir)
      filename = fil
      if not key: key = filename
      self.debug_print(f"Opening dir={filedir} file={filename} key={key}")
      fullname = f"{filedir}/{filename}"
      if key not in self.file_handles.keys():
        h = open(fullname,"w")
        self.file_handles[key] = h; self.file_names[key] = fullname
        return h,filedir,filename,key
      elif new:
        raise Exception(f"Key <<{key}>> File <<{fullname}>> already exists")
      else:
        return self.file_handles[key],filedir,filename,key
    def open_new(self,fil,key=None,dir=None,subdir=None):
      self.debug_print(f"Open new <{fil}>> at <<{dir}/{subdir}>>")
      return self.open(fil,key=key,dir=dir,subdir=subdir,new=True)
    def get(self,id):
      return self.file_handles[id]
    def close_by_path(self,path):
      for fk in self.file_names.keys():
        if self.file_names[fk]==path:
          self.file_handles[fk].close()
    def close_files(self,keys):
        for k in keys:
            if k is None or k not in self.file_handles.keys():
                self.debug_print(f"Suspicious attempt to close {k}")
            else:
                self.debug_print(f"closing job: {k} => {self.file_names[k]}")
                self.file_handles[k].close()
            self.file_handles.pop(k,None)
            self.file_names.pop(k,None)
    def __del__(self):
      for f in self.file_handles.keys():
        self.debug_print(f"closing file: {f}")
        self.file_handles[f].close()
  def __new__(cls):
    if not SpawnFiles.instance:
      SpawnFiles.instance = SpawnFiles.__spawnfiles()
    return SpawnFiles.instance
  def __getattr__(self,attr):
    return self.instance.__getattr__(attr)

def regression_test_dict(regression):
    ## split `regression' clause, return dict
    rtest = {}
    for kv in regression.split():
        if not re.search(":",kv):
            print(f"ill-formed regression clause <<{kv}>>")
            continue
        k,v = kv.split(":")
        if k=="label":
            if k not in rtest.keys():
                rtest[k] = []
            rtest[k].append(v)
        else:
            rtest[k] = v
    return rtest

class Job():
    def __init__(self,configuration,**kwargs):

        self.configuration = configuration
        for key in [ "account", "queue", "sbatch", "user", "time", ]:
            self.__dict__[key] = self.configuration[key]

        self.suite = "paw"
        self.nodes = 1; self.cores = 10; self.ppn = 1; self.threads = 0
        self.unique_name = None

        self.time = "01:00:00"
        self.runner = "./"
        self.trace = False; self.debug = False
        self.logfile,_,_,_ = SpawnFiles().open("logfile")
        self.macros = copy.copy( kwargs.pop("macros",{}) )
        self.set_has_not_been_submitted()

        tracestring = ""
        forbidden = [ "logfile","macros", ]
        for key,val in kwargs.items():
            if key in forbidden:
              continue
            tracestring += " {}={}".format(key,val)
            self.__dict__[key] = val
            self.macros[key] = val

        self.cores = int( self.macros["nodes"] ) * int( self.macros["ppn"] )
        self.macros["cores"] = self.cores
        if not self.unique_name: raise Exception(f"Missing key: unique_name")
        tracestring = f"Creating job <<{self.unique_name}>> with <<{tracestring}>>"

        script_file_name = f"{self.unique_name}.script"
        script_file_handle,scriptdir,script_file_name,_ \
          = SpawnFiles().open_new( script_file_name,subdir="scripts" )
        self.script_file_name = f"{scriptdir}/{script_file_name}"
        self.slurm_output_file_name = f"{self.outputdir}/{self.unique_name}.out"
        script_file_handle.write(self.script_contents()+"\n")
        script_file_handle.close()
        self.logfile.write(f"""
%%%%%%%%%%%%%%%%
{self.count:3}: script={self.script_file_name}
 logout={self.slurm_output_file_name}
""")
        if self.trace:
            print(f"Written job file <<{self.script_file_name}>> for <<{self.unique_name}>>")
        if self.regression and not self.global_regression_handle:
            raise Exception("Trying to create regression job without global regressionfile")
        ## if self.trace: print(tracestring)
        self.logwrite(tracestring)
    def logwrite(self,msg):
        if self.logfile:
            self.logfile.write(msg+"\n")
    def modules_load_line(self):
        if self.modules!="default":
          return f"""## custom modules
module reset
module load {self.modules}
"""
        else: return ""
    def omp_thread_spec(self):
        if self.threads==0:
          return ""
        else:
          if self.threads>0:
            threadcount = self.threads
          else:
            threadcount = "$(( SLURM_CPUS_ON_NODE / SLURM_NTASKS * SLURM_NNODES ))"
          return f"""## OpenMP thread specification
threadcount={threadcount}
if [ $threadcount -lt 1 ] ; then threadcount=1 ; fi
export OMP_NUM_THREADS=$threadcount
export OMP_PROC_BIND=true
"""
    def script_contents(self):
        bench_program = self.runner+self.programdir+"/"+self.unique_name
        module_spec = self.modules_load_line()
        thread_spec = self.omp_thread_spec()
        sbatch = ""
        for s in self.sbatch:
          sbatch += f"""#SBATCH {s}
"""
        return  \
f"""#!/bin/bash
#SBATCH -J {self.unique_name}
#SBATCH -o {self.slurm_output_file_name}
#SBATCH -e {self.slurm_output_file_name}
#SBATCH -p {self.queue}
#SBATCH -t {self.time}
#SBATCH -N {self.nodes}
#SBATCH --tasks-per-node {self.ppn}
#SBATCH -A {self.account}
{sbatch}

{module_spec}{thread_spec}
cd {self.outputdir}
program={self.programdir}/{self.program_name}
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
        return f"N{self.nodes}-ppn{self.ppn}{thread_spec}"
    def __str__(self):
        return f"{self.unique_name} N={self.nodes} cores={self.cores} threads={self.threads} regression={self.regression}"
    def submit(self):
        if self.trace:
            print(f"sbatch: {self.script_file_name}")
        p = sp.Popen(["sbatch",self.script_file_name],stdout=sp.PIPE)
        submitted = False
        for line in io.TextIOWrapper(p.stdout, encoding="utf-8"):
            line = line.strip()
            if False and ( self.trace or self.debug ):
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
                if not self.done_running():
                    self.set_done_running()
    def is_running(self):
        return self.jobid!="1" and self.status=="R"
    def is_pending(self):
        return self.jobid!="1" and self.status=="PD"
    def done_running(self):
        return self.status=="POST"
    def set_done_running(self):
        self.status = "POST" # done running
        ## filter crud from output file
        with open(self.slurm_output_file_name,"r") as slurm_out:
            lines = slurm_out.readlines()
        with open(self.slurm_output_file_name,"w") as slurm_out:
            for line in lines:
                if not re.match("TACC",line):
                    slurm_out.write(line)
        ## regression
        if self.regression:
            self.do_regression()
    def get_status(self):
        id = self.jobid
        # squeue -j 6137988 -h -o "%t"
        p = sp.Popen(["squeue","-j",id,"-h","-o","%t"],stdout=sp.PIPE)
        status = "CD"
        for status in io.TextIOWrapper(p.stdout, encoding="utf-8"):
            status = status.strip()
        return status
    def regression_line_pick_field(self,line,rtest):
        if "field" in rtest.keys():
            fields = line.split(); ifield = rtest["field"]
            try:
                return fields[ int(ifield)-1 ]
            except:
                error = f"ERROR Can not extract field {ifield} from <<{line}>>"
                print(error)
                return None
        else: return line
    def regression_label_prepend(self,string,rtest):
        if "label" in rtest.keys():
            labels = ""
            for l in rtest["label"]:
                if labels=="":
                    labels = macro_value( l, self.macros )
                else:
                    labels = labels+" "+macro_value( l, self.macros )
            return f"{labels} {string}"
        else: return string
    def regression_grep(self,output_file,rtest):
        unique_name = self.unique_name
        greptext = re.sub("_"," ",rtest["grep"])
        found = False; rkey = None
        for line in output_file:
            line = line.strip()
            if re.search(greptext,line):
                found = True
                string = self.regression_line_pick_field(line,rtest)
                string = self.regression_label_prepend(string,rtest)
                self.logfile.write(f"File: {self.unique_name}\n{string}\n")
                self.global_regression_handle.write(f"File: {self.unique_name} Result: {string}\n")
                rfile,_,_,rkey = SpawnFiles().open\
                            (f"{self.unique_name}.out",subdir="regression",key=f"r-{unique_name}")
                rfile.write(f"{string}\n")
                break
        if not found:
            self.logfile.write\
              (f"{self.unique_name}: regression failed to find <<{greptext}>>\n")
            self.global_regression_handle.write\
              (f"{self.unique_name}: regression failed to find <<{greptext}>>\n")
        return rkey
    def regression_line(self,output_file,rtest):
        what_line = rtest["line"]
        for line in output_file:
            the_line = line.strip()
            if what_line=="first":
                break;
        return_value = self.regression_line_pick_field(the_line,rtest)
        return_value = self.regression_label_prepend(return_value,rtest)
        return return_value
    def apply_regression(self,rtest,filename):
        ## get regression result from filename
        rreturn = None; regger = None
        if "line" in rtest.keys():
            regger = self.regression_line
        elif "grep" in rtest.keys():
            regger = self.regression_grep
        if regger:
            try:
                with open(filename,"r") as output_file:
                    rreturn = regger(output_file,rtest)
            except FileNotFoundError as e :
                print(f"Could not open file for regression: <<{e}>>")
        return rreturn
    def do_regression(self,filename=None):
        ## regress on `filename', writing private and global file
        if not filename: filename = self.slurm_output_file_name
        self.logwrite(f"Doing regression <<{self.regression}>> on job {self.unique_name} from <<{filename}>>")
        print(f"Doing regression on {filename}")
        if self.regression is None or self.regression=="none": return None
        rtest = regression_test_dict( self.regression )
        ## rtest = self.get_regression_tests()
        rreturn = self.apply_regression(rtest,filename)
        if not rreturn: rreturn = "REGRESSION ERROR"
        rfilekey = None
        self.logwrite(f".. done regression on {self.unique_name}, giving: {rreturn}")
        self.global_regression_handle.write(rreturn+"\n")
        rfilename = f"{self.unique_name}.txt"
        rfilehandle,_,_,rfilekey \
          = SpawnFiles().open(rfilename,subdir="regression",new=True)
        self.logwrite(f"writing regression result <<{rreturn}>> to global and <<{rfilename}>>")
        rfilehandle.write(rreturn+"\n")
        return rfilekey

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
        self.limit = int(limit)
    def enqueue(self,j):
        self.jobs.append(j)
        qrunning = running_jobids(self.name,j.user)
        if len(qrunning)<self.limit:
            ## this may throw an exception if QoS exceeded
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
                try :
                    j.submit()
                    nslots -= 1
                except :
                    print(f"Failed to submit")
                    self.jobs.remove(j)
                    continue
    def how_many_unfinished(self):
        return sum( [ 1 for j in self.jobs if not j.done_running() ] )
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
            if name in self.queues.keys():
              self.queues[name].set_limit(limit)
            else:
              self.queues[name] = Queue(name,limit)
        def set_limit(self,name,limit):
            if not name in self.queues.keys():
                raise Exception(f"Can only set limit for existing queue, not: {name}")
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
  def __init__(self,suite_spec,configuration):

    self.logfile        = SpawnFiles().get("logfile")
    self.starttime      = configuration.get("date","00-00-00")

    self.name = configuration.pop("name","testsuite")
    self.regression = configuration.get( "regression",False )
    if self.regression in ["none", "None"]:
      self.regression = None

    env = configuration.get("env",[])
    for e in env:
      name,value = e.split(" ",1)
      print(f"Setting environment variable <<{name}>> to <<{value}>>")
      os.environ[name] = value

    self.configuration = configuration
    self.testing = self.configuration.get( "testing",False )
    self.modules = self.configuration.get( "modules",None )
    print(f"Test suite with modules {self.modules}")

    self.nodes_cores_threads = nodes_cores_threads_values(self.configuration)
    self.suites = [ parse_suite( suite_spec ) ]
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
  def tracemsg(self,msg):
      print(msg)
      self.logfile.write(msg+"\n")
  def run(self,**kwargs):
      testing = kwargs.get("testing",False)
      debug = kwargs.get("debug",False)
      submit = kwargs.get("submit",True)

      count = 1
      jobs = []; jobids = []
      ## for now all output goes in the same directory
      outputdir = SpawnFiles().ensurefiledir(subdir="output")
      jobnames = []; regressionfiles = []
      ## iterate over suites
      ## I think this only does one iteration.
      for suite in self.suites:
          suitename = suite["name"]
          print(f"Suitename: {suitename}")
          regressionfilename = f"regression-{suitename}.txt"
          if self.regression:
              global_regression_handle,_,_,k = SpawnFiles().open_new( f"{regressionfilename}" )
          else: global_regression_handle = None
          self.tracemsg(f"Test suite {self.name} run at {self.starttime}")
          self.logfile.write(str(self))
          for benchmark in suite["apps"]:
              self.tracemsg("="*16+"\n"+f"{count}: submitting suite=<<{suitename}>> benchmark=<<{benchmark}>>")
              for nodes,ppn,threads in self.nodes_cores_threads:
                self.tracemsg(f" .. N={nodes} ppn={ppn} threads={threads}")
                unique_name = f"{suitename}-{benchmark}-{nodes}-{ppn}-{threads}"
                if unique_name in jobnames:
                    raise Exception(f"Job name conflict: {unique_name}")
                else:
                    jobnames.append(unique_name)
                job = Job(self.configuration,
                          program_name=benchmark,unique_name=unique_name,
                          outputdir=outputdir,
                          nodes=nodes,ppn=ppn,threads=threads,
                          programdir=suite["dir"],
                          modules=self.modules,
                          regression=self.regression,global_regression_handle=global_regression_handle,
                          runner=suite["runner"],
                          macros=self.configuration,
                          count=count,trace=True,
                        )
                if submit:
                    Queues().enqueue(job)
                elif job.regression:
                    regression_key = job.do_regression()
                    regressionfiles.append( regression_key )
                count += 1
      if submit:
          Queues().wait_for_jobs()
      else:
          SpawnFiles().close_files( regressionfiles )
      if cdir := self.configuration["comparedir"]:
          print("All jobs finished, only regression comparison left to do")
          cdir = cdir+"/regression"
          odir = self.configuration["outputdir"]+"/regression"
          if self.regression: ## we can have both regression and none in the same job
              self.regression_compare(suitename,cdir,odir)
  def regression_compare(self,suitename,cdir,odir):
        rtest = regression_test_dict( self.regression )
        comparison,_,_,_ = SpawnFiles().open_new(f"regression_compare-{suitename}")
        majorly_off = []
        for ofile in [ f for f in os.listdir(odir) 
                       if os.path.isfile( os.path.join( odir,f ) ) ]:
            opath = os.path.join( odir,ofile )
            SpawnFiles().close_by_path(opath)
            cpath = os.path.join( cdir,ofile )
            if os.path.isfile( cpath ):
                comparison.write(f"Comparing: output={opath} compare={cpath}\n")
                with open( opath,"r" ) as ohandle:
                    oline = ohandle.readline().strip()
                with open( cpath,"r" ) as chandle:
                    cline = chandle.readline().strip()
                dev = ""
                if "margin" in rtest.keys():
                    margin = rtest["margin"]
                    if perc := re.match(r'([0-1]+)p.*',margin):
                        dev = float( perc.groups()[0] )/100
                        violate = False
                        try :
                            oval = float( oline ); cval = float( cline )
                            violate = (oval-cval)/cval>dev or (cval-oval)/oval>dev
                            if violate:
                                dev = f", outside {dev} margin"
                            else:
                                dev = f", inside {dev} margin"
                        except:
                            dev = f", margin comparison failed"
                    report = f"Output: {oline}, compare: {cline}{dev}"
                    if violate: majorly_off.append( f"{opath} {report}" )
                else: report = f"Output: {oline}, compare: {cline}"
                comparison.write( f"{report}\n" )
        if len(majorly_off)>0:
            comparison.write( "================ Major violations ================\n" )
            for m in majorly_off:
                comparison.write( m+"\n" )












































































































































































































































































































































































































































