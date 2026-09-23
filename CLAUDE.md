# CUPC/8: working in this repository

## Running tests

- Run anything that takes more than a few seconds (emulated firmware tests,
  QEMU, formal proofs, place and route, long test suites) **in the
  background**, then carry on with other work while it runs. Check the result
  when it finishes; don't sit waiting on it in the foreground.
- Run single tests by name rather than whole suites, unless the whole suite
  is what's needed.
