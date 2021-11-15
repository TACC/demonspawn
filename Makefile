################################################################
####
#### Makefile for the Demonspawn tool
#### Victor Eijkhout eijkhout@tacc.utexas.edu
#### 2020-2021
####
################################################################

info ::

info ::
	@echo "make localclean clean totalclean"
.PHONY: localclean clean totalclean
clean :: localclean
	@for d in *  ; do \
	  if [ -d "$$d" ] ; then \
	    ( cd "$$d" && make --no-print-directory localclean -f ../Makefile ) \
	    ; \
	  fi ; \
	done
localclean ::
	@/bin/rm -rf *~ slurm*.out *.pyc __pycache__ \
	    *.out[0-9]* *.slurm-out
totalclean :: clean
	@/bin/rm -rf log-* regress-* regression-* output-* script-* scripts-* \
	    logfile-* spawn-* testsuite-*
