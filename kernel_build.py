#!/usr/bin/env python3
# CHROMEOS COMPILE INSTRUCTIONS: https://www.chromium.org/chromium-os/how-tos-and-troubleshooting/kernel-configuration/
# This script is primarily designed to be run in a cloud container system
import os
import sys
from functions import *
from functions import print_question as print_green
import argparse
from time import perf_counter
import json


# parse arguments from the cli.
def process_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(dest="version", type=str, help="Kernel version to build(flag intended for docker containers)")
    parser.add_argument("-i", "--ignore-os", action="store_true", dest="ignore_os", default=False,
                        help="Allow building on non Ubuntu/debian based systems")
    return parser.parse_args()


def clone_kernel(kernel_head: str) -> None:
    print_status(f"Cloning kernel: {kernel_head}")
    if args.version == "alt-chromeos-5.10":
        bash("git clone --branch chromeos-5.10 --single-branch https://chromium.googlesource.com/chromiumos/third_party"
             "/kernel.git chromeos-kernel")
        # revert to older commit
        os.chdir("./chromeos-kernel")
        bash('git checkout "$(git rev-list -n 1 --first-parent --before="2021-08-1 23:59" chromeos-5.10)"')
    else:
        bash(f"git clone --branch {kernel_head} --single-branch --depth 1 https://chromium.googlesource.com/chromiumos"
             f"/third_party/kernel.git chromeos-kernel")
        os.chdir("./chromeos-kernel")


def apply_patches():
    print_status("Applying Eupnea patches")

    print_status("Applying bloog audio patch")
    try:
        bash(f"git apply ../patches/bloog-audio.patch")
    except subprocess.CalledProcessError:
        print_warning("Bloog audio patch already applied")

    print_status("Applying important jsl i915 patch")  # Add support for Jasperlake i915 (many DEDEDE devices)
    try:
        bash(f"git apply ../patches/jsl-i915.patch")
    except subprocess.CalledProcessError:
        print_status("Checking if patch is already applied")
        # check if patch is actually applied
        try:
            bash('grep -C3 "BIT(RCS0) | BIT(BCS0) | BIT(VCS0) | BIT(VECS0)" drivers/gpu/drm/i915/i915_pci.c | '
                 'grep "jsl_info" -A5 | grep -c ".require_force_probe = 1"')
        except subprocess.CalledProcessError:
            print_error("JSL i915 patch is not applied!! CRITICAL ERROR")
        else:
            print_status("Bloog audio patch already applied")

    print_status("Applying headphone jack patch")  # Fixes headphone jack detection
    try:
        bash(f"git apply ../patches/jack-detection.patch").strip()
    except subprocess.CalledProcessError:
        print_warning("Headphone jack patch already applied")

    # Patch util functions that are not in the chromeos kernel, but are needed for the above patch to work
    print_status("Applying headphone jack utils patch")
    try:
        bash(f"git apply ../patches/jack-detection-utils.patch").strip()
    except subprocess.CalledProcessError:
        print_warning("Headphone jack utils patch already applied")


def build_kernel() -> None:
    print_status("Preparing to build kernel")
    # preventing dirty kernel build:
    # add mod to .gitignore
    with open(".gitignore", "a") as file:
        file.write("mod")
    # create .scmversion
    with open(".scmversion", "w") as file:
        file.write("")

    # copy config file from GitHub
    try:
        rmfile(".config")  # just in case
    except FileNotFoundError:
        pass
    if args.version == "alt-chromeos-5.10":
        cpfile("../kernel-alt.conf", "./.config")
    else:
        cpfile("../kernel.conf", "./.config")

    # make config with default selections
    print_status("Making config with default options")
    bash("make olddefconfig")
    # TODO: add config editing for normal users

    print_status(f"Building {args.version} kernel")
    kernel_start = perf_counter()
    try:
        bash(f"make -j{cores}")
    except subprocess.CalledProcessError:
        print_error(f"Kernel build failed in: " + "%.0f" % (perf_counter() - kernel_start) + "seconds")
        exit(1)
    print_green(f"Kernel build succeeded in: " + "%.0f" % (perf_counter() - kernel_start) + "seconds")


