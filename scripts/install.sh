#!/bin/bash
#
# Install skill-chrome-log
#
# This script:
# 1. Checks dependencies (Python 3, Chrome)
# 2. Installs Python dependencies to shared venv
# 3. Creates CLI wrapper at ~/.claude/scripts/chrome-log
# 4. Creates chrome-debug shell function
# 5. Creates Chrome Debug launcher app with purple icon
# 6. Links skill to ~/.claude/skills/chrome-log
# 7. Optionally adds to shell config
#
# Usage:
#   ./install.sh           # Full install
#   ./install.sh --check   # Dry-run dependency check
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
VENV_DIR="$HOME/.claude/.venv"
SCRIPTS_DIR="$HOME/.claude/scripts"
SKILLS_DIR="$HOME/.claude/skills"
LAUNCHER_APP="$HOME/Applications/Chrome Debug.app"
SHELL_CONFIG="$HOME/.zshrc"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
NC='\033[0m' # No Color

# Parse args
CHECK_ONLY=false
if [[ "$1" == "--check" ]]; then
    CHECK_ONLY=true
fi

# Pre-flight dependency checks
check_dependencies() {
    echo "Checking dependencies..."
    local has_errors=false

    # Python 3
    if command -v python3 &> /dev/null; then
        local py_version=$(python3 --version 2>&1)
        echo -e "  ${GREEN}[OK]${NC} Python 3: $py_version"
    else
        echo -e "  ${RED}[!!]${NC} Python 3 not found"
        echo "       → Install: brew install python3"
        has_errors=true
    fi

    # Chrome
    if [[ -d "/Applications/Google Chrome.app" ]]; then
        echo -e "  ${GREEN}[OK]${NC} Google Chrome installed"
    else
        echo -e "  ${RED}[!!]${NC} Google Chrome not found"
        echo "       → Download: https://www.google.com/chrome/"
        has_errors=true
    fi

    # ImageMagick (optional)
    if command -v magick &> /dev/null || command -v convert &> /dev/null; then
        echo -e "  ${GREEN}[OK]${NC} ImageMagick installed"
    else
        echo -e "  ${YELLOW}[--]${NC} ImageMagick not installed (optional, for purple icon)"
        echo "       → Install: brew install imagemagick"
    fi

    # websockets package check
    if [[ -d "$VENV_DIR" ]] && "$VENV_DIR/bin/pip" show websockets &> /dev/null; then
        echo -e "  ${GREEN}[OK]${NC} websockets package installed"
    else
        echo -e "  ${YELLOW}[--]${NC} websockets package not installed (will install)"
    fi

    echo

    if $has_errors; then
        echo -e "${RED}Missing required dependencies. Please install them first.${NC}"
        return 1
    fi

    echo -e "${GREEN}All required dependencies present.${NC}"
    return 0
}

# Check if shell config already has our source line
shell_config_has_source() {
    grep -q "skill-chrome-log/shell-config.sh" "$SHELL_CONFIG" 2>/dev/null
}

