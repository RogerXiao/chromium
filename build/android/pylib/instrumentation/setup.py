# Copyright 2013 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Generates test runner factory and tests for instrumentation tests."""

import logging
import os

from pylib.instrumentation import test_package
from pylib.instrumentation import test_runner


def Setup(test_options):
  """Create and return the test runner factory and tests.

  Args:
    test_options: An InstrumentationOptions object.

  Returns:
    A tuple of (TestRunnerFactory, tests).
  """
  if (test_options.coverage_dir and not
      os.path.exists(test_options.coverage_dir)):
    os.makedirs(test_options.coverage_dir)

  test_pkg = test_package.TestPackage(test_options.test_apk_path,
                                      test_options.test_apk_jar_path)
  tests = test_pkg.GetAllMatchingTests(
      test_options.annotations,
      test_options.exclude_annotations,
      test_options.test_filter)
  if not tests:
    logging.error('No instrumentation tests to run with current args.')

  def TestRunnerFactory(device, shard_index):
    return test_runner.TestRunner(test_options, device, shard_index,
                                  test_pkg)

  return (TestRunnerFactory, tests)
