# Västtrafik Journey Sensor (Home Assistant Custom Integration)

A Home Assistant custom integration for Västtrafik journey planning using the official Travel Planner v4 API.

## Features
- Journey-based public transport sensors
- Uses Västtrafik's official API
- Supports multiple departures, lines, and destinations
- **Journey list sensor**: List all departures/arrivals for a route in a configurable time window (e.g., all buses from A to B between 6am and 9am)
- UI-based configuration (config flow) and YAML support
- Unique entity IDs for registry support
- Pause/resume updates for each journey via switch entity

## Installation
1. Add this repository as a custom repository in HACS (type: Integration), or copy the `vastraffik-journey` folder to your `custom_components` directory.
2. Restart Home Assistant.
3. Add the integration via Home Assistant UI (Settings → Devices & Services → Add Integration → Västtrafik Journey).

## Configuration
### UI (Recommended)
- Go to Home Assistant > Settings > Devices & Services > Add Integration > Västtrafik Journey.
- Enter your API client ID and secret.
- Add departures via the options menu after setup (Settings → Devices & Services → Västtrafik Journey → Configure).

### YAML (Legacy, not recommended)
```yaml
sensor:
  - platform: vastraffik_journey
    client_id: YOUR_CLIENT_ID
    secret: YOUR_API_SECRET
    departures:
      - from: "Göteborg"
        destination: "Borås"
        delay: 0
        lines: ["100"]
        name: "To Borås"
    journey_list_sensors:
      - from: "Göteborg"
        destination: "Borås"
        lines: ["100"]
        name: "Morning Buses"
        list_start_time: "06:00"
        list_end_time: "09:00"
        list_time_relates_to: "departure"  # or "arrival"
```

## Example Home Assistant Dashboard Card
Display your journey sensor, its attributes, and the pause switch in a dashboard Entities card:

```yaml
type: entities
entities:
  - entity: sensor.vastraffik_journey_1  # Replace with your actual journey sensor entity_id
    name: Next Departure
  - type: attribute
    entity: sensor.vastraffik_journey_1
    attribute: connections
    name: Connections
  - type: attribute
    entity: sensor.vastraffik_journey_1
    attribute: final_arrival
    name: Final Arrival
  - entity: switch.pause_vastraffik_journey_1  # This switch allows you to pause/unpause updates for this journey
  - type: attribute
    entity: sensor.morning_buses  # Example journey list sensor
    attribute: journeys
    name: Morning Departures
# Optionally, you can adjust grid_options and title as needed:
grid_options:
  columns: 48
  rows: auto
title: Your Journey Title
```
Replace `vastraffik_journey_1` with your actual journey sensor entity ID (e.g., `sensor.vastraffik_journey_1`).

## Troubleshooting
- Ensure your API credentials are correct and have access to the Västtrafik Travel Planner v4 API.
- If you see errors about credentials, re-check your API client ID and secret.
- At least one departure must be configured in the options flow.
- Pause switches are named like `switch.pause_vastraffik_journey_1`, etc.
- Use the UI to add, edit, or remove journeys and to control the pause state.

## Credits
- Based on the official Västtrafik API
- Custom integration by Engineer-Ash

## License
MIT
