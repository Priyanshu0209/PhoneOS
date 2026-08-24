#!/bin/bash
# Local testing / manual startup script

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"

if [ ! -d "venv" ]; then
    echo "Error: Virtual environment not found. Please run install.sh first."
    exit 1
fi

source venv/bin/activate

echo "Starting SwarmOS DroneOS..."
python3 -m DroneOS.main DroneOS/configs/
