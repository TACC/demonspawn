#!/bin/bash

if [ $# -lt 3 ] ; then
    echo "Usage: $0 dirone dirtwo pattern"
    echo "    where pattern is used to select file names"
    exit 1
fi

dirone=$1
dirtwo=$2
pat=$3

for t in ` ( cd $dirone ; ls *${pat}* ) ` ; do 
  r=${t%%.out*}
  echo 
  echo $r
  diff paw.output/${r}* paw.output-daos/${r}*
done
