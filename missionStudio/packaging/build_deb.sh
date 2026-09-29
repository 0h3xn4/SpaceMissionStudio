#!/usr/bin/env bash
#
#  ISC License
#
#  Copyright (c) 2026, Autonomous Vehicle Systems Lab, University of Colorado at Boulder
#
#  Permission to use, copy, modify, and/or distribute this software for any
#  purpose with or without fee is hereby granted, provided that the above
#  copyright notice and this permission notice appear in all copies.
#
#  THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
#  WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
#  MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
#  ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
#  WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
#  ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
#  OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.
#
#
# Builds a real, installable Debian package (missionstudio_<version>_all.deb):
# a genuine "apt install ./missionstudio_*.deb" / double-click-in-a-file
# -manager experience -- no terminal, no pip commands typed by the end
# user. The package itself only carries missionStudio's own pure-Python
# wheel (built via build_wheel.sh) plus a handful of maintainer scripts
# (packaging/deb/DEBIAN/) and a desktop entry; Basilisk itself is NOT
# bundled (~impractical to vendor a multi-hundred-MB compiled wheel with
# mujoco/rust bits into a package built in this project's own development
# sandbox -- see packaging/README.md's "The vendoring decision") --
# instead, postinst creates a dedicated virtualenv at /opt/missionstudio/venv
# and pip installs "bsk[all]" from PyPI there the moment the package is
# configured (dpkg/apt's normal "configure" step), which needs internet
# access on the installing machine, same tradeoff install.sh's own
# --basilisk-wheel-less path already has.
#
# Usage:
#   ./build_deb.sh [OUTPUT_DIR]
#
# Genuinely built AND test-installed (via `dpkg -i` as root, in a
# throwaway environment with real network access to PyPI) in this
# project's own development sandbox -- see packaging/README.md for what
# exactly that confirmed.

set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
project_dir="$(dirname "$script_dir")"
output_dir="${1:-$project_dir/dist}"

if ! command -v dpkg-deb >/dev/null 2>&1; then
    echo "dpkg-deb not found -- this script only runs on Debian/Ubuntu-family systems" >&2
    echo "(or any system with dpkg-dev installed: apt-get install dpkg-dev)." >&2
    exit 1
fi

version=$(cd "$project_dir" && python3 -c "import missionstudio; print(missionstudio.__version__)")
echo "Building missionstudio_${version}_all.deb ..."

# Build the wheel this package bundles -- same script, same source of
# truth, as the plain (non-.deb) wheel distribution.
wheel_build_dir=$(mktemp -d)
trap 'rm -rf "$wheel_build_dir"' EXIT
"$script_dir/build_wheel.sh" "$wheel_build_dir" >/dev/null
wheel=$(ls -1t "$wheel_build_dir"/missionstudio-*.whl | head -n1)

# Assemble the package's staging directory from packaging/deb/ (the
# checked-in skeleton: DEBIAN/ maintainer scripts + control.in, the
# desktop entry, the copyright file) plus this build's freshly-built
# wheel -- never mutate packaging/deb/ itself, so re-running this script
# (or building at a different version) never leaves stray build output
# in source control.
staging=$(mktemp -d)
trap 'rm -rf "$wheel_build_dir" "$staging"' EXIT
chmod 755 "$staging"
cp -r "$script_dir/deb/." "$staging/"
mkdir -p "$staging/opt/missionstudio/dist"
cp "$wheel" "$staging/opt/missionstudio/dist/"

sed "s/@VERSION@/${version}/" "$staging/DEBIAN/control.in" > "$staging/DEBIAN/control"
rm "$staging/DEBIAN/control.in"

chmod 755 "$staging/DEBIAN/postinst" "$staging/DEBIAN/prerm" "$staging/DEBIAN/postrm"

mkdir -p "$output_dir"
output_deb="$output_dir/missionstudio_${version}_all.deb"
# --root-owner-group: every file dpkg-deb packs is owned by root:root in
# the resulting .deb, regardless of who's actually running this script --
# the correct, standard choice for a package meant to be installed
# system-wide via apt/dpkg (which always runs as root), and avoids
# baking this build machine's own uid/gid into the archive.
dpkg-deb --build --root-owner-group "$staging" "$output_deb"

echo
echo "Built: $output_deb"
echo "Install with: sudo apt install ./$(basename "$output_deb")"
echo "(or: sudo dpkg -i $(basename "$output_deb")  -- apt install ./PATH is preferred, it also resolves"
echo " python3/python3-venv/python3-pip if you don't already have them)"
