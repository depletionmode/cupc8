# CUPC/8 top-level targets. Test details: test/README.md

.PHONY: test verify test-list

# every implemented test (developer loop)
test:
	python3 test/run.py

# the fab gate: fails while any test fails or any non-hardware test is pending
verify:
	python3 test/run.py --gate

test-list:
	python3 test/run.py --list
