#!/usr/bin/env python3
# CHROMEOS COMPILE INSTRUCTIONS: https://www.chromium.org/chromium-os/how-tos-and-troubleshooting/kernel-configuration/

import os
from os import system as bash
from subprocess import check_output as bash_return
from shutil import rmtree as rmdir, copy
from pathlib import Path
import sys
import argparse
import time
import json


# parse arguments from the cli.
def process_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(dest="version", type=str, help="Kernel version to build(flag intended for docker containers)")
    parser.add_argument("-i", "--ignore-os", action="store_true", dest="ignore_os", default=False,
                        help="Allow building on non Ubuntu/debian based systems")
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
    patch_bloog = bash_return(f"git apply ../patches/bloog-audio.patch", shell=True, text=True).strip()
    if patch_bloog.__contains__("patch does not apply"):
        print(patch_bloog, flush=True)
        print("Bloog audio patch already applied", flush=True)

    print("\033[96m" + "Applying important jsl i915 patch" + "\033[0m", flush=True)
    patch_jsl = bash_return(f"git apply ../patches/jsl-i915.patch", shell=True, text=True).strip()
    if patch_jsl.__contains__("patch does not apply"):
        print("Checking if patch is already applied", flush=True)
        # check if patch is actually applied
        if bash_return('grep -C3 "BIT(RCS0) | BIT(BCS0) | BIT(VCS0) | BIT(VECS0)" drivers/gpu/drm/i915/i915_pci.c | '
                       'grep "jsl_info" -A5 | grep -c ".require_force_probe = 1"', shell=True, text=True) == "1":
            print(patch_jsl, flush=True)
            print("\033[91m" + "JSL i915 patch is not applied!! CRITICAL ERROR" + "\033[0m", flush=True)
        else:
            print("Bloog audio patch already applied", flush=True)

    print("\033[96m" + "Applying headphone jack patch" + "\033[0m", flush=True)
    patch_jack = bash_return(f"git apply ../patches/jack-detection.patch", shell=True, text=True).strip()
    if patch_jack.__contains__("patch does not apply"):
        print(patch_jack, flush=True)
        print("Headphone jack patch already applied", flush=True)

    print("\033[96m" + "Applying headphone jack utils patch" + "\033[0m", flush=True)
    patch_jack_utils = bash_return(f"git apply ../patches/jack-detection-utils.patch", shell=True, text=True).strip()
    if patch_jack.__contains__("patch does not apply"):
        print(patch_jack_utils, flush=True)
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
        os.remove(".config", )
    except FileNotFoundError:
        pass
    if args.version == "alt-chromeos-5.10":
        bash("cp ../kernel-alt.conf ./.config")
    else:
        bash("cp ../kernel.conf ./.config")

    # make config with default selections
    print("\033[96m" + "Making config with default options" + "\033[0m", flush=True)
    bash("make olddefconfig")
    # TODO: add config editing for users

    # Remove all debug options from kernel config
    # with open(".config", "r") as file:
    #     config = file.readlines()
    # new_config = []
    # for line in config:
    #     if line.__contains__("CONFIG_DEBUG"):
    #         line = "# " + line
    #     new_config.append(line)
    # with open(".config", "w") as file:
    #     file.writelines(new_config)

    print("\033[96m" + "Building kernel" + "\033[0m", flush=True)
    kernel_start = time.time()
    bash(f"make -j{cores}")
    # if sp.run(f"make -j{cores}", shell=True).returncode == 2:
    #    print("\033[91m" + f"Kernel build failed in: {time.time() - kernel_start}" + "\033[0m")
    #    exit(1)
    # else:
    bash("echo $?")
    print("\033[96m" + f"Kernel build succeeded in: {time.time() - kernel_start}" + "\033[0m", flush=True)


def build_modules() -> None:
    print("\033[96m" + "Preparing for modules build" + "\033[0m", flush=True)
    rmdir("mod", ignore_errors=True)  # just in case
    Path("mod").mkdir()

    print("\033[96m" + "Building modules" + "\033[0m", flush=True)
    modules_start = time.time()
    print(os.getcwd(), flush=True)
    bash("ls -a")
    bash(f"make -j{cores} modules_install INSTALL_MOD_PATH=mod")
    # if sp.run(f"make -j{cores} modules_install INSTALL_MOD_PATH=mod", shell=True).returncode == 2:
    #     print("\033[91m" + f"Modules build failed in: {time.time() - modules_start}" + "\033[0m")
    #     exit(1)
    # else:
    print("\033[96m" + f"Modules build succeeded in: {time.time() - modules_start}" + "\033[0m", flush=True)

    print("\033[96m" + "Compressing modules" + "\033[0m", flush=True)
    os.chdir("./mod")
    # TODO: convert to one liner
    # create extraction script
    with open("fastxz", "w") as file:
        file.write("xz -9 -T0")
    bash("chmod +x fastxz")  # make script executable
    modules_start = time.time()
    bash("tar -cvI './fastxz' -f ../modules.tar.xz lib/")
    # if sp.run("tar -cvI './fastxz' -f ../modules.tar.xz lib/", shell=True).returncode == 2:
    #     print("\033[91m" + f"Modules archival failed in: {time.time() - modules_start}" + "\033[0m")
    #     exit(1)
    # else:
    print("\033[96m" + f"Modules archival succeeded in: {time.time() - modules_start}" + "\033[0m", flush=True)
    os.chdir("..")  # go back to chromeos kernel root


if __name__ == "__main__":
    # Elevate script to root
    if not os.geteuid() == 0:
        sudo_args = ['sudo', sys.executable] + sys.argv + [os.environ]
        os.execlpe('sudo', *sudo_args)
    script_start = time.time()
    args = process_args()

    # get number of cores
    cores = bash_return("nproc", shell=True, text=True).strip()
    print(f"Available cores: {cores}", flush=True)

    # check if running on ubuntu
    if not os.path.exists("/usr/bin/apt") and not args.ignore_os:  # check if running on ubuntu/debian
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

    # determine file names
    match args.version:
        case "alt-chromeos-5.10":
            modules_name = "modules-alt.tar.xz"
            bzImage_name = "bzImage-alt"
            # system_map_name = "System-alt.map"
            config_name = "kernel-alt.config"
        case "chromeos-5.15":
            modules_name = "modules-exp.tar.xz"
            bzImage_name = "bzImage-exp"
            #  system_map_name = "System-exp.map"
            config_name = "kernel-exp.config"
        case "chromeos-5.10":
            modules_name = "modules.tar.xz"
            bzImage_name = "bzImage"
            #  system_map_name = "System.map"
            config_name = "kernel.config"
        case _:
            # shouldn't be built by GitHub actions
            modules_name = "modules-old.tar.xz"
            bzImage_name = "bzImage-old"
            # system_map_name = "System-old.map"
            config_name = "kernel-old.config"

    # copy files to actual root
    print("\033[96m" + "Copying files to actual root" + "\033[0m", flush=True)

    print(os.getcwd(), flush=True)

    bash("ls -a")
    bash("ls arch/x86/boot")

    copy("modules.tar.xz", f"../{modules_name}")
    copy("arch/x86/boot/bzImage", f"../{bzImage_name}")
    # cp("System.map", f"../{system_map_name}")
    copy(".config", f"../{config_name}")

    print("\033[96m" + f"Build completed in: {time.time() - script_start}" + "\033[0m", flush=True)
