"""Test the Journiv config flow."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant import config_entries
from homeassistant.const import CONF_EMAIL, CONF_HOST, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.journiv.api import (
    JournivApi,
    JournivAuthenticationError,
    JournivConnectionError,
)
from custom_components.journiv.const import (
    CONF_JOURNAL_IDS,
    CONF_REFRESH_TOKEN,
    DOMAIN,
)

TEST_HOST = "http://journiv.example.com"
TEST_EMAIL = "test@example.com"
TEST_PASSWORD = "test-password"
TEST_USER_ID = "12345678-1234-1234-1234-123456789abc"
TEST_SECOND_EMAIL = "second@example.com"
TEST_SECOND_USER_ID = "87654321-4321-4321-4321-cba987654321"
TEST_JOURNAL_ID = "11111111-1111-1111-1111-111111111111"
TEST_SECOND_JOURNAL_ID = "22222222-2222-2222-2222-222222222222"
TEST_REFRESH_TOKEN = "refresh-token"

TEST_USER_INPUT = {
    CONF_HOST: TEST_HOST,
    CONF_EMAIL: TEST_EMAIL,
    CONF_PASSWORD: TEST_PASSWORD,
}

TEST_USER = {
    "id": TEST_USER_ID,
    "email": TEST_EMAIL,
}

TEST_SECOND_USER_INPUT = {
    CONF_HOST: TEST_HOST,
    CONF_EMAIL: TEST_SECOND_EMAIL,
    CONF_PASSWORD: TEST_PASSWORD,
}

TEST_SECOND_USER = {
    "id": TEST_SECOND_USER_ID,
    "email": TEST_SECOND_EMAIL,
}

TEST_JOURNALS = [
    {"id": TEST_JOURNAL_ID, "title": "Personal"},
    {"id": TEST_SECOND_JOURNAL_ID, "title": "Travel"},
]


async def test_form(
    hass: HomeAssistant,
    mock_setup_entry: AsyncMock,
) -> None:
    """Test successful configuration and journal selection."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {}
    assert result["description_placeholders"] == {
        "example_url": "https://journiv.example.com:8443",
        "http_scheme": "http://",
        "https_scheme": "https://",
    }

    with (
        patch(
            "custom_components.journiv.config_flow.JournivApi.authenticate",
            new_callable=AsyncMock,
        ),
        patch(
            "custom_components.journiv.config_flow.JournivApi.get_current_user",
            new_callable=AsyncMock,
            return_value=TEST_USER,
        ),
        patch(
            "custom_components.journiv.config_flow.JournivApi.get_journals",
            new_callable=AsyncMock,
            return_value=TEST_JOURNALS,
        ),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            TEST_USER_INPUT,
        )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "journals"
    assert result["data_schema"]({}) == {
        CONF_JOURNAL_IDS: [TEST_JOURNAL_ID, TEST_SECOND_JOURNAL_ID]
    }
    assert len(mock_setup_entry.mock_calls) == 0

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_JOURNAL_IDS: [TEST_JOURNAL_ID]},
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == TEST_EMAIL
    assert result["data"] == TEST_USER_INPUT
    assert result["options"] == {CONF_JOURNAL_IDS: [TEST_JOURNAL_ID]}
    assert result["result"].unique_id == TEST_USER_ID
    assert len(mock_setup_entry.mock_calls) == 1


async def test_form_stores_refresh_token(
    hass: HomeAssistant,
    mock_setup_entry: AsyncMock,
) -> None:
    """Test the refresh token is stored for future reloads."""
    api = MagicMock(spec=JournivApi)
    api.refresh_token = TEST_REFRESH_TOKEN
    api.authenticate = AsyncMock()
    api.get_current_user = AsyncMock(return_value=TEST_USER)
    api.get_journals = AsyncMock(return_value=TEST_JOURNALS)

    with patch(
        "custom_components.journiv.config_flow.JournivApi",
        return_value=api,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], TEST_USER_INPUT
        )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_JOURNAL_IDS: [TEST_JOURNAL_ID]}
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {
        **TEST_USER_INPUT,
        CONF_REFRESH_TOKEN: TEST_REFRESH_TOKEN,
    }
    assert result["result"].unique_id == TEST_USER_ID
    assert len(mock_setup_entry.mock_calls) == 1


