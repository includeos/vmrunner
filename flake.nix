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
    in {
      packages.${system}.default = vmrunner;

      devShells.${system}.default = import ./shell.nix { inherit pkgs; };

      apps.${system}.default = {
        type = "app";
        program = "${vmrunner}/bin/boot";
      };

      lib.${system}.mkBoot = chainloader: pkgs.symlinkJoin {
        name = "boot-with-chainloader";
        paths = [ vmrunner ];
        buildInputs = [ pkgs.makeWrapper ];
        postBuild = ''
          wrapProgram $out/bin/boot \
            --set INCLUDEOS_CHAINLOADER ${chainloader}/bin/
        '';
      };
    };
}
