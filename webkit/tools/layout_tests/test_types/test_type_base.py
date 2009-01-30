# Copyright (c) 2006-2008 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Defines the interface TestTypeBase which other test types inherit from.

Also defines the TestArguments "struct" to pass them additional arguments.
"""

import cgi
import difflib
import errno
import os.path
import subprocess


import google.path_utils

from layout_package import path_utils
from layout_package import platform_utils

def isRenderTreeDump(data):
  """Returns true if data appears to be a render tree dump as opposed to a
  plain text dump."""
  return data.find("RenderView at (0,0)") != -1

class TestArguments(object):
  """Struct-like wrapper for additional arguments needed by specific tests."""
  # Whether to save new baseline results.
  new_baseline = False

  # Path to the actual PNG file generated by pixel tests
  png_path = None

  # Value of checksum generated by pixel tests.
  hash = None

  # Whether to use wdiff to generate by-word diffs.
  wdiff = False

  # Whether to report the locations of the expected result files used.
  show_sources = False

# Python bug workaround.  See the wdiff code in WriteOutputFiles for an
# explanation.
_wdiff_available = True

class TestTypeBase(object):
  # Filename pieces when writing failures to the test results directory.
  FILENAME_SUFFIX_ACTUAL = "-actual"
  FILENAME_SUFFIX_EXPECTED = "-expected"
  FILENAME_SUFFIX_DIFF = "-diff"
  FILENAME_SUFFIX_WDIFF = "-wdiff.html"
  FILENAME_SUFFIX_COMPARE = "-diff.png"

  def __init__(self, platform, root_output_dir):
    """Initialize a TestTypeBase object.

    Args:
      platform: the platform (e.g., 'chromium-mac-leopard') identifying the
        platform-specific results to be used
      root_output_dir: The unix style path to the output dir.
    """
    self._root_output_dir = root_output_dir
    self._platform = platform
  
  def _MakeOutputDirectory(self, filename):
    """Creates the output directory (if needed) for a given test filename."""
    output_filename = os.path.join(self._root_output_dir,
                                   path_utils.RelativeTestFilename(filename))
    google.path_utils.MaybeMakeDirectory(os.path.split(output_filename)[0])

  def _SaveBaselineData(self, filename, data, modifier):
    """Saves a new baseline file into the platform directory.

    The file will be named simply "<test>-expected<modifier>", suitable for
    use as the expected results in a later run.

    Args:
      filename: path to the test file
      data: result to be saved as the new baseline
      modifier: type of the result file, e.g. ".txt" or ".png"
    """
    output_file = os.path.basename(os.path.splitext(filename)[0] +
                                   self.FILENAME_SUFFIX_EXPECTED + modifier)
    if isRenderTreeDump(data):
      relative_dir = os.path.dirname(path_utils.RelativeTestFilename(filename))
      output_dir = os.path.join(path_utils.PlatformResultsDir(self._platform),
                                self._platform,
                                relative_dir)

      google.path_utils.MaybeMakeDirectory(output_dir)
      open(os.path.join(output_dir, output_file), "wb").write(data)
    else:
      # If it's not a render tree, then the results can be shared between all
      # platforms.  Copy the file into the chromium-win and chromium-mac dirs.
      relative_dir = os.path.dirname(path_utils.RelativeTestFilename(filename))
      for platform in ('chromium-win', 'chromium-mac'):
        output_dir = os.path.join(path_utils.PlatformResultsDir(self._platform),
                                  platform,
                                  relative_dir)

        google.path_utils.MaybeMakeDirectory(output_dir)
        open(os.path.join(output_dir, output_file), "wb").write(data)

  def OutputFilename(self, filename, modifier):
    """Returns a filename inside the output dir that contains modifier.
    
    For example, if filename is c:/.../fast/dom/foo.html and modifier is
    "-expected.txt", the return value is
    c:/cygwin/tmp/layout-test-results/fast/dom/foo-expected.txt
    
    Args:
      filename: absolute filename to test file
      modifier: a string to replace the extension of filename with

    Return:
      The absolute windows path to the output filename
    """
    output_filename = os.path.join(self._root_output_dir,
                                   path_utils.RelativeTestFilename(filename))
    return os.path.splitext(output_filename)[0] + modifier

  def RelativeOutputFilename(self, filename, modifier):
    """Returns a relative filename inside the output dir that contains 
    modifier.
    
    For example, if filename is fast\dom\foo.html and modifier is
    "-expected.txt", the return value is fast\dom\foo-expected.txt
    
    Args:
      filename: relative filename to test file
      modifier: a string to replace the extension of filename with

    Return:
      The relative windows path to the output filename
    """
    return os.path.splitext(filename)[0] + modifier

  def CompareOutput(self, filename, proc, output, test_args, target):
    """Method that compares the output from the test with the expected value.
    
    This is an abstract method to be implemented by all sub classes.
    
    Args:
      filename: absolute filename to test file
      proc: a reference to the test_shell process
      output: a string containing the output of the test
      test_args: a TestArguments object holding optional additional arguments
      target: Debug or Release
    
    Return:
      a list of TestFailure objects, empty if the test passes
    """
    raise NotImplemented

  def WriteOutputFiles(self, filename, test_type, file_type, output, expected,
                       diff=True, wdiff=False):
    """Writes the test output, the expected output and optionally the diff
    between the two to files in the results directory.

    The full output filename of the actual, for example, will be
      <filename><test_type>-actual<file_type>
    For instance,
      my_test-simp-actual.txt

    Args:
      filename: The test filename
      test_type: A string describing the test type, e.g. "simp"
      file_type: A string describing the test output file type, e.g. ".txt"
      output: A string containing the test output
      expected: A string containing the expected test output
      diff: if True, write a file containing the diffs too. This should be
          False for results that are not text
      wdiff: if True, write an HTML file containing word-by-word diffs
    """
    self._MakeOutputDirectory(filename)
    actual_filename = self.OutputFilename(filename,
                      test_type + self.FILENAME_SUFFIX_ACTUAL + file_type)
    expected_filename = self.OutputFilename(filename,
                      test_type + self.FILENAME_SUFFIX_EXPECTED + file_type)
    open(actual_filename, "wb").write(output)
    open(expected_filename, "wb").write(expected)

    if diff:
      diff = difflib.unified_diff(expected.splitlines(True),
                                  output.splitlines(True),
                                  expected_filename,
                                  actual_filename)

      diff_filename = self.OutputFilename(filename,
                           test_type + self.FILENAME_SUFFIX_DIFF + file_type)
      open(diff_filename, "wb").write(''.join(diff))

    if wdiff:
      # Shell out to wdiff to get colored inline diffs.
      platform_util = platform_utils.PlatformUtility('')
      executable = platform_util.WDiffExecutablePath()
      cmd = [executable,
             '--start-delete=##WDIFF_DEL##', '--end-delete=##WDIFF_END##',
             '--start-insert=##WDIFF_ADD##', '--end-insert=##WDIFF_END##',
             actual_filename, expected_filename]
      filename = self.OutputFilename(filename,
                      test_type + self.FILENAME_SUFFIX_WDIFF)

      global _wdiff_available

      try:
        # Python's Popen has a bug that causes any pipes opened to a process
        # that can't be exceuted to be leaked.  Since this code is specifically
        # designed to tolerate exec failures to gracefully handle cases where
        # wdiff is not installed, the bug results in a massive file descriptor
        # leak.  As a workaround, if an exec failure is ever experienced for
        # wdiff, assume it's not available.  This will leak one file descriptor
        # but that's better than leaking each time wdiff would be run.
        #
        # http://mail.python.org/pipermail/python-list/2008-August/505753.html
        # http://bugs.python.org/issue3210
        if _wdiff_available:
          wdiff = subprocess.Popen(cmd, stdout=subprocess.PIPE).communicate()[0]
      except OSError, e:
        if e.errno == errno.ENOENT or e.errno == errno.EACCES:
          _wdiff_available = False
        else:
          raise e

      if not _wdiff_available:
        out = open(filename, 'wb')
        out.write(
            """wdiff not installed.<br/>"""
            """If you're running OS X, you can install via macports.<br/>"""
            """If running Ubuntu linux, you can run "sudo apt-get install"""
            """ wdiff".""")
        out.close()
        return

      wdiff = cgi.escape(wdiff)
      wdiff = wdiff.replace('##WDIFF_DEL##', '<span class=del>')
      wdiff = wdiff.replace('##WDIFF_ADD##', '<span class=add>')
      wdiff = wdiff.replace('##WDIFF_END##', '</span>')
      out = open(filename, 'wb')
      out.write('<head><style>.del { background: #faa; } ')
      out.write('.add { background: #afa; }</style></head>')
      out.write('<pre>' + wdiff + '</pre>')
      out.close()
