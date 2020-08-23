info ::

info ::
	@echo "make clean"
.PHONY: clean
clean ::
	@/bin/rm -rf *~ slurm*.out *.pyc __pycache__ \
	    paw.* *.dat \
	    *.out[0-9]*
