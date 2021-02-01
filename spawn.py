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

def macro_parse(defspec,macros={}):
  #print("macro parsing: <<{}>>".format(defspec))
  name,val = defspec.split("=")
  name = name.strip(" *").lstrip(" *")
  val  =  val.strip(" *").lstrip(" *")
  val = macros_substitute( val,macros )
  print("defining macro <<{}>>=<<{}>>".format(name,val))
  return name,val

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

run_user = "eijkhout"
def DefineMacro(name,val,macros):
  newval = macros_substitute( val,macros )
  print("define {} to {}->{}".format(name,val,newval))
  macros[name] = newval
  return newval
def LetLine(specline,macros):
  letline = re.match(r'^ *(let )(.*)$',specline)
  if letline:
    print("Let, using macros:",macros)
    name,val = macro_parse(letline.groups()[1], macros)
    DefineMacro(name,val,macros)
    return True
  else: return False
def KeyValLine(specline,macros,options,system):
    # parse two-field line as macro;
    # couple of special cases
    fields = specline.split()
    if len(fields)!=2: return False
    key,value = fields
    if key=="system":
      if value!=system:
        print("This configuration can only be run on <<{}>>".format(value))
        sys.exit(1)
    # define key/value also as macro
    value = DefineMacro(key,value,macros)
    print("setting key={} to value={}".format(key,value))
    # but mostly set options[key] = value
    if key=="nodes":
      try :
        options[key] = [ int(i) for i in value.split(":") ]
      except:
        print("Could not parse node specification <<{}>>".format(value))
        raise
    else: options[key] = value
    return True
def SpecLine(specline,macros,options,suites):
    # remaining case: multi-option line
    # (mostly "suite" and "modules")
    key,fields = specline.split(" ",1)
    if key=="suite":
      fields = fields.split(" ")
      values = [ macros_substitute(f,macros) for f in fields ]
      # we can have more than one suite per configuration,
      # each uses the currect options
      print("defining testsuite with options=<<{}>>, configuration=<<{}>>"\
            .format(values,options))
      s = TestSuite( values,options )
      suites.append(s)
      print("defining suite <<{}>>".format(s))
    else:
      #fields = re.sub(" ","_",re.sub("/","-",fields))
      fields = macros_substitute(fields,macros)
      options[key] = fields
      print("setting spec: {} to value=<<{}>>".format(key,fields))
      DefineMacro(key,fields,macros)
    return True
def parse_configuration(filename):
  options = {}
  suites = []
  system = os.environ["TACC_SYSTEM"]
  macros = { "system":system,"date":str( datetime.date.today() ) }
  with open(filename,"r") as configuration:
    for specline in configuration:
      specline = specline.strip()
      if re.match("#",specline) or re.match(r'^[ \t]*$',specline):
        continue
      #
      # detect macro definitions, starting with "let"
      #
      if LetLine(specline,macros):
        continue
      #
      # simple key-value lines
      #
      if KeyValLine(specline,macros,options,system):
        continue
      #
      # other specification lines with 3 or more fields
      #
      if SpecLine(specline,macros,options,suites):
        continue
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
  debug = False
  while len(args)>0:
    if args[0]=="-h":
      print("Usage: python3 batch.py [ -h ] [ -d --debug ] [ -t --test ] [ -c configuration ]")
      sys.exit(0)
    elif args[0]=="-c":
      args = args[1:]
      if len(args)==0 or re.match("^-",args[0]):
        print("ERROR: expected name of configuration file")
        sys.exit(1)
      configuration_file = args[0]
      configuration = parse_configuration(configuration_file)
    elif args[0] in [ "-t", "--test" ]:
      testing = True
    elif args[0] in [ "-d", "--debug" ]:
      debug = True
    args = args[1:]
  configuration["debug"] = debug
  configuration["testing"] = testing
  print("returned configuration: {}".format(configuration))
  print_configuration(configuration)
  for s in configuration["suites"]:
    s.run(testing=testing)
  #print("Done.")
