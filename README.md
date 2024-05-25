# vmrunner
Utilities for booting [IncludeOS](https://github.com/includeos/includeos) binaries - _for testing and development only_. 

- `vmrunner.py` - a convenience wrapper around qemu, used by IncludeOS integration tests
- `boot`        - a command line tool using vmrunner.py, that boots IncludeOS binaries with qemu
- `grubify.sh`  - a script to create a bootable grub image from an IncludeOS binary


## Installing
Install python3 venv, `sudo apt install python3.12-venv` on ubuntu 24.24. Then create a venv:
```
$ python3 -m venv venv
$ source venv/bin/activate
$ pip install -r requirements.txt
```
Consider adding `vmrunner/bin` to your path to make the `boot` command available everywhere:
```
# For boot and tests to find vmrunner.py
$ export INCLUDEOS_VMRUNNER=<absolute-path-to-vmrunner>

# For `boot` to be available anywhere
$ export PATH=$INCLUDEOS_VMRUNNER/bin:$PATH

# To make python3 from your venv be the first python, which will then start boot
$ export PATH=$INCLUDEOS_VMRUNNER/venv/bin:$PATH
```
If you've built a chainloader, boot might be faster as it can use qemu's `-kernel` argument and not spend time building a grub filesystem.
```
$ export INCLUDEOS_CHAINLOADER=<your-includeos-chainloader-pkg>/bin/chainloader
```
If you don't have a chainloader, use `boot -g <your binary>` to create a grub image. Requires `grub-pc` to be installed.

## Note: conan / jenkins deprecated.
The Conanfile / Jenkinsfile is no longer maintained and will probably be removed
