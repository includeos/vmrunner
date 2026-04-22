{ pkgs }:

let
  memToMiB = mem:
    let
      g = builtins.match "^([0-9]+)[Gg]$" mem;
      m = builtins.match "^([0-9]+)[Mm]$" mem;
    in
      if g != null then (builtins.fromJSON (builtins.head g)) * 1024
      else if m != null then builtins.fromJSON (builtins.head m)
      else throw "invalid mem: ${mem}";
in
{
  mkConfig = { mem ? "128m" }:
    let
      mem' = memToMiB mem;
      vmJson = pkgs.writeText "vm.json"
        (builtins.toJSON { mem = mem'; });
    in {
      mem = mem';
      inherit vmJson;
      args = [ "-j" vmJson ];
    };
}
