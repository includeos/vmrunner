{ pkgs ? import <nixpkgs> { } }:
let
  pythonEnv = pkgs.python3.withPackages(python-pkgs: [
    python-pkgs.future
    python-pkgs.jsonschema
    python-pkgs.psutil
  ]);

in
  pkgs.mkShell {
    INCLUDEOS_VMRUNNER=builtins.toString ./.;
    PYTHONPATH=builtins.toString ./.;

    buildInputs = [
      pkgs.qemu
    ];

    packages = [
      pythonEnv
    ];
  }
