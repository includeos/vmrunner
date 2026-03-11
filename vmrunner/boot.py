#!/usr/bin/env python3
""" command line utility for vmrunner """

# pylint: disable=invalid-name

import os
import sys
import argparse
import subprocess
import shutil

from vmrunner.prettify import color

# Argparse
parser = argparse.ArgumentParser(
  description="Boot - Run IncludeOS services")

parser.add_argument("-v", "--verbose", dest="verbose", action="store_true", default=False,
                    help="Verbose output")

parser.add_argument("--sudo", dest="sudo", action="store_true", default=False,
                    help="Allow sudo. Required for creating bridges and using kvm")

parser.add_argument("--kvm", dest="kvm", action="store_true", default=False,
                    help="Enables kvm if present. Requires --sudo. The default " + \
                        "is to emulate without kvm.")

parser.add_argument("--create-bridge", dest="bridge", action="store_true",
                    help="Create bridge43, used in local testing when TAP devices " + \
                        "are supported. Requires --sudo.")

parser.add_argument("-g", "--grub", dest="grub", action="store_true",
                    help="Create image with GRUB bootloader that will boot provided " + \
                        "binary. Requires --sudo.")

parser.add_argument("--grub-reuse", dest="grub_reuse", action="store_true",
                    help="Reuse existing GRUB image if exists. Avoids reinstalling " + \
                         "GRUB. Requires --sudo.")

parser.add_argument("-j", "--config", dest="config", type = str, metavar = "PATH",
                    help="Location of VM config file - JSON validated against a schema")

parser.add_argument('vm_location', action="store", type = str, default=".",
                    help="Location of the IncludeOS service binary, image or source")

parser.add_argument("-d", "--debug", dest="debug", action="store_true",
                    help="Start hypervisor in debug mode if available")

parser.add_argument("--with-solo5-hvt", dest="solo5_hvt", action="store_true",
                    help="Run includeOS on solo5 kernel with hvt tender as monitor. " + \
                        "Requires --sudo and --kvm.")

parser.add_argument("--with-solo5-spt", dest="solo5_spt", action="store_true",
                    help="Run includeOS on solo5 kernel with spt tender as " + \
                        "monitor. Requires --sudo and --kvm.")

parser.add_argument('vmargs', nargs='*', help="Arguments to pass on to the VM start / main")

args = parser.parse_args()


# Pretty printing from this command
nametag = "<boot>    "
INFO = color.INFO(nametag)

# Override VM output prepension
color.VM_PREPEND = ""

# in verbose mode we will set VERBOSE=1 for this environment
VERB = False
if args.verbose:
    os.environ["VERBOSE"] = "1"
    VERB = True
    print(INFO, "VERBOSE mode set for environment")
# Avoid the verbose var to hang around next run
elif "VERBOSE" in os.environ:
    del os.environ["VERBOSE"]

# Note: importing vmrunner will make it start looking for VM's
# vmrunner also relies on the verbose env var to be set on initialization
from vmrunner import vmrunner # pylint: disable=wrong-import-position

# We can boot either a binary without bootloader, or an image with bootloader already attached
has_bootloader = False

# File extensions we assume to be bootable images, not just a kernel
image_extensions = [".img",
                    ".raw"]

if VERB:
    print(INFO , "Args to pass to VM: ", args.vmargs)
# path w/name of VM image to run
image_name = args.vm_location

# if the binary argument is a directory, go there immediately and
# then initialize stuff ...
if os.path.isdir(args.vm_location):
    image_name = os.path.abspath(args.vm_location)
    if VERB:
        print(INFO, "Changing directory to  " + image_name)
    os.chdir(os.path.abspath(args.vm_location))


if len(vmrunner.vms) < 1:
    # This should never happen - there should always be a default
    print(color.FAIL("No vm object found in vmrunner - nothing to boot"))
    sys.exit(-1)

if VERB:
    print(INFO, len(vmrunner.vms), "VM initialized. Commencing boot...")

config = None
if args.config:
    config = os.path.abspath(args.config)
    if VERB:
        print(INFO, "Using config file", config)

hyper_name = "qemu"
if args.solo5_hvt:
    hyper_name = "solo5-hvt"
    os.environ['PLATFORM'] = "x86_solo5"
    solo5_hvt = "solo5-hvt"

    if not args.sudo:
        print("Error: bringing up the solo5 interface requires suddo. Allow by passing --sudo")
        sys.exit(1)

    subprocess.call(['chmod', '+x', solo5_hvt])
    subprocess.call(['sudo', "solo5-ifup.sh" ])

elif args.solo5_spt:
    hyper_name = "solo5-spt"
    os.environ['PLATFORM'] = "x86_solo5"
    solo5_spt = "solo5-spt"

    if not args.sudo:
        print("Error: bringing up the solo5 interface requires suddo. Allow by passing --sudo")
        sys.exit(1)

    subprocess.call(['chmod', '+x', solo5_spt])
    subprocess.call(['sudo', "solo5-ifup.sh" ])

vm = vmrunner.add_vm(config = config, hyper_name = hyper_name)

# Don't listen to events needed by testrunner
vm.on_success(lambda x: None, do_exit = False)
vm.on_panic(lambda x: None, do_exit = False)

file_extension = os.path.splitext(args.vm_location)[1]

def is_executable(file_path):
    """ checks if file_path is a file and has executable flag """
    return os.path.isfile(file_path) and os.access(file_path, os.X_OK)

if args.debug:
    print(INFO, "Booting in debug mode")

if args.bridge:
    print(INFO, "Creating bridge")
    subprocess.call("create_bridge.sh", shell=True)

elif file_extension in image_extensions:
    if VERB:
        print(INFO, f"File extension '{file_extension}' recognized as bootable image")
    has_bootloader = True

elif not file_extension:
    if VERB:
        print(INFO, "No file extension. Trying to boot as kernel")

else:
    if VERB:
        print(INFO, f"Unrecognized file extension '{file_extension}'. " + \
                "Trying to boot as kernel")

if (args.grub or args.grub_reuse):
    print(INFO, "Creating GRUB image from ", args.vm_location)
    opts = ""

    if args.grub_reuse:
        opts += "-u "

    grubify_script = shutil.which("grubify.sh")
    if not grubify_script:
        print(f"Error: {grubify_script} not found or not executable.")
        sys.exit(1)

    if not args.sudo:
        print("Error: creating grub images require sudo. Allow with --sudo.")
        sys.exit(1)


    if not os.access('.', os.W_OK):
        print("Error: Cannot write to the current directory.")
        sys.exit(1)

    subprocess.call(grubify_script + " " + opts + image_name, shell=True)

    base_image_name = os.path.basename(image_name)
    image_name = os.path.join(os.getcwd(), base_image_name + ".grub.img")

    if not os.path.exists(image_name):
        print(f"Error: {image_name} does not exist.")
        sys.exit(1)

    has_bootloader = True

if not has_bootloader:
    vm.boot(timeout = None, multiboot = True, debug = args.debug,
            kernel_args = " ".join(args.vmargs), image_name = image_name,
            allow_sudo = args.sudo, enable_kvm = args.kvm)
else:
    vm.boot(timeout = None, multiboot = False, debug = args.debug,
            kernel_args = None, image_name = image_name, allow_sudo = args.sudo,
            enable_kvm = args.kvm)

sys.exit(0)
