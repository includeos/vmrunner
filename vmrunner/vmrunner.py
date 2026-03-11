#!/usr/bin/env python3

""" vmrunner is hypervisor-agnostic tool and library for running
    and testing IncludeOS unikernels """

# pylint: disable=line-too-long, too-many-lines, invalid-name, fixme, broad-exception-raised, broad-exception-caught, too-many-arguments, too-many-branches, too-many-statements, too-many-instance-attributes, too-many-locals

from builtins import hex
from builtins import chr
from builtins import str

import os
import sys
import subprocess
import threading
import re
import traceback
import signal
import tempfile
from enum import Enum
import platform
import psutil

from vmrunner import validate_vm
from .prettify import color

package_path = os.path.dirname(os.path.realpath(__file__))

# Use INCLUDEOS_VMRUNNER from environment if set, otherwise get from package metadata
INCLUDEOS_VMRUNNER = os.environ.get('INCLUDEOS_VMRUNNER', None)
if INCLUDEOS_VMRUNNER is None:
    from importlib.metadata import files
    for p_ in files('vmrunner'):
        if '__init__.py' in str(p_):
            INCLUDEOS_VMRUNNER=os.path.dirname(os.path.realpath(p_.locate()))

assert INCLUDEOS_VMRUNNER is not None

default_config = INCLUDEOS_VMRUNNER  + "/vm.userspace.json"

default_json = "./vm.json"

# Use INCLUDEOS_CHAINLOADER from environment if set, otherwise look for nix propagatedBuildInputs
chainloader = os.environ.get('INCLUDEOS_CHAINLOADER', None)
if chainloader is None:
    propagatedBuildInputs = os.environ.get('propagatedBuildInputs', None)
    if propagatedBuildInputs is not None:
        for c_path in propagatedBuildInputs.split(' '):
            chainloader_candidate = c_path + "/bin/chainloader"
            if os.path.isfile(chainloader_candidate):
                chainloader = c_path + "/bin"
                break

if chainloader is not None:
    chainloader = chainloader + "/chainloader"

# Provide a list of VM's with validated specs
# (One default vm added at the end)
vms = []

panic_signature = re.escape(r"\x15\x07\t**** PANIC ****")

# TODO: Consider adding hidden control characters here
#       to make it even less likely that this will appear in the wild
includeos_signature = "#include<os> // Literally"

nametag = "<VMRunner>"
INFO = color.INFO(nametag)
VERB = bool(os.environ["VERBOSE"]) if "VERBOSE" in os.environ else False

class Logger:
    """ Logger class """
    def __init__(self, tag):
        self.tag = tag
        if VERB:
            self.info = self.info_verb
        else:
            self.info = self.info_silent

    def __call__(self, *args):
        self.info(args)

    def info_verb(self, args):
        """ verbose mode version of info """
        print(self.tag, end=' ')
        for arg in args:
            print(arg, end=' ')
        print()

    def info_silent(self, args):
        """ silenced mode version of info """

# Define verbose printing function "info", with multiple args
default_logger = Logger(INFO)
def info(*args):
    """ verbose printing function with multiple args """
    default_logger.info(args)

# Example on Ubuntu:
# ELF 32-bit LSB executable, Intel 80386, version 1 (SYSV), statically linked, not stripped
# ELF 64-bit LSB executable, x86-64, version 1 (SYSV), statically linked, not stripped
#
# Example on mac (same files):
# ELF 32-bit LSB executable, Intel 80386, version 1 (SYSV), statically linked, not stripped, with debug_info
# ELF 64-bit LSB executable, x86-64, version 1 (SYSV), statically linked, not stripped, with debug_info
#
# Mac native:
# Mach-O 64-bit x86_64 executable, flags:<NOUNDEFS|DYLDLINK|TWOLEVEL|WEAK_DEFINES|BINDS_TO_WEAK|PIE>

def file_type(filename):
    """ calls the 'file' tool to determine file type """
    with subprocess.Popen(['file',filename],stdout=subprocess.PIPE,stderr=subprocess.STDOUT) as p:
        output, _ = p.communicate()
        return output.decode("utf-8")

def is_Elf64(filename):
    """ returns true if the file is an elf64 executable """
    magic = file_type(filename)
    return "ELF" in magic and "executable" in magic and "64-bit" in magic

def is_Elf32(filename):
    """ returns true if the file is an elf32 executable """
    magic = file_type(filename)
    return "ELF" in magic and "executable" in magic and "32-bit" in magic


# The end-of-transmission character
EOT = chr(4)

# Exit codes used by this program
exit_codes = {"SUCCESS" : 0,
              "PROGRAM_FAILURE" : 1,
              "TIMEOUT" : 66,
              "VM_PANIC" : 67,
              "CALLBACK_FAILED" : 68,
              "ABORT" : 70,
              "VM_EOT" : 71,
              "BOOT_FAILED": 72,
              "PARSE_ERROR": 73,
              "UNSAFE": 74
}

def get_exit_code_name (exit_code):
    """ convert exit code to string """
    for name, code in exit_codes.items():
        if code == exit_code:
            return name
    return "UNKNOWN ERROR"

