{
  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-unstable";
    pre-commit-hooks.url = "github:cachix/git-hooks.nix";
  };

  outputs =
    {
      self,
      nixpkgs,
      ...
    }@inputs:
    let
      supportedSystems = [
        "x86_64-linux"
        "aarch64-linux"
        "x86_64-darwin"
        "aarch64-darwin"
      ];

      forAllSystems = nixpkgs.lib.genAttrs supportedSystems;

    in
    {
      checks = forAllSystems (system: {
        pre-commit-check = inputs.pre-commit-hooks.lib.${system}.run {
          src = ./.;
          hooks = {
            check-added-large-files.enable = true;
            typos = {
              enable = true;
            };
            check-yaml.enable = true;
            convco.enable = true;
            end-of-file-fixer.enable = true;
            fix-byte-order-marker.enable = true;
            ruff-format.enable = true;
            ruff.enable = true;
            trim-trailing-whitespace.enable = true;
            trufflehog = {
              enable = true;
              stages = [ "pre-push" ];
            };
          };
        };
      });

      devShells = forAllSystems (
        system:
        let
          pkgs = nixpkgs.legacyPackages.${system};
        in
        {
          default = nixpkgs.legacyPackages.${system}.mkShell {
            shellHook = ''
              ${self.checks.${system}.pre-commit-check.shellHook}
              export LD_LIBRARY_PATH="$NIX_LD_LIBRARY_PATH:$LD_LIBRARY_PATH"
              exec ${pkgs.nushell}/bin/nu
            '';
            buildInputs = self.checks.${system}.pre-commit-check.enabledPackages ++ [
              pkgs.uv
            ];
          };
        }
      );
    };
}
