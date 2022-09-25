#!/usr/bin/env python3
# CHROMEOS COMPILE INSTRUCTIONS: https://www.chromium.org/chromium-os/how-tos-and-troubleshooting/kernel-configuration/

import os
from functions import *
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
    print("\033[96m" + "Preparing host system" + "\033[0m", flush=True)
    bash("apt update -y")
    bash("apt install -y netpbm imagemagick git build-essential ncurses-dev xz-utils libssl-dev bc flex libelf-dev "
         "bison binutils")
    # TODO: add cleaning after previous builds


def clone_kernel(kernel_head: str) -> None:
    print("\033[96m" + "Cloning kernel: " + kernel_head + "\033[0m", flush=True)
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
    print("\033[96m" + "Creating boot image" + "\033[0m", flush=True)
    # TODO: Boot image


def apply_patches():
    print("\033[96m" + "Applying Eupnea patches" + "\033[0m", flush=True)

    print("\033[96m" + "Applying bloog audio patch" + "\033[0m", flush=True)
    try:
        bash(f"git apply ../patches/bloog-audio.patch")
    except subprocess.CalledProcessError:
        print("Bloog audio patch already applied", flush=True)

    print("\033[96m" + "Applying important jsl i915 patch" + "\033[0m", flush=True)
    try:
        bash(f"git apply ../patches/jsl-i915.patch")
    except subprocess.CalledProcessError:
        print("Checking if patch is already applied", flush=True)
        # check if patch is actually applied
        try:
            bash('grep -C3 "BIT(RCS0) | BIT(BCS0) | BIT(VCS0) | BIT(VECS0)" drivers/gpu/drm/i915/i915_pci.c | '
                        'grep "jsl_info" -A5 | grep -c ".require_force_probe = 1"')
        except subprocess.CalledProcessError:
            print("\033[91m" + "JSL i915 patch is not applied!! CRITICAL ERROR" + "\033[0m", flush=True)
        else:
            print("Bloog audio patch already applied", flush=True)

    print("\033[96m" + "Applying headphone jack patch" + "\033[0m", flush=True)
    try:
        bash(f"git apply ../patches/jack-detection.patch").strip()
    except subprocess.CalledProcessError:
        print("Headphone jack patch already applied", flush=True)

    print("\033[96m" + "Applying headphone jack utils patch" + "\033[0m", flush=True)
    try:
        bash(f"git apply ../patches/jack-detection-utils.patch").strip()
    except subprocess.CalledProcessError:
        print("Headphone jack utils patch already applied", flush=True)


def build_kernel() -> None:
    print("\033[96m" + "Preparing to build kernel" + "\033[0m", flush=True)
    # prevent dirty kernel build
    # add mod to .gitignore
    with open(".gitignore", "a") as file:
        file.write("mod")
    # create .scmversion
    with open(".scmversion", "w") as file:
        file.write("")

    # copy config file from GitHub
    try:
        rmfile(".config", )
    except FileNotFoundError:
        pass
    if args.version == "alt-chromeos-5.10":
        cpfile("../kernel-alt.conf", "./.config")
    else:
        cpfile("../kernel.conf", "./.config")

    # make config with default selections
    print("\033[96m" + "Making config with default options" + "\033[0m", flush=True)
    bash("make olddefconfig")
    # TODO: add config editing for users

    print("\033[96m" + "Building kernel" + "\033[0m", flush=True)
    kernel_start = time.time()
    try:
        bash(f"make -j{cores}")
    except subprocess.CalledProcessError:
        print("\033[91m" + f"Kernel build failed in: {time.time() - kernel_start}" + "\033[0m")
        exit(1)
    print("\033[96m" + f"Kernel build succeeded in: {time.time() - kernel_start}" + "\033[0m", flush=True)


