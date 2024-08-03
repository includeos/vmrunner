{ pkgs ? import <nixpkgs> { } }:
let
  vmrunner = pkgs.callPackage ./default.nix {  };
in
pkgs.mkShell rec {
    buildInputs = [
      pkgs.qemu
    ];

    packages = [
      vmrunner
    ];

    # This binary must be added to the sudoers list to enable bridged networking
    qemu_bridge_helper = "${pkgs.qemu}/libexec/qemu-bridge-helper";

    # In addition, you'll need /etc/qemu/bridge.conf to contain this line:
    # allow bridge43
    # This bridge can be set up with /bin/create_bridge.sh
    create_bridge = vmrunner.create_bridge;

    shellHook = ''
      echo ""
      echo "================= vmrunner example shell ================="
      echo "The vmrunner for IncludeOS tests requires bridged networking for full functionality."
      echo "In order to use bridge networking, you need the following:"
      echo "1. the qemu-bridge-helper needs sudo. Can be enabled with:"
      echo "   sudo chmod u+s ${qemu_bridge_helper}"
      echo "2. bridge43 must exist. Can be set up with \$create_bridge :"
      echo "   ${vmrunner.create_bridge}"
      echo "3. /etc/qemu/bridge.conf must contain this line:"
      echo "   allow bridge43"
      echo "These steps require sudo. Without them we're restricted to usermode networking."
      echo
    '';
}
