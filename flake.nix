{
  description = "A convenience wrapper around qemu for IncludeOS integration tests";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/25.05";
  };

  outputs = { self, nixpkgs }:
    let
      system = "x86_64-linux";
      pkgs = import nixpkgs { inherit system; };

      vmrunner = pkgs.callPackage ./default.nix {};

      vmconfig = import ./vmconfig.nix { inherit pkgs; };
      boot = import ./boot.nix { inherit pkgs vmrunner; };

      mkBoot = chainloader:
      { mem ? "128m" }:
        let
          cfg = vmconfig.mkConfig { inherit mem; };
        in
          boot.mkBoot chainloader { vm = cfg; };

    in {
      packages.${system}.default = vmrunner;

      devShells.${system}.default = import ./shell.nix { inherit pkgs; };

      lib.${system}.mkBoot = mkBoot;

      apps.${system}.default = {
        type = "app";
        program = "${vmrunner}/bin/boot";
      };

    };
}
