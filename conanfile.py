import os
from conans import ConanFile, python_requires

conan_tools = python_requires("conan-tools/[>=1.0.0]@includeos/stable")

class VmrunnerConan(ConanFile):
    name = "vmrunner"
    version = conan_tools.git_get_semver()
    license = "Apache-2.0"
    description = "A set of tools for booting IncludeOS binaries as VM's"
    scm = {
        "type" : "git",
        "url" : "auto",
        "subfolder": ".",
        "revision" : "auto"
    }
    no_copy_source=True
    default_user="includeos"
    default_channel="test"

    def package(self):
        self.copy("*", dst="vmrunner", src="vmrunner")
        self.copy("*", dst="bin", src="bin")

    def package_info(self):
        self.env_info.PYTHONPATH.append(self.package_folder)
        self.env_info.INCLUDEOS_VMRUNNER=(os.path.join(self.package_folder))
        self.env_info.path.append((os.path.join(self.package_folder, "bin")))

    def deploy(self):
        self.copy("*", dst="vmrunner",src="vmrunner")
        self.copy("*", dst="bin",src="bin")