# Main install
do_install() {
    echo "Installing skill-chrome-log..."
    echo

    # 1. Install dependencies
    echo "Installing Python dependencies..."
    if [[ -d "$VENV_DIR" ]]; then
        "$VENV_DIR/bin/pip" install -q -r "$PROJECT_DIR/requirements.txt"
    else
        echo "  Creating shared venv at $VENV_DIR..."
        python3 -m venv "$VENV_DIR"
        "$VENV_DIR/bin/pip" install -q -r "$PROJECT_DIR/requirements.txt"
    fi
    echo "  Done"
    echo

    # 2. Create CLI wrapper
    echo "Creating CLI wrapper..."
    mkdir -p "$SCRIPTS_DIR"
    cat > "$SCRIPTS_DIR/chrome-log" << EOF
#!/bin/bash
exec "$VENV_DIR/bin/python" "$PROJECT_DIR/scripts/chrome_log.py" "\$@"
EOF
    chmod +x "$SCRIPTS_DIR/chrome-log"
    echo "  Created: $SCRIPTS_DIR/chrome-log"
    echo

    # 3. Create shell alias file
    echo "Creating shell configuration..."
    cat > "$PROJECT_DIR/shell-config.sh" << EOF
# Chrome Log aliases
alias chrome-debug="$PROJECT_DIR/scripts/chrome-debug.sh"
alias chrome-log="$HOME/.claude/scripts/chrome-log"
EOF
    echo "  Created: $PROJECT_DIR/shell-config.sh"
    echo

    # 4. Create Chrome Debug launcher app
    echo "Creating Chrome Debug launcher app..."

    # Check for ImageMagick (prefer 'magick' for v7, fallback to 'convert')
    if command -v magick &> /dev/null; then
        IMAGEMAGICK_CMD="magick"
    elif command -v convert &> /dev/null; then
        IMAGEMAGICK_CMD="convert"
    else
        IMAGEMAGICK_CMD=""
    fi

    if [[ -n "$IMAGEMAGICK_CMD" ]]; then
        # Create app bundle structure
        rm -rf "$LAUNCHER_APP"
        mkdir -p "$LAUNCHER_APP/Contents/MacOS"
        mkdir -p "$LAUNCHER_APP/Contents/Resources"

        # Create Info.plist
        cat > "$LAUNCHER_APP/Contents/Info.plist" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key>
    <string>launch</string>
    <key>CFBundleIconFile</key>
    <string>AppIcon</string>
    <key>CFBundleIdentifier</key>
    <string>local.chrome-debug-launcher</string>
    <key>CFBundleName</key>
    <string>Chrome Debug</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleVersion</key>
    <string>1.0</string>
    <key>LSMinimumSystemVersion</key>
    <string>10.15</string>
    <key>LSUIElement</key>
    <false/>
</dict>
</plist>
EOF

        # Create launcher script
        cat > "$LAUNCHER_APP/Contents/MacOS/launch" << EOF
#!/bin/bash
exec "$PROJECT_DIR/scripts/chrome-debug.sh"
EOF
        chmod +x "$LAUNCHER_APP/Contents/MacOS/launch"

        # Extract and tint Chrome icon
        CHROME_ICNS="/Applications/Google Chrome.app/Contents/Resources/app.icns"
        if [[ -f "$CHROME_ICNS" ]]; then
            # Create temp directory for icon processing
            TEMP_DIR=$(mktemp -d)

            # Convert icns to png, hue-shift 180 degrees (opposite colors)
            sips -s format png "$CHROME_ICNS" --out "$TEMP_DIR/chrome.png" > /dev/null 2>&1
            $IMAGEMAGICK_CMD "$TEMP_DIR/chrome.png" -modulate 100,100,50 "$TEMP_DIR/shifted.png"

            # Create iconset
            mkdir -p "$TEMP_DIR/AppIcon.iconset"
            for size in 16 32 128 256 512; do
                sips -z $size $size "$TEMP_DIR/shifted.png" --out "$TEMP_DIR/AppIcon.iconset/icon_${size}x${size}.png" > /dev/null 2>&1
                size2=$((size * 2))
                sips -z $size2 $size2 "$TEMP_DIR/shifted.png" --out "$TEMP_DIR/AppIcon.iconset/icon_${size}x${size}@2x.png" > /dev/null 2>&1
            done

            # Convert to icns
            iconutil -c icns "$TEMP_DIR/AppIcon.iconset" -o "$LAUNCHER_APP/Contents/Resources/AppIcon.icns" 2>/dev/null || {
                # Fallback: just copy the tinted PNG
                cp "$TEMP_DIR/purple.png" "$LAUNCHER_APP/Contents/Resources/AppIcon.icns"
            }

            rm -rf "$TEMP_DIR"
            echo "  Created: $LAUNCHER_APP (with inverted colors icon)"
        else
            echo "  Warning: Chrome icon not found"
        fi
    else
        echo "  Skipped: ImageMagick not installed"
    fi
    echo

    # 5. Link skill
    echo "Linking skill..."
    mkdir -p "$SKILLS_DIR"
    if [[ -L "$SKILLS_DIR/chrome-log" ]]; then
        rm "$SKILLS_DIR/chrome-log"
    fi
    ln -s "$PROJECT_DIR" "$SKILLS_DIR/chrome-log"
    echo "  Linked: $SKILLS_DIR/chrome-log -> $PROJECT_DIR"
    echo

    # 6. Make scripts executable
    chmod +x "$PROJECT_DIR/scripts/"*.sh 2>/dev/null || true
    chmod +x "$PROJECT_DIR/scripts/"*.py 2>/dev/null || true

    # 7. Shell config handling
    echo "=========================================="
    echo "Installation complete!"
    echo

    if shell_config_has_source; then
        echo "Shell config already configured."
        echo
    else
        echo "Add to shell config?"
        echo
        echo "  This will add the following to $SHELL_CONFIG:"
        echo "    source $PROJECT_DIR/shell-config.sh"
        echo
        read -p "Add to $SHELL_CONFIG? [y/N] " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            echo "" >> "$SHELL_CONFIG"
            echo "# Chrome Log" >> "$SHELL_CONFIG"
            echo "source $PROJECT_DIR/shell-config.sh" >> "$SHELL_CONFIG"
            echo -e "${GREEN}Added to $SHELL_CONFIG${NC}"
            echo
            echo "Run this to activate now:"
            echo "  source $SHELL_CONFIG"
        else
            echo "Skipped. To activate manually, run:"
            echo "  source $PROJECT_DIR/shell-config.sh"
        fi
        echo
    fi

    echo "Verify installation:"
    echo "  chrome-log doctor"
    echo
    echo "Usage:"
    echo "  chrome-debug          # Start Chrome in debug mode"
    echo "  chrome-log start      # Start capture daemon"
    echo "  chrome-log tail       # View recent requests"
    echo
    if [[ -d "$LAUNCHER_APP" ]]; then
        echo "(Optional) Drag Chrome Debug to Dock:"
        echo "  open -R \"$LAUNCHER_APP\""
    fi
}

# Main
echo
if $CHECK_ONLY; then
    check_dependencies
    exit $?
else
    if ! check_dependencies; then
        exit 1
    fi
    echo
    do_install
fi
