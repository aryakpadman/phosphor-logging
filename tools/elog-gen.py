#!/usr/bin/env python3

r"""
This script will parse error log yaml file(s) and generate
a header file which will then be used by the error logging client and
server to collect and validate the error information generated by the
openbmc software components.

This code uses a mako template to provide the basic template of the header
file we're going to generate.  We then call it with information from the
yaml to generate the header file.
"""

from mako.template import Template
from optparse import OptionParser
import yaml
import sys
import os


def order_inherited_errors(i_errors, i_parents):
    # the ordered list of errors
    errors = list()
    has_inheritance = False
    for error in i_errors:
        if(i_parents[error] is not None):
            has_inheritance = True
            break

    if(has_inheritance):
        # Order the error codes list such that an error is never placed
        # before it's parent. This way generated code can ensure parent
        # definitions precede child error definitions.
        while(len(errors) < len(i_errors)):
            for error in i_errors:
                if(error in errors):
                    # already ordererd
                    continue
                if((not i_parents[error]) or (i_parents[error] in errors)):
                    # parent present, or has no parent, either way this error
                    # can be added
                    errors.append(error)
    else:
        # no inherited errors
        errors = i_errors

    return errors


def check_error_inheritance(i_errors, i_parents):
    for error in i_errors:
        if(i_parents[error] and (i_parents[error] not in i_errors)):
            print(error + " inherits " + i_parents[error] +
                  " but the latter is not defined")
            return False
    return True


# Return the yaml files with their directory structure plus the file name
# without the yaml extension, which will be used to set the namespaces.
# Ex: file xyz/openbmc_project/Error/Callout/Device.errors.yaml
# will have namespce xyz/openbmc_project/Error/Callout/Device
def get_error_yaml_files(i_yaml_dir, i_test_dir):
    yaml_files = dict()
    if i_yaml_dir != "None":
        for root, dirs, files in os.walk(i_yaml_dir):
            for files in \
                    [file for file in files if file.endswith('.errors.yaml')]:
                splitdir = root.split(i_yaml_dir)[1] + "/" + files[:-12]
                if splitdir.startswith("/"):
                    splitdir = splitdir[1:]
                yaml_files[(os.path.join(root, files))] = splitdir
    for root, dirs, files in os.walk(i_test_dir):
        for files in [file for file in files if file.endswith('.errors.yaml')]:
            splitdir = root.split(i_test_dir)[1] + "/" + files[:-12]
            yaml_files[(os.path.join(root, files))] = splitdir
    return yaml_files


def get_meta_yaml_file(i_error_yaml_file):
    # the meta data will be defined in file name where we replace
    # <Interface>.errors.yaml with <Interface>.metadata.yaml
    meta_yaml = i_error_yaml_file.replace("errors", "metadata")
    return meta_yaml


def get_cpp_type(i_type):
    typeMap = {
        'int16': 'int16_t',
        'int32': 'int32_t',
        'int64': 'int64_t',
        'uint16': 'uint16_t',
        'uint32': 'uint32_t',
        'uint64': 'uint64_t',
        'double': 'double',
        # const char* aids usage of constexpr
        'string': 'const char*'}

    return typeMap[i_type]


def gen_elog_hpp(i_yaml_dir, i_test_dir, i_output_hpp,
                 i_template_dir, i_elog_mako):
    r"""
    Read  yaml file(s) under input yaml dir, grab the relevant data and call
    the mako template to generate the output header file.

    Description of arguments:
    i_yaml_dir                  directory containing base error yaml files
    i_test_dir                  directory containing test error yaml files
    i_output_hpp                name of the to be generated output hpp
    i_template_dir              directory containing error mako templates
    i_elog_mako                 error mako template to render
    """

    # Input parameters to mako template
    errors = list()  # Main error codes
    error_msg = dict()  # Error msg that corresponds to error code
    error_lvl = dict()  # Error code log level (debug, info, error, ...)
    meta = dict()  # The meta data names associated (ERRNO, FILE_NAME, ...)
    meta_data = dict()  # The meta data info (type, format)
    parents = dict()
    metadata_process = dict()  # metadata that have the 'process' keyword set

    error_yamls = get_error_yaml_files(i_yaml_dir, i_test_dir)

    for error_yaml in error_yamls:
        # Verify the error yaml file
        if (not (os.path.isfile(error_yaml))):
            print("Cannot find input yaml file " + error_yaml)
            exit(1)

        # Verify the metadata yaml file
        meta_yaml = get_meta_yaml_file(error_yaml)

        # Verify the input mako file
        template_path = "/".join((i_template_dir, i_elog_mako))
        if (not (os.path.isfile(template_path))):
            print("Cannot find input template file " + template_path)
            exit(1)

        get_elog_data(error_yaml,
                      meta_yaml,
                      error_yamls[error_yaml],
                      # Last arg is a tuple
                      (errors,
                       error_msg,
                       error_lvl,
                       meta,
                       meta_data,
                       parents,
                       metadata_process))

    if(not check_error_inheritance(errors, parents)):
        print("Error - failed to validate error inheritance")
        exit(1)

    errors = order_inherited_errors(errors, parents)

    # Load the mako template and call it with the required data
    yaml_dir = i_yaml_dir.strip("./")
    yaml_dir = yaml_dir.strip("../")
    template = Template(filename=template_path)
    f = open(i_output_hpp, 'w')
    f.write(template.render(
            errors=errors,
            error_msg=error_msg,
            error_lvl=error_lvl,
            meta=meta,
            meta_data=meta_data,
            parents=parents,
            metadata_process=metadata_process))
    f.close()

