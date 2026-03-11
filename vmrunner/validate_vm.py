#!/usr/bin/env python3
""" validate VM configuration against schema """

# pylint: disable=invalid-name

import json
import sys
import os
import glob

from builtins import str
from jsonschema import Draft4Validator, validators


# Fetched from:
# http://python-jsonschema.readthedocs.io/en/latest/faq/
def extend_with_default(validator_class):
    """ make the validator fill in defaults from the schema """
    validate_properties = validator_class.VALIDATORS["properties"]

    def set_defaults(validator_, properties, instance, schema):
        for property_, subschema in properties.items():
            if "default" in subschema:
                instance.setdefault(property_, subschema["default"])

        yield from validate_properties(
            validator_, properties, instance, schema,
        )

    return validators.extend(
        validator_class, {"properties" : set_defaults},
    )

vm_schema = None
verbose = False

validator = extend_with_default(Draft4Validator)

package_path = os.path.dirname(os.path.realpath(__file__))
default_schema = package_path + "/vm.schema.json"

def load_schema(filename = default_schema):
    """ load json schema from file """
    global vm_schema # pylint: disable=global-statement
    with open(filename, encoding="utf8") as f:
        vm_schema = json.loads(f.read())

def validate_vm_spec(filename):
    """ validate vm spec against schema """
    vm_spec = None

    # Load and parse as JSON
    try:
        with open(filename, encoding="utf8") as f:
            vm_spec = json.loads(f.read())
    except Exception as e:
        raise Exception("JSON load / parse Error for " + filename + ": " + str(e)) from e # pylint: disable=broad-exception-raised

    if not vm_schema:
        load_schema()

    # Validate JSON according to schema
    validator(vm_schema).validate(vm_spec)

    return vm_spec


def load_config(path_, verbose_ = verbose):
    """ load VM config from file """
    # Single JSON-file  must conform to VM-schema
    if os.path.isfile(path_):
        return validate_vm_spec(path_)

    jsons = []

    if os.path.isdir(path_):
        jsons = glob.glob(path_ + "/*.json")
        jsons.sort()

    # For several JSON-files, return the ones conforming to VM-schema
    valid_vms = []
    for json_ in jsons:
        if verbose_:
            print("\t*Validating ", json_, ": ", end=' ')
        try:
            spec = validate_vm_spec(json_)
            valid_vms.append(spec)
            if verbose_:
                print("OK")
        except Exception as e: # pylint: disable=broad-exception-caught
            if verbose_:
                print("FAIL " + str(e))

    return valid_vms


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "."
    if not load_config(path):
        print("No valid config found")
        sys.exit(-1)