def build_modules() -> None:
    print_status("Preparing for modules build")
    rmdir("mod")  # just in case
    mkdir("mod")

    print_status("Building modules")
    modules_start = perf_counter()
    try:
        # INSTALL_MOD_STRIP=1 removes debug symbols -> reduces unpacked kernel modules size from 1.2GB to 70MB
        bash(f"make -j{cores} modules_install INSTALL_MOD_PATH=mod INSTALL_MOD_STRIP=1")
    except subprocess.CalledProcessError:
        print_error(f"Modules build failed in: " + "%.0f" % (perf_counter() - modules_start) + " seconds")
        exit(1)
    print_green(f"Modules build succeeded in: " + "%.0f" % (perf_counter() - modules_start) + " seconds")

    print_status("Removing broken symlinks")
    # TODO: Use pathlib
    bash("rm -f ./mod/lib/modules/*/build")
    bash("rm -f ./mod/lib/modules/*/source")

    print_status("Compressing kernel modules")
    os.chdir("./mod/lib/modules")
    modules_start = perf_counter()
    try:
        bash("tar -cv -I 'xz -9 -T0' -f ../../../modules.tar.xz ./")  # fast multicore xtreme compression
    except subprocess.CalledProcessError:
        print_error(f"Modules archival failed in: " + "%.0f" % (perf_counter() - modules_start) + " seconds")
        exit(1)
    print_green(f"Modules archival succeeded in: " + "%.0f" % (perf_counter() - modules_start) + " seconds")
    os.chdir("../../../")  # go back to chromeos kernel root


def build_headers():
    print_status("Packing headers")
    # Pack headers
    # Modified archlinux PKGBUILD
    # Source: https://github.com/archlinux/svntogit-packages/blob/packages/linux/trunk/PKGBUILD#L94
    headers_start = perf_counter()

    # Make directories
    mkdir("headers/tools/objtool", create_parents=True)
    mkdir("headers/kernel")
    mkdir("headers/arch/x86/kernel", create_parents=True)
    mkdir("headers/drivers/md", create_parents=True)
    mkdir("headers/drivers/media/usb/dvb-usb", create_parents=True)
    mkdir("headers/drivers/media/dvb-frontends")
    mkdir("headers/drivers/media/tuners")
    mkdir("headers/drivers/media/i2c")
    mkdir("headers/drivers/iio/common/hid-sensors", create_parents=True)
    mkdir("headers/net/mac80211", create_parents=True)

    # Copy files
    cpfile("./.config", "./headers/.config")
    cpfile("./Module.symvers", "./headers/Module.symvers")
    cpfile("./System.map", "./headers/System.map")
    # cpfile("./vmlinux", "./headers/vmlinux")
    cpfile("./Makefile", "./headers/Makefile")
    bash("chmod 644 ./headers/*")

    cpfile("./Makefile", "./headers/kernel/Makefile")
    bash("chmod 644 ./headers/kernel/Makefile")

    cpfile("./arch/x86/Makefile", "./headers/arch/x86/Makefile")
    bash("chmod 644 ./headers/arch/x86/Makefile")

    cpfile("./tools/objtool/objtool", "./headers/tools/objtool/objtool")

    cpfile("./arch/x86/kernel/asm-offsets.s", "./headers/arch/x86/kernel/asm-offsets.s")
    bash("chmod 644 ./headers/arch/x86/kernel/asm-offsets.s")

    cpfile("./drivers/media/i2c/msp3400-driver.h", "./headers/drivers/media/i2c/msp3400-driver.h")
    bash("chmod 644 ./headers/drivers/media/i2c/msp3400-driver.h")

    for file in os.listdir("./drivers/md"):
        if file.endswith(".h"):
            cpfile(f"./drivers/md/{file}", f"./headers/drivers/md/{file}")
            bash(f"chmod 644 ./headers/drivers/md/{file}")

    for file in os.listdir("./net/mac80211"):
        if file.endswith(".h"):
            cpfile(f"./net/mac80211/{file}", f"./headers/net/mac80211/{file}")
            bash(f"chmod 644 ./headers/net/mac80211/{file}")

    for file in os.listdir("./drivers/media/usb/dvb-usb"):
        if file.endswith(".h"):
            cpfile(f"./drivers/media/usb/dvb-usb/{file}", f"./headers/drivers/media/usb/dvb-usb/{file}")
            bash(f"chmod 644 ./headers/drivers/media/usb/dvb-usb/{file}")

    for file in os.listdir("./drivers/media/dvb-frontends"):
        if file.endswith(".h"):
            cpfile(f"./drivers/media/dvb-frontends/{file}", f"./headers/drivers/media/dvb-frontends/{file}")
            bash(f"chmod 644 ./headers/drivers/media/dvb-frontends/{file}")

    for file in os.listdir("./drivers/media/tuners"):
        if file.endswith(".h"):
            cpfile(f"./drivers/media/tuners/{file}", f"./headers/drivers/media/tuners/{file}")
            bash(f"chmod 644 ./headers/drivers/media/tuners/{file}")

    for file in os.listdir("./drivers/iio/common/hid-sensors"):
        if file.endswith(".h"):
            cpfile(f"./drivers/iio/common/hid-sensors/{file}", f"./headers/drivers/iio/common/hid-sensors/{file}")
            bash(f"chmod 644 ./headers/drivers/iio/common/hid-sensors/{file}")

    # Copy directories
    cpdir("./scripts", "./headers/scripts")
    cpdir("./include", "./headers/include")
    cpdir("./arch/x86/include", "./headers/arch/x86/include")

    # Recursively copy all kconfig files
    bash('find . -name "Kconfig*" -exec install -Dm644 {} ./headers/{} \;')
    # TODO: fix recursive copy of Kconfig files
    rmdir("./headers/headers")  # remove recursive copy of headers

    # Remove unnecessary architectures
    for directory in os.listdir("./headers/arch"):
        if os.path.isdir(directory) and directory != "x86":
            rmdir(directory)

    # Remove docs
    rmdir("./headers/Documentation")

    # Delete broken symlinks
    bash("find -L ./headers -type l -printf 'Removing %P\n' -delete")

    # Strip all files in headers
    bash("find ./headers -type f -exec strip -v {} \;")

    os.chdir("./headers")
    try:
        bash("tar -cv -I 'xz -9 -T0' -f ../headers.tar.xz ./")  # fast multicore xtreme compression
    except subprocess.CalledProcessError:
        print_error(f"Headers archival failed in: " + "%.0f" % (perf_counter() - headers_start) + " seconds")
        exit(1)
    print_green(f"Headers archival succeeded in: " + "%.0f" % (perf_counter() - headers_start) + " seconds")
    os.chdir("../")  # go back to chromeos kernel root