def get_elog_data(i_elog_yaml,
                  i_elog_meta_yaml,
                  i_namespace,
                  o_elog_data):
    r"""
    Parse the error and metadata yaml files in order to pull out
    error metadata.

    Use default values if metadata yaml file is not found.

    Description of arguments:
    i_elog_yaml                 error yaml file
    i_elog_meta_yaml            metadata yaml file
    i_namespace                 namespace data
    o_elog_data                 error metadata
    """
    (errors, error_msg, error_lvl, meta,
     meta_data, parents, metadata_process) = o_elog_data
    ifile = yaml.safe_load(open(i_elog_yaml))

    #for all the errors in error yaml file
    for error in ifile:
        if 'name' not in error:
            print("Error - Did not find name in entry %s in file %s " % (
                str(error), i_elog_yaml))
            exit(1)
        fullname = i_namespace.replace('/', '.') + ('.') + error['name']
        errors.append(fullname)

        if 'description' in error:
            error_msg[fullname] = error['description'].strip()

        #set default values
        error_lvl[fullname] = "ERR"
        parents[fullname] = None

        #check if meta data yaml file is found
        if not os.path.isfile(i_elog_meta_yaml):
            continue
        mfile = yaml.safe_load(open(i_elog_meta_yaml))

        # Find the meta data entry
        match = None
        for meta_entry in mfile:
            if meta_entry['name'] == error['name']:
                match = meta_entry
                break

        if match is None:
            print("Error - Did not find error named %s in %s" % (
                error['name'], i_elog_meta_yaml))
            continue

        error_lvl[fullname] = match.get('level', 'ERR')

        # Get 0th inherited error (current support - single inheritance)
        if 'inherits' in match:
            parents[fullname]  = match['inherits'][0]

        # Put all errors in meta[] even the meta is empty
        # so that child errors could inherits such error without meta
        tmp_meta = []
        if 'meta' in match:
            # grab all the meta data fields and info
            for i in match['meta']:
                str_short = i['str'].split('=')[0]
                tmp_meta.append(str_short)
                meta_data[str_short] = {}
                meta_data[str_short]['str'] = i['str']
                meta_data[str_short]['str_short'] = str_short
                meta_data[str_short]['type'] = get_cpp_type(i['type'])
                if ('process' in i) and (True == i['process']):
                    metadata_process[str_short] = fullname + "." + str_short
        meta[fullname] = tmp_meta

    # Debug
    # for i in errors:
    #   print "ERROR: " + errors[i]
    #   print " MSG:  " + error_msg[errors[i]]
    #   print " LVL:  " + error_lvl[errors[i]]
    #   print " META: "
    #   print meta[i]


def main(i_args):
    parser = OptionParser()

    parser.add_option("-m", "--mako", dest="elog_mako",
                      default="elog-gen-template.mako.hpp",
                      help="input mako template file to use")

    parser.add_option("-o", "--output", dest="output_hpp",
                      default="elog-errors.hpp",
                      help="output hpp to generate, elog-errors.hpp default")

    parser.add_option("-y", "--yamldir", dest="yamldir",
                      default="None",
                      help="Base directory of yaml files to process")

    parser.add_option("-u", "--testdir", dest="testdir",
                      default="./tools/example/",
                      help="Unit test directory of yaml files to process")

    parser.add_option("-t", "--templatedir", dest="templatedir",
                      default="phosphor-logging/templates/",
                      help="Base directory of files to process")

    (options, args) = parser.parse_args(i_args)

    gen_elog_hpp(options.yamldir,
                 options.testdir,
                 options.output_hpp,
                 options.templatedir,
                 options.elog_mako)

# Only run if it's a script
if __name__ == '__main__':
    main(sys.argv[1:])
