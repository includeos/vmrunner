# vmrunner
Utilities for booting [IncludeOS](https://github.com/includeos/includeos) binaries - _for testing and development only_.

- `vmrunner.py` - a convenience wrapper around qemu, used by IncludeOS integration tests
- `boot`        - a command line tool using vmrunner.py, that boots IncludeOS binaries with qemu
- `grubify.sh`  - a script to create a bootable grub image from an IncludeOS binary


By default, the `boot` tool requires the `INCLUDEOS_CHAINLOADER` environment to
be defined, and pointing to a directory containing an IncludeOS chainloader.


## Installing with nix
The supported way of using vmrunner is via nix. For example, in your nix shell, you can add:

```nix
vmrunner = pkgs.callPackage (builtins.fetchGit {
  url = "https://github.com/includeos/vmrunner";
}) {};
```
After which `vmrunner` can be added as a package:
```
packages = [
  vmrunner
  ...
]
```

An example shell.nix is provided here as well, which can be used as follows:

```
$ nix-shell

Executing pythonImportsCheckPhase

================= vmrunner example shell =================
The vmrunner for IncludeOS tests requires bridged networking for full functionality.
In order to use bridge networking, you need the following:
1. the qemu-bridge-helper needs sudo. Can be enabled with:
   sudo chmod u+s /nix/store/ij3945kiq3p26vilqlc3ck5gvmrjsa2c-qemu-8.2.4/libexec/qemu-bridge-helper
2. bridge43 must exist. Can be set up with $create_bridge :
   /nix/store/9qhp9w3fkb7dh6q4647v889fmfaya7hs-create_bridge.sh
3. /etc/qemu/bridge.conf must contain this line:
   allow bridge43
These steps require sudo. Without them we're restricted to usermode networking.

```

Note the generated instructions for enabling bridged networking. Once the bridge is avalable, any of
the IncludeOS examples and integration tests should be able to boot:

```
$ export INCLUDEOS_CHAINLOADER=$(nix-build <path-to-IncludeOS>/chainloader.nix)/bin/
$ boot ./your/includeos/unikernel.elf.bin
```

## Installing and running with pipx
Installing and running with pipx should work as recommended here: https://packaging.python.org/en/latest/guides/creating-command-line-tools/#installing-the-package-with-pipx .

```
pipx install .
``

Will by default install boot locally to your `$HOME/.local/bin`. It can also be run directly from `pipx` without installation.

**Example:**
```
$ cd ~/IncludeOS
$ export INCLUDEOS_CHAINLOADER=$(nix-build chainloader.nix)/bin
$ pipx run --spec ~/vmrunner/ boot $(nix-build example.nix)/bin/hello_includeos.elf.bin
Looking for chainloader:
Found /nix/store/524d584z9apnbrnl5i6gzza9wsijj846-chainloader-static-i686-unknown-linux-musl-dev/bin/chainloader Type:  /nix/store/524d584z9apnbrnl5i6gzza9wsijj846-chainloader-static-i686-unknown-linux-musl-dev/bin/chainloader: ELF 32-bit LSB executable, Intel 80386, version 1 (SYSV), statically linked, not stripped

SeaBIOS (version 1.16.3-debian-1.16.3-2)
Booting from ROM..* Multiboot begin: 0x9500
* Multiboot cmdline @ 0x234092: /nix/store/524d584z9apnbrnl5i6gzza9wsijj846-chainloader-static-i686-unknown-linux-musl-dev/bin/chainloader ""
* Multiboot end: 0x234100
* Module list @ 0x234000
...
================================================================================

                           #include<os> // Literally

================================================================================
     [ Kernel ] Stack: 0x1ffbe8
     [ Kernel ] Boot magic: 0x2badb002, addr: 0x9500
     [ x86_64 ] Initializing paging
...
```



## Setting up a network bridge



## Note: conan / jenkins deprecated.
The Conanfile / Jenkinsfile is no longer maintained and will probably be removed
