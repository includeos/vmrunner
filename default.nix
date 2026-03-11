{ pkgs ? import <nixpkgs> {} }:
pkgs.python3.pkgs.buildPythonPackage rec {
  pname = "vmrunner";
  version = "0.16.0";
  src = ./.;  # Use the current directory as the source
  pyproject = true;
  dontUseSetuptoolsCheck = true;
  doCheck = true;

  build-system = with pkgs.python3.pkgs; [
    setuptools
    setuptools-scm
  ];

  dependencies = with pkgs.python3.pkgs; [
    jsonschema
    psutil
  ];

  create_bridge = ./vmrunner/bin/create_bridge.sh;

  passthru = {
    inherit create_bridge;
  };

  meta = {
    description = "A convenience wrapper around qemu for IncludeOS integration tests";
    license = pkgs.lib.licenses.asl20;
  };

  nativeCheckInputs = [
    pkgs.shellcheck
    pkgs.pylint
  ];

  checkPhase = ''
    for f in vmrunner/bin/{*.sh,qemu-ifup,qemu-ifdown}; do
      echo Checking "$f" with shellcheck
      shellcheck "$f"
    done

    for f in vmrunner/*.py; do
      echo Checking $f with pylint
      pylint --persistent no "$f"
    done
  '';

}
