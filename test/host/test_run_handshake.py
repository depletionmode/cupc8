#!/usr/bin/env python3
"""HOST-002 upload protocol without firmware build dependencies."""
import test_cupc8

test_cupc8.test_run_handshake()
print("HOST-002 upload handshake: %d checks, %d failures" %
      (test_cupc8.checks, test_cupc8.bad))
raise SystemExit(1 if test_cupc8.bad else 0)
