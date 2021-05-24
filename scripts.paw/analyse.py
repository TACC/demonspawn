#!/usr/bin/env python3

import re
import sys

args = sys.argv[1:]
if len(sys.argv)<2:
    print("Need two directories")
    sys.exit(1)

dir1,dir2 = sys.argv[-2:]
print(f"dir1: {dir1}")
print(f"dir2: {dir2}")

from os import listdir
from os.path import isfile, join
files1 = [f for f in listdir(dir1) if isfile(join(dir1, f)) and re.search(r'.dat$',f) ]
files2 = [f for f in listdir(dir2) if isfile(join(dir2, f)) and re.search(r'.dat$',f) ]
print(f"Files1: {files1}")
print(f"Files2: {files2}")

def parse_file(dir,fn):
    with open(join(dir,fn),"r") as f:
        timing = {}
        for l in f:
            if re.match(r'\#',l): continue
            l = l.strip(); l = re.sub(r'[ \t]+'," ",l)
            #print(f"Line:{l}")
            try:
                s,t,rest = l.split(" ",2)
                #print(f"{s}//{t}//{rest}")
                s = str(int(float(s))); t = float(t)
                timing[s] = t
            except ValueError:
                print(f"Problem parsing file <<{fn}>> line=<<{l}>>")
                continue
    return timing

def relative_error(t1,t2):
    if t1==0.:
        return abs(t2)
    elif t2==0:
        return abs(t1)
    else:
        return abs( (t2-t1)/t1 )

for f in files1:
    tol = 1.e-5
    if isfile(join(dir2,f)):
        print(f"Comparing {f}")
        timing1 = parse_file(dir1,f)
        timing2 = parse_file(dir2,f)
        #print(f".. {timing1.keys()}")
        #print(f".. {timing2.keys()}")
        for s1 in timing1.keys():
            if s1 not in timing2.keys(): continue
            t1 = timing1[s1]; t2 = timing2[s1]
            e = relative_error(t1,t2)
            if e>.2:
                print(f"At size {s1} values {t1} <> {t2} : relative {e}")

