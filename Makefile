info ::

info ::
	@echo "make clean"
.PHONY: clean
clean :: localclean
	@for d in *  ; do \
	  if [ -d "$$d" ] ; then \
	    ( cd "$$d" && make localclean -f ../Makefile ) \
	    ; \
	  fi ; \
	done
localclean ::
	@/bin/rm -rf *~ slurm*.out *.pyc __pycache__ \
	    paw.* *.dat \
	    *.out[0-9]*
