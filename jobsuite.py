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

class Job():
    def __init__(self,**kwargs):
        #default values to be overwritten later
        self.suite = "paw"
        self.modules = DefaultModules()
        self.queue = "normal"
        self.nodes = 10
        self.cores = 20
        self.runtime = "00:05:00"
        self.user = "nosuchuser"
        self.account = "MyAccount"
        self.runner = "./"
        self.benchmark = "echo foo"
        self.trace = False
        self.logfile = None # this is the global log
        self.set_has_not_been_submitted()

        tracestring = "Creating job with"
        for key,val in kwargs.items():
            if key=="modules":
                val = " ".join(val)
            tracestring += " {}={}".format(key,val)
            self.__dict__[key] = val

        self.CheckValidDir("scriptdir")
        self.CheckValidDir("outputdir")
        self.output_file_name = self.outputdir+"/"+self.name()+".out%j"

        if self.trace:
            print(tracestring)
        self.script_name = self.scriptdir+"/"+self.name()
    def generate_script(self):
        script_content = str(self)
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
                             self.modules \
                             +"-N"+str(self.nodes)+"-n"+str(self.cores) \
                         ) \
                  )
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
    def status_update(self,status):
        if status!="NS":
            # job was found in slurm, status is PD or R or CG
            self.status = status 
        else:
            # job not found in slurm: either not scheduled, or already finished
            if self.jobid!="1":
                # it has an actual id
                self.status = "POST" # done running
            
    def get_is_running(self):
        return self.jobid!="1" and self.status=="R"
    def get_is_pending(self):
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
    def __str__(self):
      return \
"""#!/bin/bash
#SBATCH -J {}
#SBATCH -o {}
#SBATCH -e {}
#SBATCH -p {}
#SBATCH -t {}
#SBATCH -N {}
#SBATCH -n {}
#SBATCH -A {}

module reset
module load {}

cd {}
{}
""".format(self.name(),
           self.output_file_name,self.output_file_name,
           self.queue,self.runtime,self.nodes,self.cores,
           self.account,self.modules,
           self.outputdir,
           self.runner+self.dir+"/"+self.benchmark,
         )

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
        p = sp.Popen( "cd {} ; ls {}".format( suite["dir"],opt ),\
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
  def nodes_cores_from_cores_list(nodes,cores):
    ## this assumes cores is a list!
    if not isinstance(nodes,list):
      nodes = [ nodes for c in cores ]
    if not len(cores)==len(nodes):
      print("Core and node lists need to be equal length")
      raise Exception()
    return nodes,cores
  def cores_list_from_nodes(nodes,cores):
    if isinstance(nodes,list):
      cores = [ cores for n in nodes ]
    else:
      cores = [ cores ]
    return cores
  def cores_list_from_ppn(nodes,ppn):
    if not isinstance(nodes,list):
      nodes = [ nodes ]
    cores = [ n*ppn for n in nodes ]
    return cores
  nodes = configuration.get("nodes",None)
  if nodes is None:
    print("Node specification always needed, regardless cores")
    raise Exception()
  cores = configuration.get("cores",None)
  ppn   = configuration.get("ppn",None)
  if cores is None and ppn is None:
    print("Configuration needs to specify `cores' or `ppn'")
    raise Exception()
  elif cores is not None:
    ## cores are specified
    if not isinstance(cores,list):
      # cores is scalar, first make list
      cores = cores_list_from_nodes(nodes,cores)
    return nodes_cores_from_cores_list(nodes,cores)
  else:
    ## ppn specified
    ppn  = int(ppn)
    cores = cores_list_from_ppn(nodes,ppn)
    return nodes_cores_from_cores_list(nodes,cores)

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
        nrunning = sum( [ 1 for j in self.jobs if j.get_is_running() ] ) \
                   + sum( [ 1 for j in self.jobs if j.get_is_pending() ] )
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
    def __init__(self,testing=False):
        self.queues = {}; self.testing = testing
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
    self.modules = self.configuration.get( "modules",[ "intel" ] )
    self.nodes,self.cores = nodes_cores_values(self.configuration)
    suite_spec_list = suite
    suite_spec_list.append( "nodes:"+str(self.nodes) )
    self.suites = [ parse_suite( suite_spec_list ) ]
    if not isinstance(self.modules,list):
      print("Modules should be a list, not <<{}>>".format(self.modules))
      raise Exception()
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
    description = """
################################################################
{}: {}
################################################################
""".format("modules",self.modules)
    return description
  def run(self,testing=False):
      logfilename = self.outputdir+"/log.txt"
      with open(logfilename,"a") as logfile:
          logfile.write("Test suite <<{}>> run at <<{}>>\n".\
                        format(self.name,datetime.date.today()))
          count = 1
          jobs = []; jobids = []
          queues = Queues(testing) ## should probaby be global
          queues.add_queue("development",1)
          queues.add_queue("normal",10)
          for suite in self.suites:
              for benchmark in suite["apps"]:
                  print("="*80)
                  print("JOB: {0}".format(count))
                  print("="*80)
                  print("submitting",suite["name"], benchmark)
                  for nnodes,ncores in zip( self.nodes,self.cores ):
                    print(".. on %d nodes" % nnodes)
                    job = Job(scriptdir=self.scriptdir,outputdir=self.outputdir,
                              nodes=nnodes,cores=ncores,queue=self.configuration["queue"],
                              dir=suite["dir"],
                              benchmark=benchmark,modules=self.modules,
                              runner=suite["runner"],
                              account=self.configuration["account"],user=self.configuration["user"],
                              logfile=logfile,
                              trace=True)
                    script_file_name = job.generate_script()
                    output_file_name = job.output_file_name

                    logfile.write(f"""
%%%%%%%%%%%%%%%%
{count:3}: {script_file_name}
     {output_file_name}
""")
                    queues.enqueue(job)
                    count += 1
          print(f"See log file: {logfilename}")
          queues.wait_for_jobs()
          print(f"See log file: {logfilename}")

