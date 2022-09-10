#!/bin/bash

# install requirements
sudo apt update -y
sudo apt install -y netpbm imagemagick git build-essential ncurses-dev xz-utils libssl-dev bc flex libelf-dev bison cgpt vboot-kernel-utils

# Exit on errors
set -e

# If no kernel version in args
if [[ $# -eq 0 ]]; then
  printf "What kernel version would you like? (choose a number 1-3)"
  printf "This can be any ChromeOS kernel branch, but the recommended versions are:"
  printf "1: chromeos-5.10:\n  (Kernel version that is up-to-date and has good audio support with SOF)\n"
  printf "2: alt-chromeos-5.10:\n  (Kernel version that is up-to-date but is pinned to a commit that supports KBL/SKL devices which do not support SOF)\n"
  printf "3: chromeos-5.4:\n  (Often causes more issues despite being a commonly-used kernel in ChromeOS)\n"
  printf "Older kernels that may provide better support for specific boards:"
  printf "4: chromeos-4.19:\n  (For testing purposes)\n"
  printf "5: chromeos-4.14:\n  (For testing purposes)\n"
  printf "6: chromeos-4.4:\n  (For testing purposes; too old for Mesa3D and some other Linux userspace software)\n"
  printf "Newer kernels that are not widely used within ChromeOS devices:"
  printf "7: chromeos-5.15:\n  (Similar version to those used in Linux distributions, not used in any ChromeOS devices currently)\n"
  read -r KERNEL_VERSION
else
  export KERNEL_VERSION=$1
fi

# Select correct release from Google
case $KERNEL_VERSION in
"1" | "chromeos-5.10") KERNEL_VERSION="release-R101-14588.B-chromeos-5.10" ;;
"2" | "alt-chromeos-5.10") KERNEL_VERSION="release-R86-13421.B-chromeos-5.4" ;;
"3" | "chromeos-5.4") KERNEL_VERSION="release-R101-14588.B-chromeos-5.4" ;;
"4" | "chromeos-4.19") KERNEL_VERSION="release-R101-14588.B-chromeos-4.19" ;;
"5" | "chromeos-4.14") KERNEL_VERSION="release-R101-14588.B-chromeos-4.14" ;;
"6" | "chromeos-4.4") KERNEL_VERSION="release-R101-14588.B-chromeos-4.4" ;;
"7" | "chromeos-5.15") KERNEL_VERSION="release-R106-15054.B-chromeos-5.15" ;;
*)
  printerr "Please supply a valid kernel version"
  exit
  ;;
esac

echo "Cloning kernel $KERNEL_VERSION"
if [[ ! -d $KERNEL_VERSION ]]; then
  if [[ $KERNEL_VERSION == "alt-chromeos-5.10" ]]; then
    git clone --branch chromeos-5.10 --single-branch https://chromium.googlesource.com/chromiumos/third_party/kernel.git $KERNEL_VERSION
    cd $KERNEL_VERSION
    git checkout "$(git rev-list -n 1 --first-parent --before="2021-08-1 23:59" chromeos-5.10)"
    cd ..
  else
    git clone --branch $KERNEL_VERSION --single-branch --depth 1 https://chromium.googlesource.com/chromiumos/third_party/kernel.git $KERNEL_VERSION
  fi
fi

(
  # TODO: fix logo
  echo "Setting up the bootlogo"
  cd logo
  mogrify -format ppm "logo.png"
  ppmquant 224 logo.ppm >logo_224.ppm
  pnmnoraw logo_224.ppm >logo_final.ppm
)

cd $KERNEL_VERSION
# CUSTOM EUPNEA PATCHES:
echo "Applying custom patches to the kernel"

cp ../logo/logo_final.ppm drivers/video/logo/logo_linux_clut224.ppm

# A somewhat commonly-used device, lesser priority than JSL i915
git apply ../patches/bloog-audio.patch || {
  git apply ../patches/bloog-audio.patch -R --check && echo "Bloog Audio Patch already applied"
}

