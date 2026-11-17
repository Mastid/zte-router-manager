#!/bin/bash
# 一键构建 APK（无需 Gradle）
set -e
ROOT="$(cd "$(dirname "$0")" && pwd)"
JDK="$ROOT/jdk-17.0.2/bin"
BT="$ROOT/sdk/build-tools/34.0.0"
PLATFORM="$ROOT/sdk/platforms/android-34/android.jar"
OUT="$ROOT/out"
APP="$ROOT/app"

export JAVA_HOME="$(cygpath -w "$ROOT/jdk-17.0.2")"
export PATH="$ROOT/jdk-17.0.2/bin:$PATH"

echo "== 0. 从 panel.html 重新生成内置页面（必须先于打包，否则 APK 里是旧界面）=="
python "$ROOT/make_assets.py"

echo "== 1. 资源编译 =="
rm -rf "$OUT"
mkdir -p "$OUT/gen" "$OUT/classes" "$OUT/dex"
"$BT/aapt2" compile --dir "$APP/res" -o "$OUT/res.zip"
"$BT/aapt2" link -o "$OUT/app.unsigned.apk" -I "$PLATFORM" \
  --manifest "$APP/AndroidManifest.xml" -A "$APP/assets" \
  --java "$OUT/gen" --auto-add-overlay \
  --min-sdk-version 21 --target-sdk-version 34 \
  --version-code 60 --version-name "2.9.9" \
  "$OUT/res.zip"

echo "== 2. 编译 Java =="
find app/src out/gen -name "*.java" > "$OUT/sources.txt"
"$JDK/javac" -encoding UTF-8 -nowarn -source 8 -target 8 \
  -classpath "$PLATFORM" -d "$OUT/classes" @"$OUT/sources.txt"

echo "== 3. 转 DEX =="
find "$OUT/classes" -name "*.class" | sed "s|^$OUT/||" > "$OUT/classes.txt"
(cd "$OUT" && cmd //c "$(cygpath -w "$BT")\\d8.bat" --release --min-api 21 --lib "$(cygpath -w "$PLATFORM")" \
  --output "$(cygpath -w "$OUT")\\dex" @"$(cygpath -w "$OUT/classes.txt")")

echo "== 4. 打包 =="
cp "$OUT/app.unsigned.apk" "$OUT/app.base.apk"
"$JDK/jar" -uf "$OUT/app.base.apk" -C "$OUT/dex" classes.dex

echo "== 5. 对齐与签名 =="
"$BT/zipalign" -f 4 "$OUT/app.base.apk" "$OUT/app.aligned.apk"
if [ ! -f "$ROOT/debug.keystore" ]; then
  "$JDK/keytool" -genkeypair -keystore "$ROOT/debug.keystore" \
    -alias router -storepass android -keypass android \
    -dname "CN=ZTE Router Manager,O=Home,C=CN" \
    -keyalg RSA -keysize 2048 -validity 10000
fi
"$BT/apksigner.bat" sign --ks "$ROOT/debug.keystore" --ks-pass pass:android \
  --key-pass pass:android --out "$ROOT/ZTE-RouterManager-v2.9.9.apk" \
  "$OUT/app.aligned.apk"
"$BT/apksigner.bat" verify "$ROOT/ZTE-RouterManager-v2.9.9.apk"

ls -la "$ROOT/ZTE-RouterManager-v2.9.9.apk"
echo "== 构建完成 =="
