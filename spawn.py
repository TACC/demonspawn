#!/usr/bin/env python
#
# Victor Eijkhout
# copyright 2020-2022

#--------------------------------------------------------------------------------
# System
#from __future__ import print_function
import copy
import datetime
import os
import re
import sys
import time


#--------------------------------------------------------------------------------
# Local
from jobsuite import *

keyword_command = [ "nodes", "ppn", "suite", ]
keyword_reserved = [ "system", "modules", 
                     # slurm variables
                     "account", "queue", "date", "time", "user",
                   ]

def read_batch_template(filename):
  """
     Read in Slurm batch submit template and return as a string.
  """
  return open(filename, "r").read()


def DefaultModules():
  return "intel/18.0.2"

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

def get_suite_name(options,values):
  if "name" in options.keys():
    return options["name"]
  else:
    for kv in values:
      if  re.match("name:",kv):
        k,v = kv.split(":")
        return v
  return "testsuite"

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

class Configuration():
  def __init__(self,**kwargs):
    self.configuration = {}
    self.configuration["jobname"]   = kwargs.get("jobname","spawn")
    jobname = self.configuration["jobname"]
    self.configuration["testing"]   = kwargs.get("testing",False)
    self.configuration["submit"]    = kwargs.get("submit",True)
    self.configuration["debug"]     = kwargs.get("debug",False)
    self.configuration["date"]      = kwargs.get("date","00-00-00")
    self.configuration["modules"]   = "default"
    try :
      self.configuration["system"]    = os.environ["TACC_SYSTEM"]
    except:
      self.configuration["system"]    = None
    try :
      self.configuration["mpi"]       = os.environ["LMOD_FAMILY_MPI"]
    except:
      self.configuration["mpi"]       = "mpich"
    self.configuration["pwd"]       = os.getcwd()
  def parse(self,filename,**kwargs):
    for k in [ "suites","sbatch","env" ]:
      self.configuration[k] = []
    queue = None
    with open(filename,"r") as configuration:
      for specline in configuration:
        specline = specline.strip()
        #
        # skip comments
        if re.match("#",specline) or re.match(r'^[ \t]*$',specline):
          continue
        #
        # otherwise interpret as key/value
        #
        key,value = specline.split(" ",1)
        # special case: system
        if key=="system":
          if value!=self.configuration["system"]:
            print(f"This configuration can only be run on <<{value}>>")
            sys.exit(1)
        # substitute any macros
        value = macros_substitute( value,self.configuration )

        # special case: jobname can be set only once
        if key=="jobname" and jobname != "spawn":
            raise Exception(f"Job name can be set only once, current: {jobname}")
        # special case: queue
        elif key=="queue":
            queue = value; nam_lim = value.split(); qname = nam_lim[0]; qlimit = 1
            if len(nam_lim)>1:
                qlimit = nam_lim[1]
                if re.match("limit",qlimit):
                    qlimit = qlimit.split(":")[1]
            Queues().add_queue( qname,qlimit )
            self.configuration[key] = qname
        # special case: output dir needs to be set immediately
        elif key=="outputdir":
          raise Exception("outputdir key deprecated")
        # special case: `sbatch'  and `env' lines are appended
        elif key in ["sbatch","env"]:
          self.configuration[key].append(value)
        #
        # suite or macro
        #
        elif key=="suite":
          # now parse
          fields = value.split(" ")
          suitespec = [ macros_substitute(f,self.configuration) for f in fields ]
          n = get_suite_name(self.configuration,suitespec)
          s = TestSuite( suitespec, copy.copy(self.configuration) )
          self.configuration["suites"].append(s)
        else:
          self.configuration[key] = value
  def run(self):
    for s in self.configuration["suites"]:
      s.run(debug=self.configuration["debug"],
            submit=self.configuration["submit"],
            testing=self.configuration["testing"])

if __name__ == "__main__":
  if sys.version_info[0]<3:
    print("Please move to python3"); sys.exit(1)
  if sys.version_info[1]<8:
    print("This requires at least python 3.8"); sys.exit(1)
  args = sys.argv[1:]
  testing = False                      
  debug = False
  submit  = True
  jobname = "spawn"; outputdir = None
  rootdir = os.getcwd()
  while re.match("^-",args[0]):
    if args[0]=="-h":
      print("Usage: python3 batch.py [ -h ]  [ -d --debug ] [ -f --filesonly ] [ -t --test ] [ -n name ] [ -r --regression dir ] [ -o --output dir ")
      sys.exit(0)
    elif args[0] == "-n":
      args = args[1:]; jobname = args[0]
    elif args[0] in [ "-f", "--filesonly" ] :
      submit = False; testing = False
    elif args[0] in [ "-r",  "--regression" ] :
      args = args[1:]; outputdir = args[0]
      testing = True; submit = False
    elif args[0] in [ "-o",  "--outputdir" ] :
      args = args[1:]; outputdir = args[0]
    elif args[0] in [ "-t", "--test" ]:
      testing = True; submit = False
    elif args[0] in [ "-d", "--debug" ]:
      debug = True
      SpawnFiles().debug = True
    args = args[1:]
  now = datetime.datetime.now()
  starttime = f"{now.year}{now.month}{now.day}-{now.hour}.{now.minute}"

  print(f"Output dir: {outputdir}")
  if not outputdir:
    outputdir = f"spawn_output_{starttime}"
  SpawnFiles().setoutputdir(outputdir)

  configuration = Configuration\
                  (jobname=jobname,date=starttime,debug=debug,submit=submit,testing=testing)
  SpawnFiles().open_new(f"logfile-{jobname}-{starttime}",key="logfile")
  queues = Queues()
  queues.testing = testing
  if os.path.exists(".spawnrc"):
    configuration.parse(".spawnrc")
  configuration.parse(args[0])

  # now activate all the suites
  configuration.run()
  # close all files
  SpawnFiles().__del__()