def print_exception():
    """ We want to catch the exceptions from callbacks, but still tell the test writer what went wrong """
    exc_type, exc_value, exc_traceback = sys.exc_info()
    traceback.print_exception(exc_type, exc_value, exc_traceback,
                              limit=10, file=sys.stdout)


def have_sudo():
    """ Check for prompt-free sudo access """
    try:
        with open(os.devnull, 'w', encoding="utf-8") as devnull:
            subprocess.check_output(["sudo", "-n", "whoami"], stderr = devnull)
    except Exception as e:
        raise Exception("Sudo access required") from e

    return True

def cmd(cmdlist):
    """ Run a command, pretty print output, throw on error """
    res = subprocess.check_output(cmdlist)
    for line in res.rstrip().split("\n"):
        print(color.SUBPROC(line))

def abstract():
    """ internal method for abstract calls - only raises an exception """
    raise Exception("Abstract class method called. Use a subclass")

class hypervisor:
    """ Hypervisor base / super class """

    def __init__(self, config):
        self._config = config
        self._allow_sudo = False # must be explicitly turned on at boot.
        self._enable_kvm = False # must be explicitly turned on at boot.
        self._sudo = False       # Set to true if sudo is available
        self._proc = None        # A running subprocess
        self._tmp_dirs = []      # A list of tmp dirs created using tempfile module. Used for socket creation for automatic cleanup and garbage collection

    # pylint: disable-next=unused-argument
    def boot_in_hypervisor(self, multiboot=False, debug=False, kernel_args="", image_name="", allow_sudo = False, enable_kvm = False):
        """ Boot a VM, returning a hypervisor handle for reuse """
        abstract()

    def stop(self):
        """ Stop the VM booted by boot """
        abstract()

    def readline(self):
        """ Read a line of output from vm """
        abstract()

    # pylint: disable-next=unused-argument
    def available(self, config_data = None):
        """ Verify that the hypervisor is available """
        abstract()

    def wait(self):
        """ Wait for this VM to exit """
        abstract()

    def poll(self):
        """ Wait for this VM to exit """
        abstract()

    def name(self):
        """ A descriptive name """
        abstract()

    def image_name(self):
        """ Name of image """
        abstract()

    def start_process(self, cmdlist):
        """ Start hypervisor process """

        if cmdlist[0] == "sudo": # and have_sudo():

            if not self._allow_sudo:
                raise Exception("Hypervisor started with sudo, but sudo is not enabled")

            print(color.WARNING("Running with sudo"))
            self._sudo = True


        # Start a subprocess
        # pylint: disable-next=consider-using-with
        self._proc = subprocess.Popen(cmdlist,
                                      stdout = subprocess.PIPE,
                                      stderr = subprocess.STDOUT,
                                      stdin = subprocess.PIPE)

        return self._proc

    def has_process(self):
        """ Returns true if a hypervisor process has been started (but it may have crashed/exited) """
        return self._proc is not None

Solo5Tender = Enum('Solo5Type', ['hvt', 'spt'])

class solo5(hypervisor):
    """ Solo5 Hypervisor interface """

    def __init__(self, tender, config):
        # config is not yet used for solo5
        super().__init__(config)
        self._proc = None
        self._stopped = False
        self._sudo = False
        self._image_name = self._config if "image" in self._config else self.name() + " vm"
        self._tender = tender

        if tender == Solo5Tender.spt:
            self._solo5_bin = "solo5-spt"
        elif tender == Solo5Tender.hvt:
            self._solo5_bin = "solo5-hvt"
        else:
            raise NotImplementedError()

        # Pretty printing
        self.info = Logger(color.INFO("<" + type(self).__name__ + ">"))

    def name(self):
        return self._solo5_bin.title()

    def image_name(self):
        return self._image_name

    def drive_arg(self, filename, device_format="raw", media_type="disk"):
        """ returns disk argument for solo5 """
        if device_format != "raw":
            raise Exception("solo5 can only handle drives in raw format.")
        if media_type != "disk":
            raise Exception("solo5 can only handle drives of type disk.")
        return ["--disk=" + filename]

    def net_arg(self):
        """ returns net argument for solo5 """
        return ["--net=tap100"]

    def get_final_output(self):
        """ gets final output from hypervisor process """
        return self._proc.communicate()

    def boot_in_hypervisor(self, multiboot = False, debug = False, kernel_args = "", image_name = "", allow_sudo = False, enable_kvm = False):
        """ start hypervisor with the selected configuration (boot the VM) """

        self._allow_sudo = allow_sudo
        self._enable_kvm = enable_kvm
        self._stopped = False

        if not self._allow_sudo or not self._enable_kvm:
            raise Exception("Solo5 requires sudo and kvm enabled")

        # Use provided image name if set, otherwise raise an execption
        if not image_name:
            raise Exception("No image name provided as param")

        self._image_name = image_name

        command = ["sudo", self._solo5_bin]

        if not "drives" in self._config:
            command += self.drive_arg(self._image_name)
        elif len(self._config["drives"]) > 1:
            raise Exception("solo5/solo5 can only handle one drive.")
        else:
            for disk in self._config["drives"]:
                info ("Ignoring drive type argument: ", disk["type"])
                command += self.drive_arg(disk["file"], disk["format"],
                                          disk["media"])

        command += self.net_arg()
        command += [self._image_name]
        command += [kernel_args]

        try:
            self.info("Starting ", command)
            self.start_process(command)
            self.info("Started process PID ",self._proc.pid)
        except Exception as e:
            raise e

    def stop(self):

        signal_ = "-SIGTERM"

        # Don't try to kill twice
        if self._stopped:
            self.wait()
            return self

        self._stopped = True

        if self._proc and self._proc.poll() is None :

            if not self._sudo:
                info ("Stopping child process (no sudo required)")
                self._proc.terminate()
            else:
                # Find and terminate all child processes, since parent is "sudo"
                parent = psutil.Process(self._proc.pid)
                children = parent.children()

                info ("Stopping", self._image_name, "PID",self._proc.pid, "with", signal_)

                for child in children:
                    info (" + child process ", child.pid)

                    # The process might have gotten an exit status by now so check again to avoid negative exit
                    if not self._proc.poll():
                        subprocess.call(["sudo", "kill", signal_, str(child.pid)])

            # Wait for termination (avoids the need to reset the terminal etc.)
            self.wait()

        return self

    def wait(self):
        """ wait for self._proc """
        if self._proc:
            self._proc.wait()
        return self

    def read_until_EOT(self):
        """ read from stdout until EOT """
        chars = ""

        while not self._proc.poll():
            char = self._proc.stdout.read(1)
            if char == chr(4):
                return chars
            chars += char

        return chars


    def readline(self):
        """ read from stdout """
        if self._proc.poll():
            raise Exception("Process completed")
        return self._proc.stdout.readline().decode("utf-8", errors="replace")


    def writeline(self, line):
        """ write to stdin """
        if self._proc.poll():
            raise Exception("Process completed")
        return self._proc.stdin.write(line + "\n")

    def poll(self):
        """ poll _proc """
        return self._proc.poll()

