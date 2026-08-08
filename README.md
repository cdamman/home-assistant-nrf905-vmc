# nRF905 VMC — Home Assistant integration

[![HACS Custom][hacs-badge]][hacs-repository]
[![Latest release][release-badge]][releases]
[![Downloads][downloads-badge]][releases]
[![Tests][tests-badge]][tests-workflow]
[![Validate][validate-badge]][validate-workflow]
[![License][license-badge]][license]

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

### With HACS (recommended)

Add this repository to HACS as a custom repository of type *Integration*, then
install *nRF905 VMC* and restart Home Assistant:

[![Open your Home Assistant instance and open this repository inside HACS.][hacs-repository-badge]][hacs-repository]

### Manually

Copy `custom_components/nrf905_vmc/` into your Home Assistant
`config/custom_components/` folder and restart.

### Add the integration

Then add the *nRF905 VMC* integration and enter the IP address, username and
password:

[![Open your Home Assistant instance and start setting up a new integration.][config-flow-badge]][config-flow-start]

## Development

The integration is covered by a `pytest` suite built on
[`pytest-homeassistant-custom-component`][phcc], run on every push and pull
request together with the HACS and hassfest validations.

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements_test.txt

pytest --cov=custom_components.nrf905_vmc --cov-report=term-missing
ruff check custom_components tests
ruff format --check custom_components tests
```

## Credits

Based on the [nRF905-API](https://github.com/eelcohn/nRF905-API) project by
eelcohn for the nRF905 device API.

<!-- Badges & links -->

[hacs-badge]: https://img.shields.io/badge/HACS-Custom-41BDF5.svg?style=for-the-badge
[release-badge]: https://img.shields.io/github/v/release/cdamman/home-assistant-nrf905-vmc?style=for-the-badge
[downloads-badge]: https://img.shields.io/github/downloads/cdamman/home-assistant-nrf905-vmc/total?style=for-the-badge
[tests-badge]: https://img.shields.io/github/actions/workflow/status/cdamman/home-assistant-nrf905-vmc/tests.yml?branch=main&label=tests&style=for-the-badge
[validate-badge]: https://img.shields.io/github/actions/workflow/status/cdamman/home-assistant-nrf905-vmc/validate.yml?branch=main&label=validate&style=for-the-badge
[license-badge]: https://img.shields.io/github/license/cdamman/home-assistant-nrf905-vmc?style=for-the-badge
[hacs-repository-badge]: https://my.home-assistant.io/badges/hacs_repository.svg
[config-flow-badge]: https://my.home-assistant.io/badges/config_flow_start.svg
[releases]: https://github.com/cdamman/home-assistant-nrf905-vmc/releases
[license]: https://github.com/cdamman/home-assistant-nrf905-vmc/blob/main/LICENSE
[tests-workflow]: https://github.com/cdamman/home-assistant-nrf905-vmc/actions/workflows/tests.yml
[validate-workflow]: https://github.com/cdamman/home-assistant-nrf905-vmc/actions/workflows/validate.yml
[hacs-repository]: https://my.home-assistant.io/redirect/hacs_repository/?owner=cdamman&repository=home-assistant-nrf905-vmc&category=integration
[config-flow-start]: https://my.home-assistant.io/redirect/config_flow_start/?domain=nrf905_vmc
[phcc]: https://github.com/MatthewFlamm/pytest-homeassistant-custom-component
