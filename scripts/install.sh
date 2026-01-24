#!/bin/bash
#
# Install skill-chrome-log
#
# This script:
# 1. Installs Python dependencies to shared venv
# 2. Creates CLI wrapper at ~/.claude/scripts/chrome-log
# 3. Creates chrome-debug shell function
# 4. Creates Chrome Debug launcher app with purple icon
# 5. Links skill to ~/.claude/skills/chrome-log
#
# Usage:
#   ./install.sh
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
VENV_DIR="$HOME/.claude/.venv"
SCRIPTS_DIR="$HOME/.claude/scripts"
SKILLS_DIR="$HOME/.claude/skills"
LAUNCHER_APP="$HOME/.chrome-debug-launcher.app"

echo "Installing skill-chrome-log..."
echo

# 1. Install dependencies
echo "Installing Python dependencies..."
if [[ -d "$VENV_DIR" ]]; then
    "$VENV_DIR/bin/pip" install -q -r "$PROJECT_DIR/requirements.txt"
else
    echo "Warning: Shared venv not found at $VENV_DIR"
    echo "Creating new venv..."
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
cat > "$PROJECT_DIR/shell-config.sh" << 'EOF'
# Chrome Log aliases
alias chrome-debug="$HOME/Repos/skill-chrome-log/scripts/chrome-debug.sh"
alias chrome-log="$HOME/.claude/scripts/chrome-log"
EOF
echo "  Created: $PROJECT_DIR/shell-config.sh"
echo

# 4. Create Chrome Debug launcher app
echo "Creating Chrome Debug launcher app..."

# Check for ImageMagick
if ! command -v convert &> /dev/null; then
    echo "  Warning: ImageMagick not installed (brew install imagemagick)"
    echo "  Skipping launcher app with custom icon"
else
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
    <string>com.modha.chrome-debug-launcher</string>
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

        # Convert icns to png, tint purple, convert back
        sips -s format png "$CHROME_ICNS" --out "$TEMP_DIR/chrome.png" > /dev/null 2>&1
        convert "$TEMP_DIR/chrome.png" -fill '#8B5CF6' -colorize 40% "$TEMP_DIR/purple.png"

        # Create iconset
        mkdir -p "$TEMP_DIR/AppIcon.iconset"
        for size in 16 32 128 256 512; do
            sips -z $size $size "$TEMP_DIR/purple.png" --out "$TEMP_DIR/AppIcon.iconset/icon_${size}x${size}.png" > /dev/null 2>&1
            size2=$((size * 2))
            sips -z $size2 $size2 "$TEMP_DIR/purple.png" --out "$TEMP_DIR/AppIcon.iconset/icon_${size}x${size}@2x.png" > /dev/null 2>&1
        done

        # Convert to icns
        iconutil -c icns "$TEMP_DIR/AppIcon.iconset" -o "$LAUNCHER_APP/Contents/Resources/AppIcon.icns" 2>/dev/null || {
            # Fallback: just copy the tinted PNG
            cp "$TEMP_DIR/purple.png" "$LAUNCHER_APP/Contents/Resources/AppIcon.icns"
        }

        rm -rf "$TEMP_DIR"
        echo "  Created: $LAUNCHER_APP (with purple icon)"
    else
        echo "  Warning: Chrome icon not found, created app without custom icon"
    fi
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
chmod +x "$PROJECT_DIR/scripts/"*.sh
chmod +x "$PROJECT_DIR/scripts/"*.py
echo

# Done
echo "=========================================="
echo "Installation complete!"
echo
echo "Next steps:"
echo
echo "1. Add to your shell config (~/.zshrc or ~/.bashrc):"
echo "   source ~/Repos/skill-chrome-log/shell-config.sh"
echo
echo "2. Restart your terminal or run:"
echo "   source ~/Repos/skill-chrome-log/shell-config.sh"
echo
echo "3. Verify installation:"
echo "   chrome-log doctor"
echo
if [[ -d "$LAUNCHER_APP" ]]; then
    echo "4. (Optional) Drag Chrome Debug to Dock:"
    echo "   open -R \"$LAUNCHER_APP\""
    echo
fi
echo "Usage:"
echo "   chrome-debug          # Start Chrome in debug mode"
echo "   chrome-log start      # Start capture daemon"
echo "   chrome-log tail       # View recent requests"
echo "   open http://localhost:9223  # Live status page"