class solo5_hvt(solo5):
    """ solo5 hvt interface """
    def __init__(self, config):
        super().__init__(Solo5Tender.hvt, config)

class solo5_spt(solo5):
    """ solo5 spt interface """
    def __init__(self, config):
        super().__init__(Solo5Tender.spt, config)

class qemu(hypervisor):
    """ Qemu Hypervisor interface """

    def __init__(self, config):
        super().__init__(config)
        self._proc = None
        self._virtiofsd_proc = None
        self._stopped = False
        self._sudo = False
        self._image_name = self._config if "image" in self._config else self.name() + " vm"
        self.m_drive_no = 0

        self._kvm_present = False # Set when KVM detected

        # TODO: Consider regex expecting a version number here
        self._bios_signature = "SeaBIOS (version"
        self._past_bios = False
        self._reboots = 0

        # Pretty printing
        self.info = Logger(color.INFO("<" + type(self).__name__ + ">"))

    def name(self):
        return "Qemu"

    def image_name(self):
        return self._image_name

    def drive_arg(self, filename, device = "virtio", drive_format = "raw", media_type = "disk"):
        """ create the drive/device arguments based on the configuration """
        names = {"virtio" : "virtio-blk",
                 "virtio-scsi" : "virtio-scsi",
                 "ide"    : "piix3-ide",
                 "nvme"   : "nvme"}

        if device == "ide":
            # most likely a problem relating to bus, or wrong .drive
            return ["-drive","file=" + filename
                    + ",format=" + drive_format
                    + ",if=" + device
                    + ",media=" + media_type]

        # Get device name if present, if not use the old name as default
        device = names.get(device, device)

        driveno = "drv" + str(self.m_drive_no)
        self.m_drive_no += 1
        return ["-drive", "file=" + filename + ",format=" + drive_format
                        + ",if=none" + ",media=" + media_type + ",id=" + driveno,
                "-device",  device + ",drive=" + driveno +",serial=foo"]

    # -initrd "file1 arg=foo,file2"
    # This syntax is only available with multiboot.

    def mod_args(self, mods):
        """ creates modules argument for hypervisor """
        mods_list =",".join([mod["path"] + ((" " + mod["args"]) if "args" in mod else "")
                             for mod in mods])
        return ["-initrd", mods_list]

    def net_arg(self, backend, device, if_name = "net0", mac = None, bridge = None, scripts = None):
        """ creates network argument for hypervisor """
        if scripts:
            qemu_ifup = scripts + "qemu-ifup"
            qemu_ifdown = scripts + "qemu-ifdown"
        else:
            qemu_ifup = INCLUDEOS_VMRUNNER + "/bin/qemu-ifup"
            qemu_ifdown = INCLUDEOS_VMRUNNER + "/bin/qemu-ifdown"

        # FIXME: this needs to get removed, e.g. fetched from the schema
        names = {"virtio" : "virtio-net", "vmxnet" : "vmxnet3", "vmxnet3" : "vmxnet3"}

        # Get device name if present, if not use the old name as default
        device = names.get(device, device)

        # Network device - e.g. host side of nic
        netdev = backend + ",id=" + if_name

        if backend == "tap":
            if not self._allow_sudo:
                raise Exception("Configuring a tap device requires --sudo, which is not enabled")

            if self._kvm_present:
                netdev += ",vhost=on"

            netdev += ",script=" + qemu_ifup + ",downscript=" + qemu_ifdown

        if backend == "bridge" and bridge is None:
            bridge = "bridge43"

        if bridge:
            netdev = "bridge,id=" + if_name + ",br=" + bridge


        # Device - e.g. guest side of nic
        device += ",netdev=" + if_name

        # Add mac-address if specified
        if mac:
            device += ",mac=" + mac
        device += ",romfile=" # remove some qemu boot info (experimental)

        return ["-device", device,
                "-netdev", netdev]

    def init_virtiocon(self, path):
        """ creates a console device and redirects to the path given """
        qemu_args = ["-device", "virtio-serial-pci,disable-legacy=on,id=virtio-serial0"]
        qemu_args += ["-device", "virtserialport,chardev=virtiocon0"]
        qemu_args += ["-chardev", f"file,id=virtiocon0,path={path}"]

        return qemu_args

    def init_virtiofs(self, socket, shared, mem):
        """ initializes virtiofs by launching virtiofsd and creating a virtiofs device """
        virtiofsd_args = ["virtiofsd", "--socket", socket, "--shared-dir", shared, "--sandbox", "none"]
        self._virtiofsd_proc = subprocess.Popen(virtiofsd_args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) # pylint: disable=consider-using-with

        if self._virtiofsd_proc.poll():
            raise Exception("VirtioFSD failed to start")

        info("Successfully started VirtioFSD!")

        while not os.path.exists(socket):
            ...

        qemu_args = ["-machine", "memory-backend=mem0"]
        qemu_args += ["-chardev", f"socket,id=virtiofsd0,path={socket}"]
        qemu_args += ["-device", "vhost-user-fs-pci,chardev=virtiofsd0,tag=vfs"]
        qemu_args += ["-object", f"memory-backend-memfd,id=mem0,size={mem}M,share=on"]

        return qemu_args

    def init_pmem(self, path, size, pmem_id):
        """ creates a pmem device with image path as memory mapped backend """
        qemu_args = ["-object", f"memory-backend-file,id=pmemdev{pmem_id},mem-path={path},size={size}M,share=on"]
        qemu_args += ["-device", f"virtio-pmem-pci,memdev=pmemdev{pmem_id}"]

        return qemu_args

    def kvm_present(self):
        """ returns true if KVM is present and available """
        if not self._enable_kvm:
            self.info("KVM OFF")
            return False

        if not self._allow_sudo:
            raise Exception("KVM is enabled, which requires sudo, but sudo is not enabled")

        command = "egrep -m 1 '^flags.*(vmx|svm)' /proc/cpuinfo"
        try:
            subprocess.check_output(command, shell = True)
            self.info("KVM ON")
            return True

        except Exception:
            self.info("KVM OFF")
            return False

    # Check if we should use the hvf accel (MacOS only)
    def hvf_present(self):
        """ returns true if Hypervisor.framework is available (Darwin/mac only) """
        return platform.system() == "Darwin"

    # Start a process and preserve in- and output pipes
    # Note: if the command failed, we can't know until we have exit status,
    # but we can't wait since we expect no exit. Checking for program start error
    # is therefore deferred to the callee

    def get_final_output(self):
        """ get final output from hypervisor process """
        return self._proc.communicate()

    def boot_in_hypervisor(self, multiboot=True, debug = False, kernel_args = "", image_name = None, allow_sudo = False, enable_kvm = False):
        """" boot VM in hypervisor """

        self._allow_sudo = allow_sudo
        self._enable_kvm = enable_kvm
        self._stopped = False

        info ("Booting with multiboot:", multiboot, "kernel_args: ", kernel_args, "image_name:", image_name,
              "allow_sudo:", allow_sudo)

        # Resolve if kvm is present
        self._kvm_present = self.kvm_present()

        # Use provided image name if set, otherwise try to find it in json-config
        if not image_name:
            if not "image" in self._config:
                raise Exception("No image name provided, neither as param or in config file")
            image_name = self._config["image"]

        self._image_name = image_name

        disk_args = []

        debug_args = []
        if debug:
            debug_args = ["-s", "-S"]

        # multiboot - e.g. boot with '-kernel' and no bootloader
        if multiboot:

            # TODO: Remove .img-extension from vm.json in tests to avoid this hack
            if image_name.endswith(".img"):
                image_name = image_name.split(".")[0]

            if not kernel_args:
                kernel_args = "\"\""

            info ("File magic: ", file_type(image_name))

            if is_Elf64(image_name):
                info ("Found 64-bit ELF, need chainloader" )
                print("Looking for chainloader: ")
                if chainloader is None or not os.path.isfile(chainloader):
                    print("Error: couldn't find chainloader. Try -g for grub, or create an .img with vmbuild.")
                    sys.exit(1)

                print("Found", chainloader, "Type: ",  file_type(chainloader))
                if not is_Elf32(chainloader):
                    print(color.WARNING("Chainloader doesn't seem to be a 32-bit ELF executable"))
                kernel_args = ["-kernel", chainloader, "-append", kernel_args, "-initrd", image_name + " " + kernel_args]
            elif is_Elf32(image_name):
                info ("Found 32-bit elf, trying direct boot")
                kernel_args = ["-kernel", image_name, "-append", kernel_args]
            else:
                print(color.WARNING("Provided kernel is neither 64-bit or 32-bit ELF executable."))
                kernel_args = ["-kernel", image_name, "-append", kernel_args]

            info ( "Booting", image_name, "directly without bootloader (multiboot / -kernel args)")
        else:
            kernel_args = []
            image_in_config = False

            # If the provided image name is also defined in vm.json, use vm.json
            if "drives" in self._config:
                for disk in self._config["drives"]:
                    if disk["file"] == image_name:
                        image_in_config = True
                if not image_in_config:
                    info ("Provided image", image_name, "not found in config. Appending.")
                    self._config["drives"].insert(0, {"file" : image_name, "type":"ide", "format":"raw", "media":"disk"})
            else:
                self._config["drives"] =[{"file" : image_name, "type":"ide", "format":"raw", "media":"disk"}]

            info ("Booting", image_name, "with a bootable disk image")

        if "drives" in self._config:
            for disk in self._config["drives"]:
                disk_args += self.drive_arg(disk["file"], disk["type"], disk["format"], disk["media"])

        mod_args = []
        if "modules" in self._config:
            mod_args += self.mod_args(self._config["modules"])

        if "bios" in self._config:
            kernel_args.extend(["-bios", self._config["bios"]])

        if "uuid" in self._config:
            kernel_args.extend(["--uuid", str(self._config["uuid"])])

        if "smp" in self._config:
            kernel_args.extend(["-smp", str(self._config["smp"])])

        if "cpu" in self._config:
            cpu = self._config["cpu"]
            cpu_str = cpu["model"]
            if "features" in cpu:
                cpu_str += ",+" + ",+".join(cpu["features"])
            kernel_args.extend(["-cpu", cpu_str])

        net_args = []
        i = 0
        if "net" in self._config:
            for net in self._config["net"]:
                mac = net["mac"] if "mac" in net else None
                bridge = net["bridge"] if "bridge" in net else None
                scripts = net["scripts"] if "scripts" in net else None
                net_args += self.net_arg(net["backend"], net["device"], "net"+str(i), mac, bridge, scripts)
                i+=1

        mem_arg = []
        if "mem" in self._config:
            mem_arg = ["-m", f"size={self._config["mem"]},maxmem=1000G"]

        vga_arg = ["-nographic" ]
        if "vga" in self._config:
            vga_arg = ["-vga", str(self._config["vga"])]

        trace_arg = []
        if "trace" in self._config:
            trace_arg = ["-trace", "events=" + str(self._config["trace"])]

        pci_arg = []
        if "vfio" in self._config:
            pci_arg = ["-device", "vfio-pci,host=" + self._config["vfio"]]

        virtiocon_args = []
        if "virtiocon" in self._config:
            virtiocon_args = self.init_virtiocon(self._config["virtiocon"]["path"])

        virtiofs_args = []
        if "virtiofs" in self._config:
            tmp_virtiofs_dir = tempfile.TemporaryDirectory(prefix="virtiofs-") # pylint: disable=consider-using-with
            self._tmp_dirs.append(tmp_virtiofs_dir)
            socket_path = os.path.join(tmp_virtiofs_dir.name, "virtiofsd.sock")

            shared = self._config["virtiofs"]["shared"]

            virtiofs_args = self.init_virtiofs(socket_path, shared, self._config["mem"])

        virtiopmem_args = []
        if "virtiopmem" in self._config:
            for pmem_id, virtiopmem in enumerate(self._config["virtiopmem"]):
                image = virtiopmem["image"]
                size = virtiopmem["size"]
                virtiopmem_args += self.init_pmem(image, size, pmem_id)

        # custom qemu binary/location
        qemu_binary = "qemu-system-x86_64"
        if "qemu" in self._config:
            qemu_binary = self._config["qemu"]


        command = []
        if self._allow_sudo:
            command.append("sudo")

        command.append(qemu_binary)

        if self._kvm_present and self._enable_kvm:
            command.extend(["--enable-kvm"])

        # If hvf is present, use it and enable cpu features (needed for rdrand/rdseed)
        if self.hvf_present():
            command.extend(["-accel","hvf"])

        # Set -cpu correctly if not specified in config
        if not "cpu" in self._config:
            if self._kvm_present:
                command.extend(["-cpu","kvm64,+rdrand,+rdseed"])
            if self.hvf_present():
                command.extend(["-cpu","host"])


        command += kernel_args
        command += disk_args + debug_args + net_args + mem_arg + mod_args
        command += vga_arg + trace_arg + pci_arg + virtiocon_args + virtiofs_args
        command += virtiopmem_args

        #command_str = " ".join(command)
        #command_str.encode('ascii','ignore')
        #command = command_str.split(" ")

        info("Command:", " ".join(command))

        try:
            self.start_process(command)
            self.info("Started process PID ",self._proc.pid)
        except Exception as e:
            print(self.info,"Starting subprocess threw exception:", e)
            raise e

    def stop(self):

        signal_ = "-SIGTERM"

        # Don't try to kill twice
        if self._stopped:
            self.wait()
            return self

        self._stopped = True

        if self._proc and self._proc.poll() is None :

            if not self._sudo:
                info ("Stopping child process (no sudo required)")
                self._proc.terminate()
            else:
                # Find and terminate all child processes, since parent is "sudo"
                parent = psutil.Process(self._proc.pid)
                children = parent.children()

                info ("Stopping", self._image_name, "PID",self._proc.pid, "with", signal_)

                for child in children:
                    info (" + child process ", child.pid)

                    # The process might have gotten an exit status by now so check again to avoid negative exit
                    if not self._proc.poll():
                        subprocess.call(["sudo", "kill", signal_, str(child.pid)])

            # Wait for termination (avoids the need to reset the terminal etc.)
            self.wait()

        return self

    def wait(self):
        """ wait for hypervisor process to exit """
        if self._proc:
            self._proc.wait()
        return self

    def read_until_EOT(self):
        """ read output from hypervisor until EOT character found """
        chars = ""

        while not self._proc.poll():
            char = self._proc.stdout.read(1).decode("utf-8", errors="replace")
            if char == chr(4):
                return chars
            chars += char

        return chars



    def readline(self, filter_all_control_chars = False):
        if self._proc.poll():
            raise Exception("Process completed")

        # SeaBIOS emits a lot of control characters, which looses important information,
        # like the number of reboots and the earliest output from IncludeOS. It also ruins your
        # terminal, by disabling line wrapping, clearing screen, moving cursor etc.
        #
        # At the time of writing, exactly what it emits is this:
        # \x1bc\x1b[?7l\x1b[2J\x1b[0mSeaBIOS (version 1.16.3-debian-1.16.3-2)\r\nBooting from Hard Disk...\r\n\x1b[H\x1b[J\x1b[1;1H
        #
        # If they ever change this, we might want to use thhe more comprehensive approach for
        # cleaning control chars using regexes below, but for now the cheapest seems to be
        # plain string matching.
        #
        if not filter_all_control_chars:
            line = self._proc.stdout.readline().decode("utf-8", errors="replace")

            # Known control sequences to be trimmed
            SeaBIOS_start = "\x1bc\x1b[?7l\x1b[2J\x1b[0m"
            SeaBIOS_end = "\x1b[H\x1b[J\x1b[1;1H"

            # Trim the start sequence if present
            if SeaBIOS_start + "SeaBIOS" in line:
                line = line.split(SeaBIOS_start, 1)[-1]
                if self._reboots > 0:
                    print(color.WARNING(f"Reboot detected, #{self._reboots}"))
                self._reboots += 1

            # Trim the end sequence (it's on its own line, so remove the whole thing)
            if SeaBIOS_end in line:
                line = ""

            return line

        # Alternative path in case we want to filter all control chars from other sources as well.
        control_sequence_pattern = re.compile(r'\x1b.*?[a-zA-Z]')

        # We need to process each character as a raw byte to preserve unicode
        clean_buffer = bytearray()
        control_buffer = bytearray()
        inside_control_sequence = False
        while True:

            # TODO: find out how slow this is.
            # if it's not reading from an in-process buffer we should buffer here.
            char = self._proc.stdout.read(1)

            if not char:
                break

            if char == b'\n':
                clean_buffer.append(char[0])
                break

            if char == b'\x1B':
                inside_control_sequence = True
                control_buffer.append(char[0])

            elif inside_control_sequence:
                control_buffer.append(char[0])
                if control_sequence_pattern.match(control_buffer.decode("utf-8", errors="replace")):
                    # Complete control sequence found, discard buffer
                    inside_control_sequence = False
                    control_buffer = bytearray()

            else:
                clean_buffer.append(char[0])

        string = clean_buffer.decode("utf-8", errors="replace")

        if includeos_signature in string:
            self._past_bios = True

        if self._past_bios and self._bios_signature in string:
            print(color.WARNING("Reboot detected"))

        return string


    def writeline(self, line):
        """ write line to hypervisor stdin """
        if self._proc.poll():
            raise Exception("Process completed")
        return self._proc.stdin.write(line + "\n")

    def poll(self):
        """ poll hypervisor process for output """
        return self._proc.poll()