def build_modules() -> None:
    print("\033[96m" + "Preparing for modules build" + "\033[0m", flush=True)
    rmdir("mod")  # just in case
    mkdir("mod")

    print("\033[96m" + "Building modules" + "\033[0m", flush=True)
    modules_start = time.time()
    try:
        # INSTALL_MOD_STRIP=1 removes debug symbols -> reduces unpacked kernel modules size
        bash(f"make -j{cores} modules_install INSTALL_MOD_PATH=mod INSTALL_MOD_STRIP=1")
    except subprocess.CalledProcessError:
        print("\033[91m" + f"Modules build failed in: {time.time() - modules_start}" + "\033[0m")
        exit(1)
    print("\033[96m" + f"Modules build succeeded in: {time.time() - modules_start}" + "\033[0m", flush=True)

    print("\033[96m" + "Compressing modules" + "\033[0m", flush=True)
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
        print("\033[91m" + f"Modules archival failed in: {time.time() - modules_start}" + "\033[0m")
        exit(1)
    print("\033[96m" + f"Modules archival succeeded in: {time.time() - modules_start}" + "\033[0m", flush=True)
    os.chdir("..")  # go back to chromeos kernel root


def build_headers():
    print("\033[96m" + "Preparing for header build" + "\033[0m", flush=True)
    rmdir("headers")  # just in case
    mkdir("headers")

    print("\033[96m" + "Building headers" + "\033[0m", flush=True)
    modules_start = time.time()
    try:
        bash(f"make -j{cores} headers_install INSTALL_MOD_PATH=headers")
    except subprocess.CalledProcessError:
        print("\033[91m" + f"Headers build failed in: {time.time() - modules_start}" + "\033[0m")
        exit(1)
    print("\033[96m" + f"Headers build succeeded in: {time.time() - modules_start}" + "\033[0m", flush=True)

    print("\033[96m" + "Compressing headers" + "\033[0m", flush=True)
    os.chdir("./headers")
    # TODO: convert to one liner
    # create extraction script
    with open("fastxz", "w") as file:
        file.write("xz -9 -T0")
    bash("chmod +x fastxz")  # make script executable
    modules_start = time.time()
    try:
        bash("tar -cvI './fastxz' -f ../headers.tar.xz usr/include/")
    except subprocess.CalledProcessError:
        print("\033[91m" + f"Headers archival failed in: {time.time() - modules_start}" + "\033[0m")
        exit(1)
    print("\033[96m" + f"Headers archival succeeded in: {time.time() - modules_start}" + "\033[0m", flush=True)
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
    print(f"Available cores: {cores}", flush=True)

    # check if running on ubuntu
    if not path_exists("/usr/bin/apt") and args.ignore_os:  # check if running on ubuntu/debian
        print("This script is made for Ubuntu(docker). Use --ignore-os to run on other systems.\n"
              " Install these packages using your package manager:", flush=True)
        print("netpbm imagemagick git build-essential ncurses-dev xz-utils libssl-dev bc flex libelf-dev bison cgpt "
              "vboot-kernel-utils", flush=True)
        exit(1)
    if args.version == "":
        print("Which kernel version would you like to use? ", flush=True)
        print("Manual building is not supported yet. Use the old script for now.", flush=True)
        exit(1)
        # TODO: add version selection for users
    if args.verbose:
        print("\033[93m" + "Verbosity increased" + "\033[0m")
        enable_verbose()  # enable verbose output in functions.py

    prepare_host()
    # get kernel_head
    try:
        with open("kernel_versions.json", "r") as json_file:
            read_kernel_head = json.load(json_file)[args.version]
    except KeyError:
        print("\033[91m" + "Kernel version not available." + "\033[0m", flush=True)
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
            #  system_map_name = "System-exp.map"
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

    # copy files to actual root
    print("\033[96m" + "Copying files to actual root" + "\033[0m", flush=True)

    cpfile("arch/x86/boot/bzImage", f"../{bzImage_name}")
    cpfile("modules.tar.xz", f"../{modules_name}")
    cpfile("headers.tar.xz", f"../{headers_name}")
    # cp("System.map", f"../{system_map_name}")
    # cpfile(".config", f"../{config_name}")

    print("\033[96m" + f"Full build completed in: {time.time() - script_start}" + "\033[0m", flush=True)
