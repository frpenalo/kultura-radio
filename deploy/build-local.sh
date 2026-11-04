#!/bin/bash
# Fabrica de builds local de Kultura Radio. Corre desatendida (nohup).
set -e
cd /opt/kultura-app
export ANDROID_HOME=/opt/android-sdk
export JAVA_HOME=$(dirname $(dirname $(readlink -f $(which java))))
export GRADLE_OPTS="-Xmx3g -Dorg.gradle.daemon=false"
echo "=== npm ci ==="
npm ci --silent
echo "=== cuenta: $(npx eas-cli whoami 2>/dev/null | head -1) ==="
echo "=== build local ==="
nice -n 19 ionice -c 3 npx eas-cli build --platform android --profile preview --local --non-interactive --output /tmp/kultura-local.apk
echo "=== BUILD_OK ==="
ls -la /tmp/kultura-local.apk
