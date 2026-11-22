# Journiv for Home Assistant

![Journiv](custom_components/journiv/brand/icon.png)

Monitor your [Journiv](https://www.journiv.com) account and selected journals in Home Assistant.

## Features

- Choose which journals Home Assistant imports during setup and change the selection later.
- Create an account overview device using your Journiv profile name.
- Create a separate device for each selected journal.
- Reuse refresh tokens so routine reloads do not repeatedly sign in to Journiv.
- Update statistics every five minutes.

### Account entities

- Current and longest writing streak
- Total entries and total words
- Average words per entry
- Last entry date
- Current mood logging streak and days logged
- Last mood log date
- Mood logs and most frequent mood over the last 30 days

### Journal entities

- Entry count
- Total words
- Last entry date and time
- Favorite status
- Archived status

## Installation

### HACS

Until Journiv is included in the default HACS repository list:

1. Open HACS in Home Assistant.
2. Select **Integrations**, then open the three-dot menu and choose **Custom repositories**.
3. Add `https://github.com/aled2305/ha-journiv` with the category **Integration**.
4. Search for **Journiv** and install it.
5. Restart Home Assistant.

### Manual

Copy `custom_components/journiv` into the `custom_components` directory in your Home Assistant configuration directory, then restart Home Assistant.

## Configuration

In Home Assistant, go to **Settings** > **Devices & services** > **Add integration** and search for **Journiv**. Enter the full URL of your Journiv server and your account credentials, then select the journals you want to monitor.

The integration communicates directly with the Journiv server URL you provide. Credentials and authentication tokens are stored in Home Assistant's config entry storage.

## Requirements

- Home Assistant 2026.11.0 or newer
- A reachable Journiv server and account

## Support

Report problems through [GitHub Issues](https://github.com/aled2305/ha-journiv/issues). Include the Home Assistant and Journiv versions, relevant logs with sensitive values removed, and the steps needed to reproduce the problem.

## Development

Install the test dependency and run the test suite:

```bash
python -m pip install -r requirements_test.txt
pytest
```

## License

This project is licensed under the Apache License 2.0.
