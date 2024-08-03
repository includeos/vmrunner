{ pkgs ? import <nixpkgs> {} }:
pkgs.python3.pkgs.buildPythonPackage rec {
  pname = "vmrunner";
  version = "0.16.0";
  src = ./.;  # Use the current directory as the source
  pyproject = true;
  dontUseSetuptoolsCheck = true;

  build-system = with pkgs.python3.pkgs; [
    setuptools
    setuptools-scm
  ];

  dependencies = with pkgs.python3.pkgs; [
    future
    jsonschema
    psutil
  ];

  meta = {
    description = "A convenience wrapper around qemu for IncludeOS integration tests";
    license = pkgs.lib.licenses.asl20;
  };
}