@pytest.mark.parametrize(
    ("exception", "error"),
    [
        pytest.param(
            JournivAuthenticationError("Invalid credentials"),
            "invalid_auth",
            id="invalid-auth",
        ),
        pytest.param(
            JournivConnectionError("Connection failed"),
            "cannot_connect",
            id="cannot-connect",
        ),
    ],
)
async def test_form_authentication_error_recovery(
    hass: HomeAssistant,
    mock_setup_entry: AsyncMock,
    exception: Exception,
    error: str,
) -> None:
    """Test an authentication error and recovery."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
    )

    with patch(
        "custom_components.journiv.config_flow.JournivApi.authenticate",
        new_callable=AsyncMock,
        side_effect=exception,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            TEST_USER_INPUT,
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": error}

    with (
        patch(
            "custom_components.journiv.config_flow.JournivApi.authenticate",
            new_callable=AsyncMock,
        ),
        patch(
            "custom_components.journiv.config_flow.JournivApi.get_current_user",
            new_callable=AsyncMock,
            return_value=TEST_USER,
        ),
        patch(
            "custom_components.journiv.config_flow.JournivApi.get_journals",
            new_callable=AsyncMock,
            return_value=TEST_JOURNALS,
        ),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            TEST_USER_INPUT,
        )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "journals"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_JOURNAL_IDS: [TEST_JOURNAL_ID]},
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert len(mock_setup_entry.mock_calls) == 1


async def test_form_cannot_fetch_journals(
    hass: HomeAssistant,
    mock_setup_entry: AsyncMock,
) -> None:
    """Test a journal discovery failure."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
    )

    with (
        patch(
            "custom_components.journiv.config_flow.JournivApi.authenticate",
            new_callable=AsyncMock,
        ),
        patch(
            "custom_components.journiv.config_flow.JournivApi.get_current_user",
            new_callable=AsyncMock,
            return_value=TEST_USER,
        ),
        patch(
            "custom_components.journiv.config_flow.JournivApi.get_journals",
            new_callable=AsyncMock,
            side_effect=JournivConnectionError("Connection failed"),
        ),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            TEST_USER_INPUT,
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}
    assert len(mock_setup_entry.mock_calls) == 0

    with (
        patch(
            "custom_components.journiv.config_flow.JournivApi.authenticate",
            new_callable=AsyncMock,
        ),
        patch(
            "custom_components.journiv.config_flow.JournivApi.get_current_user",
            new_callable=AsyncMock,
            return_value=TEST_USER,
        ),
        patch(
            "custom_components.journiv.config_flow.JournivApi.get_journals",
            new_callable=AsyncMock,
            return_value=TEST_JOURNALS,
        ),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], TEST_USER_INPUT
        )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_JOURNAL_IDS: [TEST_JOURNAL_ID]}
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == TEST_USER_ID
    assert len(mock_setup_entry.mock_calls) == 1


async def test_duplicate_entry(
    hass: HomeAssistant,
    mock_setup_entry: AsyncMock,
) -> None:
    """Test that duplicate Journiv accounts cannot be configured."""
    with (
        patch(
            "custom_components.journiv.config_flow.JournivApi.authenticate",
            new_callable=AsyncMock,
        ),
        patch(
            "custom_components.journiv.config_flow.JournivApi.get_current_user",
            new_callable=AsyncMock,
            return_value=TEST_USER,
        ),
        patch(
            "custom_components.journiv.config_flow.JournivApi.get_journals",
            new_callable=AsyncMock,
            return_value=TEST_JOURNALS,
        ),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], TEST_USER_INPUT
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_JOURNAL_IDS: [TEST_JOURNAL_ID]}
        )

        assert result["type"] is FlowResultType.CREATE_ENTRY
        assert result["result"].unique_id == TEST_USER_ID

        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], TEST_USER_INPUT
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert len(mock_setup_entry.mock_calls) == 1


