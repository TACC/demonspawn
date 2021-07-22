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

# def macro_parse(defspec,macros={}):
#   #print("macro parsing: <<{}>>".format(defspec))
#   name,val = defspec.split("=")
#   name = name.strip(" *").lstrip(" *")
#   val  =  val.strip(" *").lstrip(" *")
#   val = macros_substitute( val,macros )
#   print("defining macro <<{}>>=<<{}>>".format(name,val))
#   return name,val

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
    self.configuration["jobname"]   = kwargs.get("jobname",None)
    self.configuration["testing"]   = kwargs.get("testing",False)
    self.configuration["submit"]    = kwargs.get("submit",True)
    self.configuration["debug"]     = kwargs.get("debug",False)
    self.configuration["system"]    = os.environ["TACC_SYSTEM"]
    self.configuration["starttime"] = re.sub( " ","-",str( datetime.datetime.now() ) )
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
        # special case: modules
        if key=="modules":
          value = value
        # substitute any macros
        value = macros_substitute( value,self.configuration )
        # special case: name
        # otherwise
        #
        # suite or macro
        #
        if key=="suite":
          fields = value.split(" ")
          values = [ macros_substitute(f,self.configuration) for f in fields ]
          n = get_suite_name(self.configuration,values)
          s = TestSuite( values,self.configuration )
          suites.append(s)
        else:
          self.configuration[key] = value
        # ??? name,val = macro_parse(letline.groups()[1], configuration)
    self.configuration["suites"] = suites
  def set_dirs(self,name,rootdir=None):
    self.regressionfile \
      = SpawnFiles().open( f"{rootdir}/regression-{name}-{self.starttime}.txt","w" )
    self.configuration["logfile"] = self.logfile
    self.configuration["regressionfile"] = self.regressionfile
    scriptdir = f"{rootdir}/scripts-{name}-{self.starttime}"
    outputdir = f"{rootdir}/output-{name}-{self.starttime}"
    self.configuration["scriptdir"] = scriptdir
    self.configuration["outputdir"] = outputdir
    try :
      os.mkdir( scriptdir )
      os.mkdir( outputdir )
    except FileExistsError :
      print("script / output dir already exists")
      pass
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
  name = "spawn"
  rootdir = os.getcwd()
  while re.match("^-",args[0]):
    if args[0]=="-h":
      print("Usage: python3 batch.py [ -h ]  [ -d --debug ] [ -f --filesonly ] [ -t --test ] [ -n name ] [ -r rootdir ]")
      sys.exit(0)
    elif args[0] == "-n":
      args = args[1:]; name = args[0]
    elif args[0] == "-r":
      args = args[1:]; rootdir = args[0]
    elif args[0] in [ "-f", "--filesonly" ] :
      submit = False
    elif args[0] in [ "-t", "--test" ]:
      testing = True; submit = False
    elif args[0] in [ "-d", "--debug" ]:
      debug = True
    args = args[1:]
  configuration = Configuration(debug=debug,submit=submit,testing=testing)
  spawnfiles = SpawnFiles()
  spawnfiles.starttime = configuration.configuration["starttime"]
  spawnfiles.rootdir = rootdir
  #configuration.set_dirs(name,rootdir)
  configuration.parse(args[0])
  # now activate all the suites
  configuration.run()
  # close all files
  SpawnFiles().__del__()
  #print("returned configuration: {}".format(configuration))
  #print_configuration(configuration)
  #print("Done.")
