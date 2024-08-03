{ pkgs ? import <nixpkgs> { } }:
let
  vmrunner = pkgs.callPackage ./default.nix {  };
in
pkgs.mkShell {
    buildInputs = [
      pkgs.qemu
    ];

    packages = [
      vmrunner
    ];
}