# Super important patch, adds support for Jasperlake i915 (many DEDEDE devices)
# This is why we have a check to make sure again
git apply ../patches/jsl-i915.patch || {
  git apply ../patches/jsl-i915.patch -R --check && echo "Jasperlake iGPU Patch already applied"
}
grep -C3 "BIT(RCS0) | BIT(BCS0) | BIT(VCS0) | BIT(VECS0)" drivers/gpu/drm/i915/i915_pci.c | grep "jsl_info" -A5 | grep ".require_force_probe = 1" && {
  printerr "JSL Patch failed, exiting!"
  exit
}

# Important Jack Detection patch that fixes headphone jacks
git apply ../patches/jack-detection.patch || {
  git apply ../patches/jack-detection.patch -R --check && echo "Jack Detection Patch already applied"
}

# Utility functions not in the ChromeOS Kernel that are needed for the above patch to work
git apply ../patches/jack-detection-utils.patch || {
  git apply ../patches/jack-detection-utils.patch -R --check && echo "Jack Detection Utils Patch already applied"
}
echo "$(ls ../patches) applied"

# Prevents a dirty kernel
echo "mod" >>.gitignore
touch .scmversion

echo "Copying and updating kernel config"
if [[ $KERNEL_VERSION == "alt-chromeos-5.10" ]]; then
  MODULES="modules.alt.tar.xz"
  VMLINUZ="bzImage.alt"
  SYSTEM_MAP="System.map-eupnea-alt"
  CONFIG="config-eupnea-alt"
  [[ -f .config ]] || cp ../kernel.alt.conf .config || exit
elif [[ $KERNEL_VERSION == "chromeos-5.15" ]]; then
  MODULES="modules.exp.tar.xz"
  VMLINUZ="bzImage.exp"
  SYSTEM_MAP="System.map-eupnea-exp"
  CONFIG="config-eupnea-exp"
  [[ -f .config ]] || cp ../kernel.exp.conf .config || exit
else
  MODULES="modules.tar.xz"
  VMLINUZ="bzImage"
  SYSTEM_MAP="System.map-eupnea"
  CONFIG="config-eupnea"
  [[ -f .config ]] || cp ../kernel.conf .config || exit
fi
echo "Making olddeconfig"
make olddefconfig

# If the terminal is interactive and not running in docker
if [[ -t 0 ]] && [[ ! -f /.dockerenv ]]; then
  read -p "Would you like to make edits to the kernel config? (y/n) " -n 1 -r
  echo
  if [[ $REPLY =~ ^[Yy]$ ]]; then
    make menuconfig
  fi

  read -p "Would you like to write the new config to github? (y/n) " -n 1 -r
  echo
  if [[ $REPLY =~ ^[Yy]$ ]]; then
    if [[ $KERNEL_VERSION == "alt-chromeos-5.10" ]]; then
      cp .config ../kernel.alt.conf
    else
      cp .config ../kernel.conf
    fi
  fi

  echo "Building kernel"
  read -p "Would you like a full rebuild? (y/n) " -n 1 -r
  echo
  if [[ $REPLY =~ ^[Yy]$ ]]; then
    make clean
    make -j"$(nproc)" || exit
  else
    make -j"$(nproc)" || exit
  fi
else
  make -j"$(nproc)"
fi

cp arch/x86/boot/bzImage ../$VMLINUZ
echo "bzImage and modules built"

rm -rf mod || true
mkdir mod
make -j"$(nproc)" modules_install INSTALL_MOD_PATH=mod
# Creates an archive containing /lib/modules/...

cd mod
# Speedy multicore compression
# Some version of tar don't support arguments after the command in the -I option,
# so we're putting the arguments and the command in a script
echo "xz -9 -T0" >fastxz
chmod +x fastxz
tar -cvI './fastxz' -f ../$MODULES lib/
echo "modules.tar.xz created!"

# Copy the vmlinuz, modules.tar, system.map, and kernel config to the root directory
cd ..

# Print current path and files
echo "$MODULES"
echo "$SYSTEM_MAP"
echo "$CONFIG"

echo "$PWD"
echo $(sudo ls -a)
echo $(sudo ls -a ../)

cp modules.tar.xz ../$MODULES
cp System.map ../$SYSTEM_MAP
cp .config ../$CONFIG

echo "Command to extract modules to USB:"
echo "sudo rm -rf /mnt/lib/modules/* && sudo cp -Rv kernel/mod/lib/modules/* /mnt/lib/modules && sync"