async def test_multiple_accounts_on_same_host(
    hass: HomeAssistant,
    mock_setup_entry: AsyncMock,
) -> None:
    """Test that different accounts on the same host can be configured."""
    with (
        patch(
            "custom_components.journiv.config_flow.JournivApi.authenticate",
            new_callable=AsyncMock,
        ),
        patch(
            "custom_components.journiv.config_flow.JournivApi.get_current_user",
            new_callable=AsyncMock,
            side_effect=[TEST_USER, TEST_SECOND_USER],
        ),
        patch(
            "custom_components.journiv.config_flow.JournivApi.get_journals",
            new_callable=AsyncMock,
            return_value=TEST_JOURNALS,
        ),
    ):
        for user_input in (TEST_USER_INPUT, TEST_SECOND_USER_INPUT):
            result = await hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": config_entries.SOURCE_USER},
            )
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"], user_input
            )
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"], {CONF_JOURNAL_IDS: [TEST_JOURNAL_ID]}
            )

            assert result["type"] is FlowResultType.CREATE_ENTRY

    entries = hass.config_entries.async_entries(DOMAIN)
    assert {entry.unique_id for entry in entries} == {
        TEST_USER_ID,
        TEST_SECOND_USER_ID,
    }
    assert len(mock_setup_entry.mock_calls) == 2


async def test_options_flow(
    hass: HomeAssistant,
    mock_setup_entry: AsyncMock,
) -> None:
    """Test updating the selected journals."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=TEST_EMAIL,
        unique_id=TEST_USER_ID,
        data={**TEST_USER_INPUT, CONF_REFRESH_TOKEN: TEST_REFRESH_TOKEN},
        options={CONF_JOURNAL_IDS: [TEST_JOURNAL_ID]},
    )
    entry.add_to_hass(hass)

    with (
        patch(
            "custom_components.journiv.config_flow.JournivApi.authenticate",
            new_callable=AsyncMock,
        ) as mock_authenticate,
        patch(
            "custom_components.journiv.config_flow.JournivApi.refresh_access_token",
            new_callable=AsyncMock,
        ) as mock_refresh_access_token,
        patch(
            "custom_components.journiv.config_flow.JournivApi.get_journals",
            new_callable=AsyncMock,
            return_value=TEST_JOURNALS,
        ),
    ):
        result = await hass.config_entries.options.async_init(entry.entry_id)

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"
    assert result["data_schema"]({}) == {CONF_JOURNAL_IDS: [TEST_JOURNAL_ID]}
    mock_refresh_access_token.assert_awaited_once_with(TEST_REFRESH_TOKEN)
    mock_authenticate.assert_not_awaited()

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {CONF_JOURNAL_IDS: [TEST_SECOND_JOURNAL_ID]},
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == {CONF_JOURNAL_IDS: [TEST_SECOND_JOURNAL_ID]}
    assert len(mock_setup_entry.mock_calls) == 1


@pytest.mark.parametrize(
    ("method", "exception", "reason"),
    [
        pytest.param(
            "authenticate",
            JournivAuthenticationError("Invalid credentials"),
            "invalid_auth",
            id="invalid-auth",
        ),
        pytest.param(
            "get_journals",
            JournivConnectionError("Connection failed"),
            "cannot_connect",
            id="cannot-connect",
        ),
    ],
)
async def test_options_flow_error(
    hass: HomeAssistant,
    method: str,
    exception: Exception,
    reason: str,
) -> None:
    """Test errors while loading the options flow."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=TEST_EMAIL,
        unique_id=TEST_USER_ID,
        data=TEST_USER_INPUT,
        options={CONF_JOURNAL_IDS: [TEST_JOURNAL_ID]},
    )
    entry.add_to_hass(hass)

    with (
        patch(
            "custom_components.journiv.config_flow.JournivApi.authenticate",
            new_callable=AsyncMock,
            side_effect=exception if method == "authenticate" else None,
        ),
        patch(
            "custom_components.journiv.config_flow.JournivApi.get_journals",
            new_callable=AsyncMock,
            side_effect=exception if method == "get_journals" else None,
        ),
    ):
        result = await hass.config_entries.options.async_init(entry.entry_id)

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == reason
