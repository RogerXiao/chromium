# Copyright 2013 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

from collections import Mapping
import os

from api_schema_graph import APISchemaGraph
from branch_utility import BranchUtility
from compiled_file_system import CompiledFileSystem
from svn_constants import API_PATH
from third_party.json_schema_compiler import idl_schema, idl_parser, json_parse
from third_party.json_schema_compiler.json_parse import OrderedDict
from third_party.json_schema_compiler.model import UnixName


_EXTENSION_API = 'extension_api.json'


def _GetChannelFromFeatures(api_name, file_system, path):
  '''Finds API channel information within _features.json files at the given
  |path| for the given |file_system|. Returns None if channel information for
  the API cannot be located.
  '''
  feature = file_system.GetFromFile(path).get(api_name)

  if feature is None:
    return None
  if isinstance(feature, Mapping):
    # The channel information exists as a solitary dict.
    return feature.get('channel')
  # The channel information dict is nested within a list for whitelisting
  # purposes. Take the newest channel out of all of the entries.
  return BranchUtility.NewestChannel(entry.get('channel') for entry in feature)


def _GetChannelFromApiFeatures(api_name, file_system):
  return _GetChannelFromFeatures(
      api_name,
      file_system,
      '%s/_api_features.json' % API_PATH)


def _GetChannelFromManifestFeatures(api_name, file_system):
  return _GetChannelFromFeatures(
      UnixName(api_name), #_manifest_features uses unix_style API names
      file_system,
      '%s/_manifest_features.json' % API_PATH)


def _GetChannelFromPermissionFeatures(api_name, file_system):
  return _GetChannelFromFeatures(
      api_name,
      file_system,
      '%s/_permission_features.json' % API_PATH)


def _GetApiSchemaFilename(api_name, file_system):
  '''Gets the name of the file which contains the schema for |api_name| in
  |file_system|, or None if the API is not found. Note that this may be the
  single _EXTENSION_API file which all APIs share in older versions of Chrome.
  '''
  def under_api_path(path):
    return '%s/%s' % (API_PATH, path)

  file_names = file_system.ReadSingle(under_api_path('')).Get()

  if _EXTENSION_API in file_names:
    # Prior to Chrome version 18, extension_api.json contained all API schema
    # data, which replaced the current implementation of individual API files.
    # We're forced to parse this (very large) file to determine if the API
    # exists in it.
    #
    # TODO(epeterson) Avoid doing unnecessary work by re-parsing.
    # See http://crbug.com/295812.
    extension_api_json = json_parse.Parse(
        file_system.ReadSingle('%s/%s'% (API_PATH, _EXTENSION_API)).Get())
    if any(api['namespace'] == api_name for api in extension_api_json):
      return under_api_path(_EXTENSION_API)
    return None

  api_file_names = [
      file_name for file_name in file_names
      if os.path.splitext(file_name)[0] in (api_name, UnixName(api_name))]
  assert len(api_file_names) < 2
  return under_api_path(api_file_names[0]) if api_file_names else None


def _HasApiSchema(api_name, file_system):
  return _GetApiSchemaFilename(api_name, file_system) is not None


def _GetApiSchema(api_name, file_system):
  '''Searches |file_system| for |api_name|'s API schema data, and parses and
  returns it if found.
  '''
  api_file_name = _GetApiSchemaFilename(api_name, file_system)
  if api_file_name is None:
    return None

  api_file_text = file_system.ReadSingle(api_file_name).Get()
  if api_file_name == _EXTENSION_API:
    matching_schemas = [api for api in json_parse.Parse(api_file_text)
                        if api['namespace'] == api_name]
  elif api_file_name.endswith('.idl'):
    matching_schemas = idl_parser.IDLParser().ParseData(api_file_text)
  else:
    matching_schemas = json_parse.Parse(api_file_text)
  # There should only be a single matching schema per file.
  assert len(matching_schemas) == 1
  return matching_schemas