if __name__ == "__main__":
    # Elevate script to root
    if not os.geteuid() == 0:
        sudo_args = ['sudo', sys.executable] + sys.argv + [os.environ]
        os.execlpe('sudo', *sudo_args)
    script_start = perf_counter()
    args = process_args()

    # get number of cores
    cores = bash("nproc")
    print_status(f"Available cpu cores: {cores}")

    # check if running on ubuntu and no ignore-os flag
    if not path_exists("/usr/bin/apt") and not args.ignore_os:
        print_error("This script is made for Ubuntu(container). Use --ignore-os to run on other systems.\n"
                    " Install these packages using your package manager:")
        print_error("netpbm imagemagick git build-essential ncurses-dev xz-utils libssl-dev bc flex libelf-dev bison "
                    "cgpt vboot-kernel-utils")
        exit(1)

    set_verbose(True)  # enable verbose output in functions.py

    # get kernel_head
    try:
        with open("kernel_versions.json", "r") as json_file:
            read_kernel_head = json.load(json_file)[args.version]
    except KeyError:
        print_error("Kernel version not available.")
        print_status("Available versions:")
        with open("kernel_versions.json", "r") as json_file:
            for key in json.load(json_file):
                print(key)
        exit(1)

    clone_kernel(read_kernel_head)

    # replace boot logo
    print_status("Replacing boot logo")
    cpfile("../assets/boot_logo.ppm", "drivers/video/logo/logo_linux_clut224.ppm")

    apply_patches()
    build_kernel()
    build_modules()
    build_headers()

    # determine file names
    match args.version:
        case "alt-chromeos-5.10":
            bzImage_name = "bzImage-alt"
            modules_name = "modules-alt.tar.xz"
            headers_name = "headers-alt.tar.xz"
            # system_map_name = "System-alt.map"
            # config_name = "kernel-alt.config"
        case "chromeos-5.15":
            bzImage_name = "bzImage-exp"
            modules_name = "modules-exp.tar.xz"
            headers_name = "headers-exp.tar.xz"
            # system_map_name = "System-exp.map"
            # config_name = "kernel-exp.config"
        case "chromeos-5.10":
            bzImage_name = "bzImage-stable"
            modules_name = "modules-stable.tar.xz"
            headers_name = "headers-stable.tar.xz"
            #  system_map_name = "System.map"
            # config_name = "kernel.config"
        case _:
            # shouldn't be built by GitHub actions
            bzImage_name = "bzImage-old"
            modules_name = "modules-old.tar.xz"
            headers_name = "headers-old.tar.xz"
            # system_map_name = "System-old.map"
            # config_name = "kernel-old.config"

    # copy files up one dir for artifact upload
    print_status("Copying files to actual root")
    cpfile("arch/x86/boot/bzImage", f"../{bzImage_name}")
    cpfile("modules.tar.xz", f"../{modules_name}")
    cpfile("headers.tar.xz", f"../{headers_name}")
    # cp("System.map", f"../{system_map_name}")
    # cpfile(".config", f"../{config_name}")

    print_header(f"Full build completed in: " + "%.0f" % (perf_counter() - script_start) + "seconds")