# VM class
class vm:
    """ VM management class """

    def __init__(self, config = None, hyper_name = "qemu"):
        """ initialise VM config with specified hypervisor """

        self._stopping = False
        self._exit_status = None
        self._exit_msg = ""
        self._exit_complete = False

        self._allow_sudo = False # Set by boot()
        self._enable_kvm = False # Set by boot()

        self._config = load_with_default_config(True, config)
        self._on_success = lambda line : self.exit(exit_codes["SUCCESS"], nametag + " All tests passed")
        self._on_unsafe = lambda line : self.exit(exit_codes["UNSAFE"], nametag + " Tests passed with warnings")
        self._on_panic =  self.panic
        self._on_timeout = self.timeout
        self._on_output = {
            panic_signature : self._on_panic,
            "FATAL: Random source check failed" : self._on_unsafe,
            "SUCCESS" : self._on_success }

        if hyper_name == "solo5-spt":
            hyper = solo5_spt
        elif hyper_name == "solo5-hvt":
            hyper = solo5_hvt
        else:
            hyper = qemu

        # Initialize hypervisor with config
        assert issubclass(hyper, hypervisor)
        self._hyper  = hyper(self._config)
        self._timeout_after = None
        self._timer = None
        self._on_exit_success = lambda : None
        self._on_exit = lambda : None
        self._root = os.getcwd()
        self._kvm_present = False

    def stop(self):
        """ stop hypervisor """
        self.flush()
        self._hyper.stop().wait()
        if self._timer:
            self._timer.cancel()
        return self

    def flush(self):
        """ read and output remaining lines from hypervisor """
        if not self._hyper.has_process():
            return

        while self._exit_status is None and self.poll() is None:
            try:
                line = self._hyper.readline()
            except Exception as e:
                # We might be blocked on self._hyper.readline() when a signal handler tells us to stop
                # because it stops us by sending sigterm to the parent process and all children.
                # In that case an exception is expected, but not otherwise.
                if signal is None:
                    print(color.WARNING(f"Exception thrown while waiting for vm output: {e}"))
                break

            if line and (self.find_exit_status(line) is None):
                print(color.VM(line.rstrip()))
                self.trigger_event(line)

            # Empty line - should only happen if process exited
            else:
                pass


    def wait(self):
        """ wait """
        if hasattr(self, "_timer") and self._timer:
            self._timer.join()
        self._hyper.wait()
        return self._exit_status

    def poll(self):
        """ poll """
        return self._hyper.poll()

    def exit(self, status, msg, keep_running = False):
        """ Stop the VM with exit status / msg. Set keep_running to indicate that the program should continue """

        # Exit may have been called allready
        if self._exit_complete:
            return

        self._exit_status = status
        self._exit_msg = msg
        self.stop()

        # Change back to test source
        os.chdir(self._root)


        info("Exit called with status", self._exit_status, "(",get_exit_code_name(self._exit_status),")")
        info("Message:", msg, "Keep running: ", keep_running)

        if keep_running:
            return

        if self._on_exit:
            info("Calling on_exit")
            self._on_exit()


        if status == 0:
            if self._on_exit_success:
                info("Calling on_exit_success")
                self._on_exit_success()

            print(color.SUCCESS(msg))
            self._exit_complete = True
            return

        self._exit_complete = True
        program_exit(status, msg)

    def timeout(self):
        """ Default timeout event """
        if VERB:
            print(color.INFO("<timeout>"), "VM timed out")

        # Note: we have to stop the VM since the main thread is blocking on vm.readline
        self._exit_status = exit_codes["TIMEOUT"]
        self._exit_msg = "vmrunner timed out after " + str(self._timeout_after) + " seconds"
        self._hyper.stop().wait()

    def panic(self, _):
        """ Default panic event """
        panic_reason = self._hyper.readline()
        info("VM signalled PANIC. Reading until EOT (", hex(ord(EOT)), ")")
        print(color.VM(panic_reason), end=' ')
        remaining_output = self._hyper.read_until_EOT()
        for line in remaining_output.split("\n"):
            print(color.VM(line))

        self.exit(exit_codes["VM_PANIC"], panic_reason)


    # Events - subscribable
    def on_output(self, output, callback):
        """ register on_output callback """
        self._on_output[ output ] = callback
        return self

    def on_success(self, callback, do_exit = True):
        """ register on_success callback """
        if do_exit:
            self._on_output["SUCCESS"] = lambda line : [callback(line), self._on_success(line)]
        else:
            self._on_output["SUCCESS"] = callback
        return self

    def on_panic(self, callback, do_exit = True):
        """ register on_panic callback """
        if do_exit:
            self._on_output[panic_signature] = lambda line : [callback(line), self._on_panic(line)]
        else:
            self._on_output[panic_signature] = callback
        return self

    def on_timeout(self, callback):
        """ register on_timeout callback """
        self._on_timeout = callback
        return self

    def on_exit_success(self, callback):
        """ register on_exit_success callback """
        self._on_exit_success = callback
        return self

    def on_exit(self, callback):
        """ register on_exit callback """
        self._on_exit = callback
        return self

    def readline(self):
        """ Read a line from the VM's standard out """
        return self._hyper.readline()

    def writeline(self, line):
        """ Write a line to VM stdout """
        return self._hyper.writeline(line)

    def find_exit_status(self, line):
        """ find exit status on output line """

        # Kernel reports service exit status
        if (line.startswith("     [ Kernel ] service exited with status") or
            line.startswith("     [ main ] returned with status")):

            self._exit_status = int(line.split(" ")[-1].rstrip())
            self._exit_msg = "Service exited with status " + str(self._exit_status)
            return self._exit_status

        # Special case for end-of-transmission, e.g. on panic
        if line == EOT:
            self._exit_status = exit_codes["VM_EOT"]
            return self._exit_status

        return None

    def trigger_event(self, line):
        """ Find any callback triggered by this line """
        for pattern, func in self._on_output.items():
            if re.search(pattern, str(line)):
                try:
                    # Call it
                    res = func(line)
                except Exception:
                    print(color.WARNING("Exception raised in event callback: "))
                    print_exception()
                    res = False
                    self.stop()

                # NOTE: Result can be 'None' without problem
                if res is False:
                    self._exit_status = exit_codes["CALLBACK_FAILED"]
                    self.exit(self._exit_status, " Event-triggered test failed")


    def boot(self, timeout = 60, multiboot = True, debug = False, kernel_args = "booted with vmrunner",
             image_name = None, allow_sudo = False, enable_kvm = False):
        """ Boot the VM and start reading output. This is the main event loop. """
        info ("VM boot, timeout: ", timeout, "multiboot: ", multiboot, "Kernel_args: ", kernel_args,
              "image_name: ", image_name, allow_sudo, "allow_sudo")

        self._allow_sudo = allow_sudo
        self._enable_kvm = enable_kvm

        # This might be a reboot
        self._exit_status = None
        self._exit_complete = False
        self._timeout_after = timeout

        # Start the timeout thread
        if timeout:
            info("setting timeout to",timeout,"seconds")
            self._timer = threading.Timer(timeout, self._on_timeout)
            self._timer.start()

        # Boot via hypervisor
        try:
            self._hyper.boot_in_hypervisor(multiboot, debug, kernel_args, image_name, allow_sudo, enable_kvm)
        except Exception as err:
            print(color.WARNING("Exception raised while booting: "))
            print_exception()
            if timeout:
                self._timer.cancel()
            self.exit(exit_codes["BOOT_FAILED"], str(err))

        # Start analyzing output
        while self._exit_status is None and self.poll() is None:

            try:
                line = self._hyper.readline()
            except Exception as e:
                print(color.WARNING(f"Exception thrown while waiting for vm output: {e}"))
                break

            if line and (self.find_exit_status(line) is None):
                print(color.VM(line.rstrip()))
                self.trigger_event(line)

            # Empty line - should only happen if process exited
            else:
                pass


        # VM Done
        info("Event loop done. Exit status:", self._exit_status, "poll:", self.poll())

        # If the VM process didn't exit by now we need to stop it.
        if self.poll() is None:
            self.stop()

        # Process may have ended without EOT / exit message being read yet
        # possibly normal vm shutdown
        if self.poll() is not None:

            info("No poll - getting final output")
            try:
                data, err = self._hyper.get_final_output()

                # Print stderr if exit status wasnt 0
                if err and self.poll() != 0:
                    print(color.WARNING("Stderr: \n" + err))

                # Parse the last output from vm
                lines = data.split("\n")
                for line in lines:
                    print(color.VM(line))
                    self.find_exit_status(line)
                    # Note: keep going. Might find panic after service exit

            except Exception:
                pass

        # We should now have an exit status, either from a callback or VM EOT / exit msg.
        if self._exit_status is not None:
            info("VM has exit status. Exiting.")
            self.exit(self._exit_status, self._exit_msg)
        else:
            self.exit(self._hyper.poll(), "process exited")

        # If everything went well we can return
        return self

