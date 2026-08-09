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
- **"Current consumption" sensor** (power, W): derived from the speed, using the
  **configurable** power draw of each speed (13 / 28 / 58.5 W by default).
- **"Today's consumption" sensor** (energy, kWh, diagnostic): integrated from
  the power, reset at local midnight and restored across restarts.
- **Flicker-free** on/off tile in Google Home (optimistic state) and **error
  tolerance** (entities go unavailable only after 3 consecutive failed polls).

## Installation

### With HACS (recommended)

This integration is not in the HACS default store, so it has to be added as a
**custom repository**. The quickest way is this button, which opens the
repository straight inside your own HACS:

[![Open your Home Assistant instance and open this repository inside HACS.][hacs-repository-badge]][hacs-repository]

#### Adding the repository by URL

If the button does not work — no [My Home Assistant][my-ha] redirect
configured, a hardened network, or HACS opened from a phone — add the URL by
hand instead:

1. In Home Assistant, go to **HACS** in the sidebar.
2. Open the **⋮** menu at the top right and choose **Custom repositories**.
3. Paste this URL in the *Repository* field:

   ```text
   https://github.com/cdamman/home-assistant-nrf905-vmc
   ```

4. Pick **Integration** as the *Type*, then select **Add**.
5. Close the dialog, search for **nRF905 VMC** in HACS and select
   **Download**.
6. Restart Home Assistant.

The repository then behaves like any other HACS integration: new releases show
up as updates, and you can remove it again from the same *Custom repositories*
dialog.

### Manually

Without HACS, download `nrf905_vmc.zip` from the [latest release][releases],
create a `nrf905_vmc` folder inside your Home Assistant
`config/custom_components/` folder, extract the archive into it and restart.
Updates have to be done the same way by hand.

Installing from a checkout of the repository works too, but the `version` in
`custom_components/nrf905_vmc/manifest.json` is the `0.0.0` placeholder there:
the real version is stamped into the release archive (see
[Releasing](#releasing)), so Home Assistant will report `0.0.0`.

### Add the integration

Then add the *nRF905 VMC* integration and enter the IP address, username and
password:

[![Open your Home Assistant instance and start setting up a new integration.][config-flow-badge]][config-flow-start]

## Configuration

### Power consumption

The nRF905 bridge does not report how much the unit draws, so the *Current
consumption* and *Today's consumption* sensors derive it from the power of each
speed. The defaults are the values of the unit this integration was written
against:

| Speed | Default power |
| --- | --- |
| 1 - Bas | 13 W |
| 2 - Normal | 28 W |
| 3 - Fort | 58.5 W |

If your unit differs, enter its own values in **Settings → Devices & services →
nRF905 VMC → Configure**. The entry reloads immediately and both sensors pick up
the new figures — today's accumulated energy is kept, so only the consumption
from that point on is counted at the new rate.

Values are per config entry, so several units can each have their own.

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

### Releasing

`manifest.json` in the repository is not the version users get — the `version`
key there is a fixed `0.0.0` placeholder, and the release tag is the source of
truth. It is never bumped by hand, so it cannot drift out of sync with the
tags.

Publishing a GitHub release runs the *Release* workflow, which checks out the
tag, writes the tag (minus a leading `v`) into `manifest.json`, zips the
contents of `custom_components/nrf905_vmc/` and attaches the archive to the
release as `nrf905_vmc.zip`. `hacs.json` sets `zip_release`, so HACS downloads
that asset instead of the repository source: tagging `v1.2.0` is all it takes
for Home Assistant to report version `1.2.0`.

So the release process is just: tag, publish the release, done. A tag that is
not a usable version number (`nightly`, say) fails the workflow instead of
shipping an integration Home Assistant cannot load. The workflow can also be
re-run by hand from the Actions tab against an existing tag, which is how a
release published before this workflow existed gets its asset.

The archive holds the integration files at its root, with no
`custom_components/` prefix — that is what HACS expects, since it extracts
straight into `config/custom_components/nrf905_vmc/`.

The zip only comes into play for a release. Installing the default branch from
HACS still copies the repository source, placeholder included, so a reported
version of `0.0.0` is the expected symptom of running `main` rather than a
release.

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
[my-ha]: https://my.home-assistant.io/
