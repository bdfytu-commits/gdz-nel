#!/usr/bin/env bash
# =========================================================
# Сборка APK для ГДЗ НЭЛ через Bubblewrap (TWA-обёртка PWA).
#
# Требования (без sudo, всё ставится в домашний каталог):
#   - JDK 17            (/usr/lib/jvm/java-17-openjdk)
#   - Android SDK       (~/Android/Sdk + platforms;android-36)
#   - bubblewrap CLI    (npm i @bubblewrap/cli в отдельной папке)
#   - запущенный сервер: uv run python -m http.server 8000
#
# Использование:
#   bash scripts/build_apk.sh init    # создать android-twa/
#   bash scripts/build_apk.sh build   # собрать и подписать, положить в download/app.apk
#
# Пароли keystore по умолчанию берутся из переменных окружения
#   BUBBLEWRAP_KEYSTORE_PASSWORD и BUBBLEWRAP_KEY_PASSWORD.
# Файл подписи лежит в android-signing/ и в git не попадает.
# =========================================================
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
JDK="${JAVA_HOME:-/usr/lib/jvm/java-17-openjdk}"
SDK="${ANDROID_HOME:-$HOME/Android/Sdk}"
# на этой машине bubblewrap уже стоит в /tmp/opencode/bw — запускать так:
#   BUBBLEWRAP_DIR=/tmp/opencode/bw bash scripts/build_apk.sh build
BUBBLEWRAP_DIR="${BUBBLEWRAP_DIR:-$HOME/.local/share/gdz-nel-bubblewrap}"
TWA_DIR="$ROOT/android-twa"
KEYSTORE_DIR="$ROOT/android-signing"
MANIFEST_URL="${MANIFEST_URL:-http://localhost:8000/app/manifest.json}"

export JAVA_HOME="$JDK"
export ANDROID_HOME="$SDK"
export ANDROID_SDK_ROOT="$SDK"
export PATH="$JAVA_HOME/bin:$PATH"
export BUBBLEWRAP_KEYSTORE_PASSWORD="${BUBBLEWRAP_KEYSTORE_PASSWORD:-gdznel2026}"
export BUBBLEWRAP_KEY_PASSWORD="${BUBBLEWRAP_KEY_PASSWORD:-gdznel2026}"

need() {
  command -v "$1" >/dev/null 2>&1 || { echo "нет $1 — поставь и повтори"; exit 1; }
}

case "${1:-build}" in
  init)
    need java
    need npm
    mkdir -p "$KEYSTORE_DIR" "$BUBBLEWRAP_DIR"
    if [ ! -x "$BUBBLEWRAP_DIR/node_modules/.bin/bubblewrap" ]; then
      (cd "$BUBBLEWRAP_DIR" && npm init -y >/dev/null && npm install @bubblewrap/cli)
    fi
    echo "bubblewrap init — отвечай на вопросы, JDK: $JDK, Android SDK: $SDK"
    echo "keystore советую положить в $KEYSTORE_DIR/keystore.jks"
    (cd "$BUBBLEWRAP_DIR" && ./node_modules/.bin/bubblewrap init \
      --manifest "$MANIFEST_URL" --directory "$TWA_DIR")
    ;;

  build)
    need java
    [ -d "$TWA_DIR" ] || { echo "сначала: bash scripts/build_apk.sh init"; exit 1; }
    if [ ! -x "$BUBBLEWRAP_DIR/node_modules/.bin/bubblewrap" ]; then
      echo "bubblewrap не установлен: bash scripts/build_apk.sh init"; exit 1
    fi
    # androidbrowserhelper 2.7.x требует minSdk >= 24, а bubblewrap init ставит 21
    [ -f "$TWA_DIR/app/build.gradle" ] && sed -i 's/minSdkVersion 21/minSdkVersion 24/' "$TWA_DIR/app/build.gradle"
    [ -f "$TWA_DIR/twa-manifest.json" ] && sed -i 's/"minSdkVersion": 21,/"minSdkVersion": 24,/' "$TWA_DIR/twa-manifest.json"
    echo "если bubblewrap спросит про изменения twa-manifest.json — нажми Enter (применить)"
    (cd "$TWA_DIR" && "$BUBBLEWRAP_DIR/node_modules/.bin/bubblewrap" build --skipPwaValidation)
    # подписанный APK bubblewrap кладёт в корень проекта
    APK="$TWA_DIR/app-release-signed.apk"
    if [ ! -f "$APK" ]; then
      APK="$(ls -t "$TWA_DIR"/app/build/outputs/apk/release/*.apk 2>/dev/null | head -1 || true)"
    fi
    if [ -z "${APK:-}" ] || [ ! -f "$APK" ]; then
      echo "APK не найден — смотри вывод сборки"; exit 1
    fi
    cp "$APK" "$ROOT/download/app.apk"
    echo "готово: download/app.apk ($(du -h "$ROOT/download/app.apk" | cut -f1))"
    ;;

  *)
    echo "использование: bash scripts/build_apk.sh [init|build]"; exit 1
    ;;
esac
