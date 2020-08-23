#!/usr/bin/env python
#
# W. Cyrus Proctor
# 2015-10-24
# 2015-10-08
# Victor Eijkhout
# 2020-03-09

#--------------------------------------------------------------------------------
# System
#from __future__ import print_function
import datetime
import io
import os
import re
import sys
import subprocess as sp
import time


#--------------------------------------------------------------------------------
# Local
from jobsuite import *

# import benchmark_list        as bl
# import module_list           as ml
# import spawn_real_time_child as srtc
# import dateortime            as dtime
# import starter               as st


#--------------------------------------------------------------------------------
# Globals
sl       = "/"
sentinel = object()

#--------------------------------------------------------------------------------
#--------------------------------------------------------------------------------
#--------------------------------------------------------------------------------

def read_batch_template(filename):
  """
     Read in Slurm batch submit template and return as a string.
  """
  return open(filename, "r").read()


#--------------------------------------------------------------------------------

def fill_template(template   ,\
                  suite      ,\
                  compiler   ,\
                  benchmark  ,\
                  queue      ,\
                  time       ,\
                  nodes      ,\
                  nprocs     ,\
                  nodelist   ,\
                  acct       ,\
                  threads    ,\
                  starter    ,\
                  launch     ,\
                  runme      ):
  """
     Given input arguments, return a filled out batch submit template run name.
  """
  name    = "n" + str(nprocs) + "_N" + str(nodes) + "_t" + str(threads)
  batch   = template
  batch   = batch.replace("<date>"       , str(dtime.datetime_to_string()) ) # Add in date and time
  batch   = batch.replace("<suite>"      , str(suite)                      ) # Benchmark suite to be run
  batch   = batch.replace("<compiler>"   , str(compiler)                   ) # Compiler user to build benchmark suite
  batch   = batch.replace("<benchmark>"  , str(benchmark)                  ) # Benchmark binary to be run
  batch   = batch.replace("<name>"       , str(name)                       ) # Unique run name suffix
  batch   = batch.replace("<queue>"      , str(queue)                      ) # Slurm queue to run in
  batch   = batch.replace("<time>"       , str(time)                       ) # Slurm wall clock time limit
  batch   = batch.replace("<nodes>"      , str(nodes)                      ) # Number of nodes
  batch   = batch.replace("<nprocs>"     , str(nprocs)                     ) # Number of mpi processes
  if nodelist: 
    batch = batch.replace("<node-list>"  , "#SBATCH --nodelist=" + nodelist) # Fixed nodelist for repeatability
  else:
    batch = batch.replace("<node-list>"  , ""                              )
  batch   = batch.replace("<acct>"       , str(acct)                       ) # Account to charge
  batch   = batch.replace("<module-str>" , str(getattr(ml, compiler)())    ) # Runtime Lmod module environment
  batch   = batch.replace("<nprocs2>"    , str(int(nprocs/2.0))            ) # Number of mpi processes / 2
  batch   = batch.replace("<threads>"    , str(threads)                    ) # Number of threads
  batch   = batch.replace("<starter>"    , str(starter)                    ) # Starter command to be used (srun, mpirun, etc.)
  batch   = batch.replace("<launch>"     , str(launch)                     ) # Launch directory
  batch   = batch.replace("<runme>"      , str(runme)                      ) # Runme script
  
  return batch, name


#--------------------------------------------------------------------------------

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
    self.account = "MyAccount"
    self.runner = "./"
    self.benchmark = "echo foo"
    self.trace = False

    tracestring = "Creating job with"
    for key,val in kwargs.items():
      if key=="modules":
        val = " ".join(val)
      tracestring += " {}={}".format(key,val)
      self.__dict__[key] = val

    self.CheckValidDir("scriptdir")
    self.CheckValidDir("outputdir")

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
    self.jobid = 0
    for line in io.TextIOWrapper(p.stdout, encoding="utf-8"):
      line = line.strip()
      if self.trace:
        print( line )
      if logfile is not None:
        logfile.write(line+"\n")
      submitted = re.search("(Submitted.* )([0-9]+)",line)
      if submitted:
        self.jobid = submitted.groups()[1]
        return self.jobid
    return 0
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
           self.outputdir+"/"+self.name()+".out%j",
           self.outputdir+"/"+self.name()+".out%j",
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


def wait_for_jobs( jobs ):
  while True:
    running = []; pending = []
    for j in jobs:
      id = j.jobid
      status = j.get_status()
      if status=="R":
        running.append(id)
      elif status=="PD":
        pending.append(id)
    print(f"Running: {running} Pending: {pending}")
    if len(running)+len(pending)==0:
      break
    time.sleep(1)

run_user = "eijkhout"
def parse_configuration(filename):
  options = {}
  suites = []
  with open(filename,"r") as configuration:
    for specline in configuration:
      if re.match("#",specline):
        continue
      fields = specline.split()
      if len(fields)==2:
        key,value = fields
        if key=="nodes":
          try :
            options[key] = [ int(i) for i in value.split(":") ]
          except:
            print("Could not parse node specification <<{}>>".format(value))
            raise
        else:
          options[key] = value
        print("setting key={} to value={}".format(key,value))
      else:
        key = fields[0]; value = fields[1:]
        if key=="suite":
          s = TestSuite( value,options )
          suites.append(s)
          print("defining suite <<{}>>".format(s))
        else:
          options[key] = value
    options["suites"] = suites
    return options

def print_configuration(confdict):
  print("""
################ Configuration ################
Running as:
################################
""".format(str(confdict)))

def test_job():
  print("""================

Test job in main

================""")
  job = Job(script="/bin/true")
  id = job.submit()
  print("""Job script
================
{}
================
submitted as {}""".format(str(job),id))

if __name__ == "__main__":
  args = sys.argv[1:]
  configuration = {}
  testing = False                      
  while len(args)>0:
    if args[0]=="-h":
      print("Usage: python3 batch.py [ -h ] [ --test ] [ -c configuration ]")
      sys.exit(0)
    elif args[0]=="-c":
      args = args[1:]
      if len(args)==0 or re.match("^-",args[0]):
        print("ERROR: expected name of configuration file")
        sys.exit(1)
      configuration_file = args[0]
      configuration = parse_configuration(configuration_file)
    elif args[0]=="--test":
      testing = True
    args = args[1:]
  configuration["testing"] = testing
  print("returned configuration: {}".format(configuration))
  print_configuration(configuration)
  for s in configuration["suites"]:
    s.run(testing=testing)
  #print("Done.")
