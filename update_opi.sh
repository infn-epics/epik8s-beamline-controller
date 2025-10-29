#!/bin/bash
# Quick script to regenerate OPI display from configuration

echo "Generating OPI display from configuration..."
python3 generate_opi.py "$@"

if [ $? -eq 0 ]; then
    echo ""
    echo "✓ OPI display generated successfully!"
    echo ""
    echo "You can now open test.bob in Phoebus/CS-Studio to view the display."
    echo ""
    echo "Tip: Run this script whenever you modify test-config.yaml to update the display."
else
    echo ""
    echo "✗ Failed to generate OPI display"
    exit 1
fi
