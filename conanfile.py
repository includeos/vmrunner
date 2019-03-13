import os
from conans import ConanFile,tools

def get_version():
    git = tools.Git()
    try:
        prev_tag = git.run("describe --tags --abbrev=0")
        commits_behind = int(git.run("rev-list --count %s..HEAD" % (prev_tag)))
        # Commented out checksum due to a potential bug when downloading from bintray
        #checksum = git.run("rev-parse --short HEAD")
        if prev_tag.startswith("v"):
            prev_tag = prev_tag[1:]
        if commits_behind > 0:
            prev_tag_split = prev_tag.split(".")
            prev_tag_split[-1] = str(int(prev_tag_split[-1]) + 1)
            output = "%s-%d" % (".".join(prev_tag_split), commits_behind)
        else:
            output = "%s" % (prev_tag)
        return output
    except:
        return '0.0.0'


class VmrunnerConan(ConanFile):
    name = "vmrunner"
    version = get_version()
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
        self.copy("*", dst="bin", src="scripts")

    def package_info(self):
        self.env_info.PYTHONPATH.append(self.package_folder)
        self.env_info.INCLUDEOS_VMRUNNER=(os.path.join(self.package_folder))
        self.env_info.path.append((os.path.join(self.package_folder, "bin")))

    def deploy(self):
        self.copy("*", dst="vmrunner",src="vmrunner")
        self.copy("*", dst="bin",src="bin")
