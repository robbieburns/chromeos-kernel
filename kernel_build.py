#!/usr/bin/env python3


import os
from shutil import rmtree as rmdir
from pathlib import Path
import sys
import argparse
from urllib.request import urlretrieve
import subprocess as sp
from os import system as bash
from threading import Thread
from urllib.error import URLError
from time import sleep
import json


# parse arguments from the cli.
def process_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('-v', '--version', dest="version",
                        help="Kernel version to build(flag intended for docker containers)")
    parser.add_argument("-i", "--ignore-os", action="store_true", dest="ignore_os", default=False,
                        help="Allow building on non Ubuntu/debian based systems")
    return parser.parse_args()


def prepare_host() -> None:
    print("\033[96m" + "Preparing host system" + "\033[0m")
    bash("apt update -y")
    bash("apt install -y netpbm imagemagick git build-essential ncurses-dev xz-utils libssl-dev bc flex libelf-dev "
         "bison cgpt vboot-kernel-utils")
    # TODO: add cleaning after previous builds


def clone_kernel(kernel_head: str) -> None:
    print("\033[96m" + "Cloning kernel: " + kernel_head + "\033[0m")
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


def create_boot_image():
    print("\033[96m" + "Creating boot image" + "\033[0m")
    # TODO: Boot image


def apply_patches():
    print("\033[96m" + "Applying Eupnea patches" + "\033[0m")

    print("Applying bloog audio patch")
    patch_bloog = patch("bloog-audio.patch")
    if patch_bloog.__contains__("patch does not apply"):
        print(patch_bloog)
        print("Bloog audio patch already applied")

    print("Applying important jsl i915 patch")
    patch_jsl = patch("jsl-i915.patch")
    if patch_jsl.__contains__("patch does not apply"):
        print("Checking if patch is already applied")
        # check if patch is actually applied
        if patch('grep -C3 "BIT(RCS0) | BIT(BCS0) | BIT(VCS0) | BIT(VECS0)" drivers/gpu/drm/i915/i915_pci.c | grep '
                 '"jsl_info" -A5 | grep ".require_force_probe = 1"') == "":
            print("Bloog audio patch already applied")
        else:
            print(patch_jsl)
            print("JSL i915 patch is not applied: CRITICAL ERROR")
            exit(1)

    print("Applying headphone jack patch")
    patch_jack = patch("jack-detection.patch")
    if patch_jack.__contains__("patch does not apply"):
        print(patch_jack)
        print("Headphone jack patch already applied")

    print("Applying headphone jack utils patch")
    patch_jack_utils = patch("jack-detection-utils.patch")
    if patch_jack.__contains__("patch does not apply"):
        print(patch_jack_utils)
        print("Headphone jack utils patch already applied")


def patch(patch: str) -> str:
    return sp.run(f"git apply ../patches/{patch}", shell=True, capture_output=True).stderr.decode("utf-8").strip()


if __name__ == "__main__":
    # Elevate script to root
    if os.geteuid() != 0:
        args = ['sudo', sys.executable] + sys.argv + [os.environ]
        os.execlpe('sudo', *args)
    args = process_args()
    # check if running on ubuntu
    if not os.path.exists("/usr/bin/apt") and not args.ignore_os:  # check if running on ubuntu/debian
        print("This script is made for Ubuntu(docker). Use --ignore-os to run on other systems.\n"
              " Install these packages using your package manager:")
        print("netpbm imagemagick git build-essential ncurses-dev xz-utils libssl-dev bc flex libelf-dev bison cgpt "
              "vboot-kernel-utils")
        exit(1)
    if not args.version == "":
        print("Which kernel version would you like to use? ")
        print("Manual building is not supported yet. Use old script for now.")
        exit(1)
        # TODO: add version selection for users
    prepare_host()
    # get kernel_head
    with open("kernel_versions.json", "r") as file:
        read_kernel_head = json.load(file)[args.version]
    clone_kernel(read_kernel_head)
    create_boot_image()
    apply_patches()

    print("Preventing dirty kernel build")
    # add mod to .gitignore
    with open(".gitignore", "a") as file:
        file.write("mod")
    # create .scmversion
    with open(".scmversion", "w") as file:
        file.write("")


