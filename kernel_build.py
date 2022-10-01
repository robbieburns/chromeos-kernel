#!/usr/bin/env python3
# CHROMEOS COMPILE INSTRUCTIONS: https://www.chromium.org/chromium-os/how-tos-and-troubleshooting/kernel-configuration/
# This script is primarily designed to be run in a cloud container system
import os
import sys
from functions import *
from functions import print_question as print_green
import argparse
import time
import json


# parse arguments from the cli.
def process_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(dest="version", type=str, help="Kernel version to build(flag intended for docker containers)")
    parser.add_argument("-i", "--ignore-os", action="store_true", dest="ignore_os", default=False,
                        help="Allow building on non Ubuntu/debian based systems")
    parser.add_argument("-v", "--verbose", action="store_true", dest="verbose", default=False, help="Print more output")
    return parser.parse_args()


def prepare_host() -> None:
    print_status("Preparing host system")
    bash("apt update -y")
    bash("apt install -y netpbm imagemagick git build-essential ncurses-dev xz-utils libssl-dev bc flex libelf-dev "
         "bison binutils")
    # TODO: add cleaning after previous builds for user builds


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


# Create boot icon/image
def create_boot_image():
    print_status("Creating boot image")
    # TODO: Boot image
    print_warning("Not yet implemented")


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
    kernel_start = time.time()
    try:
        bash(f"make -j{cores}")
    except subprocess.CalledProcessError:
        print_error(f"Kernel build failed in: " + "%.0f" % (time.time() - kernel_start) + "seconds")
        exit(1)
    print_green(f"Kernel build succeeded in: " + "%.0f" % (time.time() - kernel_start) + "seconds")


def build_modules() -> None:
    print_status("Preparing for modules build")
    rmdir("mod")  # just in case
    mkdir("mod")

    print_status("Building modules")
    modules_start = time.time()
    try:
        # INSTALL_MOD_STRIP=1 removes debug symbols -> reduces unpacked kernel modules size from 1.2GB to 70MB
        bash(f"make -j{cores} modules_install INSTALL_MOD_PATH=mod INSTALL_MOD_STRIP=1")
    except subprocess.CalledProcessError:
        print_error(f"Modules build failed in: " + "%.0f" % (time.time() - modules_start) + "seconds")
        exit(1)
    print_green(f"Modules build succeeded in: " + "%.0f" % (time.time() - modules_start) + "seconds")

    print_status("Compressing kernel modules")
    os.chdir("./mod")
    # TODO: convert to one liner
    # create extraction script
    with open("fastxz", "w") as file:
        file.write("xz -9 -T0")
    bash("chmod +x fastxz")  # make script executable
    modules_start = time.time()
    try:
        bash("tar -cvI './fastxz' -f ../modules.tar.xz lib/")
    except subprocess.CalledProcessError:
        print_error(f"Modules archival failed in: " + "%.0f" % (time.time() - modules_start) + "seconds")
        exit(1)
    print_green(f"Modules archival succeeded in: " + "%.0f" % (time.time() - modules_start) + "seconds")
    os.chdir("..")  # go back to chromeos kernel root


def build_headers():
    print_status("Preparing for header build")
    rmdir("headers")  # just in case
    mkdir("headers")

    print_status("Building headers")
    headers_start = time.time()
    try:
        bash(f"make -j{cores} headers_install INSTALL_HDR_PATH=headers")
    except subprocess.CalledProcessError:
        print_error(f"Headers build failed in: " + "%.0f" % (time.time() - headers_start) + "seconds")
        exit(1)
    print_green(f"Headers build succeeded in: " + "%.0f" % (time.time() - headers_start) + "seconds")

    print_status("Compressing headers")
    os.chdir("./headers")
    # TODO: convert to one liner
    # create extraction script
    with open("fastxz", "w") as file:
        file.write("xz -9 -T0")
    bash("chmod +x fastxz")  # make script executable
    headers_start = time.time()
    try:
        bash("tar -cvI './fastxz' -f ../headers.tar.xz include/")
    except subprocess.CalledProcessError:
        print_error(f"Headers archival failed in: " + "%.0f" % (time.time() - headers_start) + "seconds")
        exit(1)
    print_green(f"Headers archival succeeded in: " + "%.0f" % (time.time() - headers_start) + "seconds")
    os.chdir("..")  # go back to chromeos kernel root


if __name__ == "__main__":
    # Elevate script to root
    if not os.geteuid() == 0:
        sudo_args = ['sudo', sys.executable] + sys.argv + [os.environ]
        os.execlpe('sudo', *sudo_args)
    script_start = time.time()
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
    if args.version == "":
        print_green("Which kernel version would you like to use? ")
        print_error("Manual building is not supported yet. Use the old script for now.")
        exit(1)
        # TODO: add version selection for users
    if args.verbose:
        print_warning("Verbosity increased")
        set_verbose(args.verbose)  # enable verbose output in functions.py

    prepare_host()
    # get kernel_head
    try:
        with open("kernel_versions.json", "r") as json_file:
            read_kernel_head = json.load(json_file)[args.version]
    except KeyError:
        print_error("Kernel version not available.")
        exit(1)

    clone_kernel(read_kernel_head)
    create_boot_image()
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
            bzImage_name = "bzImage"
            modules_name = "modules.tar.xz"
            headers_name = "headers.tar.xz"
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

    print_header(f"Full build completed in: " + "%.0f" % (time.time() - script_start) + "seconds")
