#!/usr/bin/env python3
# CHROMEOS COMPILE INSTRUCTIONS: https://www.chromium.org/chromium-os/how-tos-and-troubleshooting/kernel-configuration/
# This script is primarily designed to be run in a cloud container system
import argparse
import os
import sys
from time import perf_counter

from functions import *
from functions import print_question as print_green

branch_name = "release-R110-15278.B-chromeos-5.10"


# parse arguments from the cli.
def process_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("-i", "--ignore-os", action="store_true", dest="ignore_os", default=False,
                        help="Allow building on non Ubuntu/debian based systems")
    return parser.parse_args()


def clone_kernel() -> None:
    print_status(f"Cloning kernel: {branch_name}")
    bash(f"git clone --branch {branch_name} --single-branch --depth 1 https://chromium.googlesource.com/chromiumos"
         f"/third_party/kernel.git chromeos-kernel")
    os.chdir("./chromeos-kernel")


def build_kernel() -> None:
    print_status("Preparing to build kernel")
    # preventing dirty kernel build:
    # add mod to .gitignore
    with open(".gitignore", "a") as file:
        file.write("mod")
    # create .scmversion
    with open(".scmversion", "w") as file:
        file.write("")

    rmfile(".config")  # delete old config
    # copy config file from repo root
    cpfile("../kernel.conf", "./.config")

    print_status("Building 5.10 kernel")
    kernel_start = perf_counter()
    try:
        bash(f"make -j{cores}")
    except subprocess.CalledProcessError:
        print_error("Kernel build failed in: " + "%.0f" % (perf_counter() - kernel_start) + "seconds")
        exit(1)
    print_green("Kernel build succeeded in: " + "%.0f" % (perf_counter() - kernel_start) + "seconds")


def build_modules() -> None:
    print_status("Preparing for modules build")
    rmdir("mod")
    mkdir("mod")

    print_status("Building modules")
    modules_start = perf_counter()
    try:
        # INSTALL_MOD_STRIP=1 removes debug symbols -> reduces kernel modules size from 1.2GB to 70MB
        bash(f"make -j{cores} modules_install INSTALL_MOD_PATH=mod INSTALL_MOD_STRIP=1")
    except subprocess.CalledProcessError:
        print_error("Modules build failed in: " + "%.0f" % (perf_counter() - modules_start) + " seconds")
        exit(1)
    print_green("Modules build succeeded in: " + "%.0f" % (perf_counter() - modules_start) + " seconds")

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
        print_error("Modules archival failed in: " + "%.0f" % (perf_counter() - modules_start) + " seconds")
        exit(1)
    print_green("Modules archival succeeded in: " + "%.0f" % (perf_counter() - modules_start) + " seconds")
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
    bash("chmod 755 ./headers/tools/objtool/objtool")

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
        print_error("Headers archival failed in: " + "%.0f" % (perf_counter() - headers_start) + " seconds")
        exit(1)
    print_green("Headers archival succeeded in: " + "%.0f" % (perf_counter() - headers_start) + " seconds")
    os.chdir("../")  # go back to chromeos kernel root


if __name__ == "__main__":
    # Elevate script to root
    if os.geteuid() != 0:
        sudo_args = ['sudo', sys.executable] + sys.argv + [os.environ]
        os.execlpe('sudo', *sudo_args)

    script_start = perf_counter()
    args = process_args()
    set_verbose(True)  # enable verbose output in functions.py

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

    clone_kernel()

    # add boot logo
    print_status("Adding boot logo")
    cpfile("../assets/depthboot_boot_logo.ppm", "drivers/video/logo/logo_linux_clut224.ppm")

    build_kernel()
    build_modules()
    build_headers()

    # copy files up one dir for artifact upload
    print_status("Copying files to actual root")
    cpfile("arch/x86/boot/bzImage", "../bzImage-stable")
    cpfile("modules.tar.xz", "../modules-stable.tar.xz")
    cpfile("headers.tar.xz", "../headers-stable.tar.xz")

    print_header("Full build completed in: " + "%.0f" % (perf_counter() - script_start) + "seconds")
