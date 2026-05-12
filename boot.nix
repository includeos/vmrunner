{ pkgs, vmrunner }:

let
  mk = chainloader: { name ? "unikernel", extraFlags ? [], kvm ? false, cfg }:
    pkgs.symlinkJoin {
      name = "boot-${name}";
      paths = [ vmrunner ];
      buildInputs = [ pkgs.makeWrapper ];

      postBuild = ''
        wrapProgram $out/bin/boot \
          --set INCLUDEOS_CHAINLOADER ${chainloader}/bin/ \
          --add-flags "${builtins.concatStringsSep " " cfg.vm.args}" \
          ${pkgs.lib.optionalString kvm "--add-flags --kvm"} \
          ${pkgs.lib.optionalString (extraFlags != []) (
            "--add-flags \"" + builtins.concatStringsSep " " extraFlags + "\""
          )}
      '';
    };

  mkBoot = chainloader: cfg:
    rec {
      run = mk chainloader {
        name = "${cfg.name or "unikernel"}-run";
        inherit cfg;
      };

      debug = mk chainloader {
        name = "${cfg.name or "unikernel"}-debug";
        extraFlags = [ "-d" ];
        inherit cfg;
      };

      kvm = mk chainloader {
        name = "${cfg.name or "unikernel"}-kvm";
        kvm = true;
        inherit cfg;
      };

      default = run;
    };
in
{
  mkBoot = mkBoot;
}
