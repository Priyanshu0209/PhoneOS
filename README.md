# PhoneOS

## Overview
PhoneOS is a comprehensive project designed for drone operation, command, and control. The system includes a Python-based core (DroneOS) for direct drone communication via MAVSDK, a relay component for handling real-time communications, and a mobile application built with React, Vite, and Capacitor that serves as a ground control interface with mapping capabilities (using Leaflet).

## Features
- **Drone Control and Telemetry**: Uses MAVSDK for communicating with drones via Python (DroneOS).
- **Communication Relay**: A Python-based WebSocket relay server for bridging communications.
- **Mobile Ground Control**: A React-based mobile application wrapped in Capacitor for Android deployment, featuring Leaflet maps for telemetry visualization.
- **Multi-Drone Support**: Contains configurations and scripts (`start_drone2.py`, `start_drone3.py`) to launch and manage multiple drones.
- **System Service Configuration**: Bash scripts for installing dependencies and configuring systemd services on Raspberry Pi for automated startup.

## Architecture
The system is divided into three primary components:
1. **DroneOS**: The core Python package managing vehicle connection, telemetry logging, sensor inputs, and mission handling.
2. **Relay**: A WebSocket-based relay that facilitates communication between the mobile app and the DroneOS instances.
3. **Mobile App**: A cross-platform frontend (primarily targeting Android) that provides the user interface for monitoring and controlling the drones.

## Project Structure
- `DroneOS/`, `DroneOS1/`, `DroneOS2/`: Core Python packages for controlling the drone(s) using MAVSDK and Msgpack RPC.
- `mobile/`: The React/Vite/Capacitor application for mobile ground control.
- `relay/`: A WebSocket relay server (`relay.py`) for routing messages.
- `tests/` & `.pytest_cache/`: Python test suites for the core OS.
- `deploy/`, `deploy.sh`: Deployment scripts and configurations.
- `setup_pi.sh`: Script to install DroneOS as a systemd service on a Raspberry Pi.
- `setup_android.sh`: Environment setup script for Android SDK and OpenJDK to build the mobile app.
- `start_drone2.py`, `start_drone3.py`: Scripts for starting specific drone instances.

## Technology Stack
- **Languages**: Python 3, JavaScript / TypeScript, Bash
- **Frontend / Mobile**: React, Vite, Capacitor, Leaflet (react-leaflet)
- **Drone Communication**: MAVSDK (Python)
- **Relay / Network**: WebSockets, Msgpack RPC
- **Configuration**: Pydantic, PyYAML

## Requirements
- **Python**: Python 3.8+ (for DroneOS and Relay)
- **Node.js**: Node.js and npm (for the mobile app build process)
- **Java/Android**: OpenJDK 17 and Android SDK Command-line Tools (for Capacitor Android builds)
- **OS**: Linux (tested on Raspberry Pi/Ubuntu)

## Installation

### Python Components (DroneOS & Relay)
1. Create and activate a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate
   ```
2. Install DroneOS dependencies:
   ```bash
   pip install -r DroneOS/requirements.txt
   ```
3. Install Relay dependencies:
   ```bash
   pip install -r relay/requirements.txt
   ```

### Mobile Application
1. Navigate to the `mobile` directory:
   ```bash
   cd mobile
   ```
2. Install dependencies:
   ```bash
   npm install
   ```

## Configuration
- DroneOS uses YAML configuration files and Pydantic models (located in `configs` and `shared/config`).
- Environment variables may be set in a `.env` file (which is safely ignored by Git).
- For mobile app Android builds, run `./setup_android.sh` to configure Java and Android SDK paths.

## Usage

### Running the Python Systems
- Start individual drone instances using the provided root scripts:
  ```bash
  python start_drone2.py
  ```
- To run the relay server:
  ```bash
  cd relay
  python relay.py
  ```

### Running the Mobile App
- Start the Vite development server:
  ```bash
  cd mobile
  npm run dev
  ```
- Build for Android (Debug):
  ```bash
  npm run android:debug
  ```

### Deploying to Raspberry Pi
- Run the setup script to install DroneOS as a systemd service (requires sudo):
  ```bash
  sudo ./setup_pi.sh
  ```

## Current Status
Active development. Core DroneOS features (sensor integration, configuration loading, MAVSDK connection) and mobile interface with maps are structured. Deployment scripts for Pi and Android are functioning, and multi-drone testing scripts are available in the root.