def load_with_default_config(use_default, path = default_json):
    """ load user config, optionally return defaults with user specified values modified """

    # load default config
    conf = {}
    if use_default:
        info("Loading default config.")
        conf = load_config(default_config)

    # load user config (or fallback)
    user_conf = load_config(path)

    if user_conf:
        if not use_default:
            # return user_conf as is
            return user_conf

        # extend (override) default config with user config
        for key, value in user_conf.items():
            conf[key] = value
        info(str(conf))

    return conf

def load_config(path):
    """ Load a vm config """

    config = {}
    description = None

    # If path is explicitly "None", try current dir
    if not path:
        path = default_json

    info("Trying to load config from", path)

    if os.path.isfile(path):

        try:
            # Try loading the first valid config
            config = validate_vm.load_config(path)
            info ("Successfully loaded vm config")

        except Exception as e:
            print_exception()
            info("Could not parse VM config file(s): " + path)
            program_exit(73, str(e))

    elif os.path.isdir(path):
        try:
            configs = validate_vm.load_config(path, VERB)
            info ("Found ", len(configs), "config files")
            config = configs[0]
            info ("Trying the first valid config ")
        except Exception as e:
            info("No valid config found: ", e)
            program_exit(73, "No valid config files in " + path)


    if "description" in config:
        description = config["description"]
    else:
        description = str(config)

    info('"',description,'"')

    return config


