# nRF905 VMC — Home Assistant integration

Home Assistant integration to control a mechanical ventilation unit (VMC)
through the nRF905 HTTP bridge.

It builds on eelcohn's **nRF905-API** project, which exposes the HTTP API this
integration talks to: <https://github.com/eelcohn/nRF905-API>

## Features

- **One device per IP address**, with credentials (username / password) entered
  at setup and editable afterwards (Reconfigure / automatic re-authentication).
- **`fan` entity** with three speeds shown as **1 - Bas**, **2 - Normal**,
  **3 - Fort** (French labels, including in Google Home), plus an on/off "boost"
  command: `On` -> `high` with an auto-revert timer, `Off` -> `medium`.
- **"Timer duration" number**: delay in minutes (default 30, 1–240), kept
  across restarts.
- **"Timer remaining" sensor**: countdown driven by the device `timer` flag.
- **"Current consumption" sensor** (power, W): 13 / 28 / 58.5 W depending on the
  speed.
- **"Today's consumption" sensor** (energy, kWh, diagnostic): integrated from
  the power, reset at local midnight and restored across restarts.
- **Flicker-free** on/off tile in Google Home (optimistic state) and **error
  tolerance** (entities go unavailable only after 3 consecutive failed polls).

## Installation

Copy `custom_components/nrf905_vmc/` into your Home Assistant
`config/custom_components/` folder, restart, then add the *nRF905 VMC*
integration and enter the IP address, username and password.

## Credits

Based on the [nRF905-API](https://github.com/eelcohn/nRF905-API) project by
eelcohn for the nRF905 device API.