class AvailabilityFinder(object):
  '''Generates availability information for APIs by looking at API schemas and
  _features files over multiple release versions of Chrome.
  '''

  def __init__(self,
               file_system_iterator,
               object_store_creator,
               branch_utility,
               host_file_system):
    self._file_system_iterator = file_system_iterator
    self._object_store_creator = object_store_creator
    def create_object_store(category):
      return object_store_creator.Create(AvailabilityFinder, category=category)
    self._top_level_object_store = create_object_store('top_level')
    self._node_level_object_store = create_object_store('node_level')
    self._branch_utility = branch_utility
    self._host_file_system = host_file_system

  def _CheckStableAvailability(self, api_name, file_system, version):
    '''Checks for availability of an API, |api_name|, on the stable channel.
    Considers several _features.json files, file system existence, and
    extension_api.json depending on the given |version|.
    '''
    if version < 5:
      # SVN data isn't available below version 5.
      return False
    available_channel = None
    fs_factory = CompiledFileSystem.Factory(file_system,
                                            self._object_store_creator)
    features_fs = fs_factory.Create(lambda _, json: json_parse.Parse(json),
                                    AvailabilityFinder,
                                    category='features')
    if version >= 28:
      # The _api_features.json file first appears in version 28 and should be
      # the most reliable for finding API availability.
      available_channel = _GetChannelFromApiFeatures(api_name, features_fs)
    if version >= 20:
      # The _permission_features.json and _manifest_features.json files are
      # present in Chrome 20 and onwards. Use these if no information could be
      # found using _api_features.json.
      available_channel = available_channel or (
          _GetChannelFromPermissionFeatures(api_name, features_fs)
          or _GetChannelFromManifestFeatures(api_name, features_fs))
      if available_channel is not None:
        return available_channel == 'stable'
    if version >= 5:
      # Fall back to a check for file system existence if the API is not
      # stable in any of the _features.json files, or if the _features files
      # do not exist (version 19 and earlier).
      return _HasApiSchema(api_name, file_system)

  def _CheckChannelAvailability(self, api_name, file_system, channel_name):
    '''Searches through the _features files in a given |file_system| and
    determines whether or not an API is available on the given channel,
    |channel_name|.
    '''
    fs_factory = CompiledFileSystem.Factory(file_system,
                                            self._object_store_creator)
    features_fs = fs_factory.Create(lambda _, json: json_parse.Parse(json),
                                    AvailabilityFinder,
                                    category='features')
    available_channel = (_GetChannelFromApiFeatures(api_name, features_fs)
        or _GetChannelFromPermissionFeatures(api_name, features_fs)
        or _GetChannelFromManifestFeatures(api_name, features_fs))
    if available_channel is None and _HasApiSchema(api_name, file_system):
      # If an API is not represented in any of the _features files, but exists
      # in the filesystem, then assume it is available in this version.
      # The windows API is an example of this.
      available_channel = channel_name
    # If the channel we're checking is the same as or newer than the
    # |available_channel| then the API is available at this channel.
    return (available_channel is not None and
            BranchUtility.NewestChannel((available_channel, channel_name))
                == channel_name)

  def _CheckApiAvailability(self, api_name, file_system, channel_info):
    '''Determines the availability for an API at a certain version of Chrome.
    Two branches of logic are used depending on whether or not the API is
    determined to be 'stable' at the given version.
    '''
    if channel_info.channel == 'stable':
      return self._CheckStableAvailability(api_name,
                                           file_system,
                                           channel_info.version)
    return self._CheckChannelAvailability(api_name,
                                          file_system,
                                          channel_info.channel)

  def GetApiAvailability(self, api_name):
    '''Performs a search for an API's top-level availability by using a
    HostFileSystemIterator instance to traverse multiple version of the
    SVN filesystem.
    '''
    availability = self._top_level_object_store.Get(api_name).Get()
    if availability is not None:
      return availability

    def check_api_availability(file_system, channel_info):
      return self._CheckApiAvailability(api_name, file_system, channel_info)

    availability = self._file_system_iterator.Descending(
        self._branch_utility.GetChannelInfo('dev'),
        check_api_availability)
    if availability is None:
      # The API wasn't available on 'dev', so it must be a 'trunk'-only API.
      availability = self._branch_utility.GetChannelInfo('trunk')
    self._top_level_object_store.Set(api_name, availability)
    return availability

  def GetApiNodeAvailability(self, api_name):
    '''Returns an APISchemaGraph annotated with each node's availability (the
    ChannelInfo at the oldest channel it's available in).
    '''
    availability_graph = self._node_level_object_store.Get(api_name).Get()
    if availability_graph is not None:
      return availability_graph


    availability_graph = APISchemaGraph()
    trunk_graph = APISchemaGraph(_GetApiSchema(api_name,
                                               self._host_file_system))
    def update_availability_graph(file_system, channel_info):
      version_graph = APISchemaGraph(_GetApiSchema(api_name, file_system))
      # Keep track of any new schema elements from this version by adding
      # them to |availability_graph|.
      #
      # Calling |availability_graph|.Lookup() on the nodes being updated
      # will return the |annotation| object.
      availability_graph.Update(version_graph.Subtract(availability_graph),
                                annotation=channel_info)

      # Continue looping until there are no longer differences between this
      # version and trunk.
      return trunk_graph != version_graph

    self._file_system_iterator.Ascending(self.GetApiAvailability(api_name),
                                         update_availability_graph)

    self._node_level_object_store.Set(api_name, availability_graph)
    return availability_graph
