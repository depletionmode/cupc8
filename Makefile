# CUPC/8 top-level targets. Test details: test/README.md

.PHONY: test verify test-list

JOBS ?= $(shell nproc)

# every implemented test (developer loop)
test:
	python3 test/run.py -j $(JOBS)

# the fab gate: fails while any test fails or any non-hardware test is pending
verify:
	python3 test/run.py --gate -j $(JOBS); test_rc=$$?; python3 tools/fabready.py; readiness_rc=$$?; test $$test_rc -eq 0 && test $$readiness_rc -eq 0

test-list:
	python3 test/run.py --list

# Explicit developer report; cannot describe offline packages as manufacturing ready.
.PHONY: verify-development
verify-development:
	python3 test/run.py --gate -j $(JOBS); test_rc=$$?; python3 tools/fabready.py --development; exit $$test_rc
