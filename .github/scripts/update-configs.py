#!/usr/bin/env python3
import os
import subprocess


def bash(command: str) -> str:
    output = subprocess.check_output(command, shell=True, text=True).strip()
    print(output, flush=True)
    return output


if __name__ == "__main__":
    # init chromeos kernel git repo
    bash("git init kernel")
    os.chdir("./kernel")
    bash("git remote add origin https://chromium.googlesource.com/chromiumos/third_party/kernel")
    stable_branches = []
    for branch in bash("git ls-remote origin 'refs/heads/*'").split("\t"):
        branch = branch.split("\n")[0]
        if branch.startswith("refs/heads/release-R") and branch.endswith(".B-chromeos-5.10"):
            stable_branches.append(branch.split("/")[2])

    # sort by release number
    stable_branches.sort(key=lambda x: int(x.split("-")[1][1:]))
    # get the latest branch
    latest_version = stable_branches[-1]

    # clone latest branch
    bash(f"git clone --depth=1 --branch={latest_version} "
         f"https://chromium.googlesource.com/chromiumos/third_party/kernel")

    # Copy eupnea config into fresh chromeos kernel repo
    bash("cp kernel.conf kernel/.config")

    # Update config
    bash("cd linux && make olddefconfig")

    # Copy new config back to eupnea repo
    bash("cp kernel/.config kernel.conf")

    # Update build script
    with open("kernel_build.py", "r") as file:
        build_script = file.readlines()
    build_script[11] = f'"branch_name = "{latest_version}"\n'
    with open("kernel_build.py", "w") as file:
        file.writelines(build_script)
