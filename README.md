# Building the chromeOS kernel
Use the build.sh file

## Manually(not recommended)
1. Clone the repository with git by running:
```bash
git clone --branch chromeos-5.10 --depth=1 https://chromium.googlesource.com/chromiumos/third_party/kernel.git
cd kernel
```

2. Download the kernel `.config` file, and update it, by running:
```bash
wget https://raw.githubusercontent.com/cb-linux/breath/main/kernel.conf -O .config
make olddefconfig
```

3. Compile the kernel by running:
```bash
make -j$(nproc)
```

The `bzImage` should be located in `arch/x86/boot/bzImage`.

Running `make -j$(nproc) modules_install INSTALL_MOD_PATH=[DIRECTORY]`, and then compressing the `[DIRECTORY]` should give you the compressed modules.
