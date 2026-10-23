#!/bin/sh
set -eu
cd "$HOME/splatoon3-native-rl-stage0"
if ! .venv/bin/python -c 'import ziglang' >/dev/null 2>&1; then
 .venv/bin/uv pip install --python .venv/bin/python --index-url https://pypi.org/simple ziglang==0.13.0
fi
mkdir -p toolchain/debs toolchain/sysroot
cd toolchain/debs
apt-get download libpython3.13-dev
for package in ./*.deb; do dpkg-deb -x "$package" ../sysroot; done
cd ../..
cat > cc-zig <<'CC'
#!/bin/sh
root="$HOME/splatoon3-native-rl-stage0"
exec "$root/.venv/bin/python" -m ziglang cc -target x86_64-linux-gnu -I"$root/toolchain/sysroot/usr/include" -I"$root/toolchain/sysroot/usr/include/python3.13" -I"$root/toolchain/sysroot/usr/include/x86_64-linux-gnu/python3.13" "$@"
CC
chmod 700 cc-zig
./cc-zig --version
