#!/usr/bin/env python
#
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

keyword_command = [ "nodes", "ppn", "suite", ]
keyword_reserved = [ "system", "user", "modules", "account", "queue", ]

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

def macros_substitute(line,macros):
  subline = line
  for m in macros.keys():
    m_search = r'\%\[{}\]'.format(m)
    if re.search(m_search,line):
      replacement_text = macros[m]
      if m=="modules":
        replacement_text = module_string(replacement_text)
      subline = re.sub( m_search, replacement_text, subline )
  return subline
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
    self.configuration["jobname"]   = kwargs.get("jobname")
    self.configuration["testing"]   = kwargs.get("testing",False)
    self.configuration["submit"]    = kwargs.get("submit",True)
    self.configuration["debug"]     = kwargs.get("debug",False)
    self.configuration["system"]    = os.environ["TACC_SYSTEM"]
    self.configuration["starttime"] = kwargs.get("starttime","00-00-00")
    self.configuration["date"] = self.configuration["starttime"]
  def parse(self,filename,**kwargs):
    suites = []
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
        # special case: jobname can be set only once
        if key=="jobname" and self.configuration["jobname"] is not "spawn":
          print("Job name can be set only once, current: "+self.configuration["jobname"])
          sys.exit(1)
        # substitute any macros
        value = macros_substitute( value,self.configuration )
        #
        # suite or macro
        #
        if key=="suite":
          # first make sure we have a log file
          SpawnFiles().set("logfile","log-"+self.configuration["jobname"])
          # now parse
          fields = value.split(" ")
          values = [ macros_substitute(f,self.configuration) for f in fields ]
          n = get_suite_name(self.configuration,values)
          s = TestSuite( values,self.configuration )
          suites.append(s)
        else:
          self.configuration[key] = value
        # ??? name,val = macro_parse(letline.groups()[1], configuration)
    self.configuration["suites"] = suites
  def run(self):
    for s in self.configuration["suites"]:
      s.run(debug=self.configuration["debug"],
            submit=self.configuration["submit"],
            testing=self.configuration["testing"])

if __name__ == "__main__":
  args = sys.argv[1:]
  testing = False                      
  debug = False
  submit  = True
  jobname = "spawn"
  rootdir = os.getcwd()
  while re.match("^-",args[0]):
    if args[0]=="-h":
      print("Usage: python3 batch.py [ -h ]  [ -d --debug ] [ -f --filesonly ] [ -t --test ] [ -n name ] [ -r rootdir ]")
      sys.exit(0)
    elif args[0] == "-n":
      args = args[1:]; jobname = args[0]
    elif args[0] == "-r":
      args = args[1:]; rootdir = args[0]
      raise Exception("root -> output")
    elif args[0] in [ "-f", "--filesonly" ] :
      submit = False
    elif args[0] in [ "-t", "--test" ]:
      testing = True; submit = False
    elif args[0] in [ "-d", "--debug" ]:
      debug = True
    args = args[1:]
  starttime = re.sub( " ","-",
                      re.sub( ":","-",
                              str( datetime.datetime.now() )
                            )
                    )
  spawnfiles = SpawnFiles()
  spawnfiles.starttime = starttime
  configuration = Configuration\
                  (jobname=jobname,
                   starttime=starttime,debug=debug,submit=submit,testing=testing)
  configuration.parse(args[0])
  SpawnFiles().setoutputdir( configuration.configuration["outputdir"] )
  # now activate all the suites
  configuration.run()
  # close all files
  SpawnFiles().__del__()

