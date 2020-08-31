info ::

info ::
	@echo "make localclean clean totalclean"
.PHONY: localclean clean totalclean
clean :: localclean
	@for d in *  ; do \
	  if [ -d "$$d" ] ; then \
	    ( cd "$$d" && make localclean -f ../Makefile ) \
	    ; \
	  fi ; \
	done
localclean ::
	@/bin/rm -rf *~ slurm*.out *.pyc __pycache__ \
	    *.out[0-9]*
totalclean :: clean
	@/bin/rm -rf paw.*
