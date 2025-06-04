# vasttrafik
Implementation of the vasttrafik api for HACS

# Västtrafik Journey Sensor (HACS)

This is a custom Home Assistant integration for Västtrafik journey planning using the Travel Planner v4 API.

## Features
- Journey-based public transport sensor
- Uses Västtrafik's official API
- Supports multiple departures, lines, and destinations
- UI-based configuration (config flow) and YAML support
- Unique entity IDs for registry support

## Installation
1. Copy the `vasttrafik` folder to your `custom_components` directory, or add this repository as a custom repository in HACS (type: Integration).
2. Restart Home Assistant.
3. Add the integration via the Home Assistant UI (recommended) or YAML.

## Configuration
### UI (Recommended)
- Go to Home Assistant > Settings > Devices & Services > Add Integration > Västtrafik.
- Enter your API key and secret.
- Add departures via the options menu after setup.

### YAML (Legacy)
```yaml
sensor:
  - platform: vasttrafik
    key: YOUR_API_KEY
    secret: YOUR_API_SECRET
    departures:
      - from: "Göteborg"
        destination: "Borås"
        delay: 0
        lines: ["100"]
        name: "To Borås"
```

## Troubleshooting
- Ensure your API credentials are correct and have access to the Västtrafik Travel Planner v4 API.
- If you see errors about credentials, re-check your API key/secret.
- At least one departure must be configured in the options flow.

## Credits
- Based on the official Västtrafik API
- Custom integration by Engineer-Ash

## License
MIT
