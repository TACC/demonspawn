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


def DefaultModules():
  return "intel/18.0.2"

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
          raise Exception("No such directory: {}".format(dir))
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

def macro_parse(defspec):
  #print("macro parsing: <<{}>>".format(defspec))
  name,val = defspec.split("=")
  name = name.strip(" *").lstrip(" *")
  val  =  val.strip(" *").lstrip(" *")
  print("defining macro <<{}>>=<<{}>>".format(name,val))
  return name,val

def macros_substitute(line,macros):
  subline = line
  for m in macros.keys():
    m_search = r'\%\[{}\]'.format(m)
    if re.search(m_search,line):
      replacement_text = macros[m]
      if m=="modules":
        replacement_text = '_'.join( [ re.sub('/','-',m) for m in replacement_text ] )
      print("{} -> {}".format(m,replacement_text))
      subline = re.sub( m_search, replacement_text, subline )
      #print("replacing <<{}={}>> in <<{}>> gives <<{}>>".format(m,macros[m],line,subline))
  return subline

run_user = "eijkhout"
def LetLine(specline,macros):
  letline = re.match(r'^ *(let )(.*)$',specline)
  if letline:
    name,val = macro_parse(letline.groups()[1])
    macros[name] = val
    return True
  else: return False
def KeyValLine(specline,macros,options,system):
    fields = specline.split()
    if len(fields)==2:
      key,value = fields
      if key=="system":
        if value!=system:
          print("This configuration can only be run on <<{}>>".format(value))
          sys.exit(1)
        macros[key] = value
      elif key=="nodes":
        try :
          options[key] = [ int(i) for i in value.split(":") ]
        except:
          print("Could not parse node specification <<{}>>".format(value))
          raise
      else:
        value = macros_substitute(value,macros)
        options[key] = value
      print("setting key={} to value={}".format(key,value))
      return True
    else: return False
def SpecLine(specline,macros,options,suites):
    fields = specline.split()
    key = fields[0]
    value = [ macros_substitute(f,macros) for f in fields[1:] ]
    if key=="suite":
      # we can have more than one suite per configuration,
      # each uses the currect options
      print("defining testsuite with options=<<{}>>, configuration=<<{}>>"\
            .format(value,options))
      s = TestSuite( value,options )
      suites.append(s)
      print("defining suite <<{}>>".format(s))
    else:
      options[key] = value
      print("setting key={} to value={}".format(key,value))
    return True
def parse_configuration(filename):
  options = {}
  suites = []
  system = os.environ["TACC_SYSTEM"]
  macros = { "system":system }
  with open(filename,"r") as configuration:
    for specline in configuration:
      if re.match("#",specline):
        continue
      #
      # detect macro definitions
      #
      if LetLine(specline,macros):
        continue
      #
      # key-value lines
      #
      if KeyValLine(specline,macros,options,system):
        continue
      #
      # other specification lines
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