def program_exit(status, msg):
    """ print message, stop VMs and exit program with specified exit code """

    info("Program exit called with status", status, "(",get_exit_code_name(status),")")
    info("Stopping all vms")

    for vm_ in vms:
        vm_.stop().wait()

    # Print status message and exit with appropriate code
    if get_exit_code_name(status) == "UNSAFE":
        print(color.WARNING("Do not rely on this image for secure applications."))
        status = 0
    if status != 0:
        print(color.EXIT_ERROR(get_exit_code_name(status), msg))
    else:
        print(color.SUCCESS(msg))

    sys.exit(status)


def add_vm(**kwargs):
    """ Call this to add a new vm to the vms list as well. This ensures proper termination """
    new_vm = vm(**kwargs)
    vms.append(new_vm)
    return new_vm

def handler(signum, _):
    """ Handler for signals """
    print(color.WARNING(f"Process interrupted by signal {signum} - stopping vms"))
    for vm_ in vms:
        try:
            vm_.exit(exit_codes["ABORT"], "Process terminated by user")
        except Exception as e:
            print(color.WARNING("Forced shutdown caused exception: "), e)
            raise e


# One unconfigured vm is created by default, which will try to load a config if booted
vms.append(vm())

signal.signal(signal.SIGTERM, handler)
signal.signal(signal.SIGINT, handler)
