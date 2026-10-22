# Heatit WiFi6 / WiFi7 Integration for Home Assistant

This integration provides support for Heatit WiFi6 and Heatit WiFi7 thermostats in Home Assistant. 
The device is also sold under various other names depending on the region, such as "Älytermostaatti Pistesarjat WiFi6" in Finland.

## Disclaimer
This software is a third-party integration and is not affiliated with, maintained, or supported by Heatit (Thermo-Floor AS). Use it at your own risk.

## Supported Devices
* Heatit WiFi6 Thermostat (Firmware v2.20 and newer)
* Heatit WiFi7 Thermostat (tested with firmware 0.1.16: status, setpoint and temperature sensors, energy and power. The WiFi7 relay mode, BlueFusion and DirectLink are not supported.)

## Installation

### Method 1: HACS (Recommended)
1. Ensure [HACS](https://hacs.xyz/) is installed.
2. Go to **HACS** -> **Integrations**.
3. Click the three dots in the top right corner and select **Custom repositories**.
4. Add the URL to this repository, select **Integration** as the category, and click **Add**.
5. Find "Heatit WiFi6" in the list and click **Install**.
6. Restart Home Assistant.

### Method 2: Manual Installation
1. Download the `heatit_wifi6` folder from `custom_components/` in this repository.
2. Copy the folder into your Home Assistant `config/custom_components/` directory.
3. Restart Home Assistant.

## Setup
1. Ensure your thermostat is connected to your local WiFi network via the official Heatit mobile app.
2. In Home Assistant, go to **Settings** -> **Devices & Services** -> **Add Integration**.
3. Search for **Heatit WiFi6**.
4. Enter a descriptive name for your device.
5. Enter the local IP address of the thermostat (e.g., `http://192.168.1.50`).
6. Submit the configuration.

## Features & Usage
* **Sensor Modes:** Supports Floor, Internal, and External sensor modes. The current temperature entity automatically reflects the active sensor mode.
* **Attributes:** Detailed thermostat parameters are exposed as device attributes.
* **Polling:** The integration polls the device once per minute for status updates.
* **Advanced Control:** Parameters can be changed via HTTP POST requests to `/api/parameters` on the device. For technical details, refer to the OpenAPI documentation in the `docs` folder.
* **Energy Meter:** Reset the kWh meter by sending a DELETE request to `/api/reset/kwh` on the device.

## Version History
* **1.1.2**
    * Prepared for official PR.
    * Synchronized domain and logic for better compatibility.
* **1.1.1**
    * Enhanced stability and logic improvements.
* **0.9.4**
    * Current temperature is now dynamically based on the **sensorMode** configured on the device (Floor, Internal, or External).
* **0.9.3**
    * Initial Release

## License
This software is licensed under the [MIT License](LICENSE.md).