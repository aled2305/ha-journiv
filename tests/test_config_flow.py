"""Test the Journiv config flow."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant import config_entries
from custom_components.journiv.api import (
    JournivApi,
    JournivAuthenticationError,
    JournivConnectionError,
)
from custom_components.journiv.config_flow import CannotConnect, InvalidHost
from custom_components.journiv.const import (
    CONF_JOURNAL_IDS,
    CONF_REFRESH_TOKEN,
    DOMAIN,
)
from homeassistant.const import CONF_EMAIL, CONF_HOST, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

TEST_HOST = "http://journiv.example.com"
TEST_EMAIL = "test@example.com"
TEST_PASSWORD = "test-password"
TEST_USER_ID = "12345678-1234-1234-1234-123456789abc"
TEST_UNIQUE_ID = f"{TEST_HOST}#{TEST_USER_ID}"
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
    assert result["result"].unique_id == TEST_UNIQUE_ID
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
        CONF_HOST: TEST_HOST,
        CONF_EMAIL: TEST_EMAIL,
        CONF_REFRESH_TOKEN: TEST_REFRESH_TOKEN,
    }
    assert result["result"].unique_id == TEST_UNIQUE_ID
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
        pytest.param(RuntimeError("Unexpected response"), "unknown", id="unknown"),
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


@pytest.mark.parametrize(
    ("exception", "error"),
    [
        pytest.param(
            JournivAuthenticationError("Expired token"),
            "invalid_auth",
            id="invalid-auth",
        ),
        pytest.param(
            JournivConnectionError("Connection failed"),
            "cannot_connect",
            id="cannot-connect",
        ),
        pytest.param(RuntimeError("Unexpected response"), "unknown", id="unknown"),
    ],
)
async def test_form_cannot_fetch_journals(
    hass: HomeAssistant,
    mock_setup_entry: AsyncMock,
    exception: Exception,
    error: str,
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
            side_effect=exception,
        ),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            TEST_USER_INPUT,
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": error}
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
    assert result["result"].unique_id == TEST_UNIQUE_ID
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
        assert result["result"].unique_id == TEST_UNIQUE_ID

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
        TEST_UNIQUE_ID,
        f"{TEST_HOST}#{TEST_SECOND_USER_ID}",
    }
    assert len(mock_setup_entry.mock_calls) == 2


async def test_same_user_id_on_different_hosts(
    hass: HomeAssistant,
    mock_setup_entry: AsyncMock,
) -> None:
    """Test identical server-local user IDs can be configured on different hosts."""
    second_host = "https://second.example.com"
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
        for host in (TEST_HOST, second_host):
            result = await hass.config_entries.flow.async_init(
                DOMAIN, context={"source": config_entries.SOURCE_USER}
            )
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"], {**TEST_USER_INPUT, CONF_HOST: host}
            )
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"], {CONF_JOURNAL_IDS: []}
            )
            assert result["type"] is FlowResultType.CREATE_ENTRY

    assert {entry.unique_id for entry in hass.config_entries.async_entries(DOMAIN)} == {
        TEST_UNIQUE_ID,
        f"{second_host}#{TEST_USER_ID}",
    }
    assert len(mock_setup_entry.mock_calls) == 2


async def test_invalid_url_recovery(
    hass: HomeAssistant,
    mock_setup_entry: AsyncMock,
) -> None:
    """Test an invalid server URL can be corrected."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**TEST_USER_INPUT, CONF_HOST: "not-a-url"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_url"}

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
        result["flow_id"], {CONF_JOURNAL_IDS: []}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert len(mock_setup_entry.mock_calls) == 1


async def test_reauth_error_recovery(
    hass: HomeAssistant,
    mock_setup_entry: AsyncMock,
) -> None:
    """Test reauthentication replaces the stored credentials."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=TEST_EMAIL,
        unique_id=TEST_UNIQUE_ID,
        version=2,
        data={
            CONF_HOST: TEST_HOST,
            CONF_EMAIL: TEST_EMAIL,
            CONF_REFRESH_TOKEN: "expired-token",
        },
    )
    entry.add_to_hass(hass)
    api = MagicMock(spec=JournivApi)
    api.refresh_token = TEST_REFRESH_TOKEN
    api.authenticate = AsyncMock(
        side_effect=[JournivAuthenticationError("Invalid credentials"), None]
    )
    api.get_current_user = AsyncMock(return_value=TEST_USER)

    with patch("custom_components.journiv.config_flow.JournivApi", return_value=api):
        result = await entry.start_reauth_flow(hass)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_EMAIL: TEST_EMAIL, CONF_PASSWORD: "wrong-password"},
        )
        assert result["type"] is FlowResultType.FORM
        assert result["errors"] == {"base": "invalid_auth"}

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_EMAIL: TEST_EMAIL, CONF_PASSWORD: TEST_PASSWORD},
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data == {
        CONF_HOST: TEST_HOST,
        CONF_EMAIL: TEST_EMAIL,
        CONF_REFRESH_TOKEN: TEST_REFRESH_TOKEN,
    }
    assert len(mock_setup_entry.mock_calls) == 1


@pytest.mark.parametrize(
    ("exception", "error"),
    [
        pytest.param(CannotConnect(), "cannot_connect", id="cannot-connect"),
        pytest.param(InvalidHost(), "invalid_url", id="invalid-url"),
        pytest.param(RuntimeError("Unexpected response"), "unknown", id="unknown"),
    ],
)
async def test_reauth_other_error_recovery(
    hass: HomeAssistant,
    mock_setup_entry: AsyncMock,
    exception: Exception,
    error: str,
) -> None:
    """Test other reauthentication errors can be corrected."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=TEST_EMAIL,
        unique_id=TEST_UNIQUE_ID,
        version=2,
        data={CONF_HOST: TEST_HOST, CONF_EMAIL: TEST_EMAIL},
    )
    entry.add_to_hass(hass)
    api = MagicMock(spec=JournivApi)
    api.refresh_token = TEST_REFRESH_TOKEN
    info = {
        "api": api,
        "title": TEST_EMAIL,
        "user_id": TEST_USER_ID,
        "data": TEST_USER_INPUT,
    }

    with patch(
        "custom_components.journiv.config_flow.validate_input",
        new_callable=AsyncMock,
        side_effect=[exception, info],
    ):
        result = await entry.start_reauth_flow(hass)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_EMAIL: TEST_EMAIL, CONF_PASSWORD: TEST_PASSWORD},
        )
        assert result["type"] is FlowResultType.FORM
        assert result["errors"] == {"base": error}

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_EMAIL: TEST_EMAIL, CONF_PASSWORD: TEST_PASSWORD},
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert len(mock_setup_entry.mock_calls) == 1


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


async def test_options_flow_updates_refresh_token(hass: HomeAssistant) -> None:
    """Test the options flow persists a newly issued refresh token."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=TEST_EMAIL,
        unique_id=TEST_UNIQUE_ID,
        version=2,
        data={
            CONF_HOST: TEST_HOST,
            CONF_EMAIL: TEST_EMAIL,
            CONF_REFRESH_TOKEN: "old-token",
        },
        options={CONF_JOURNAL_IDS: []},
    )
    entry.add_to_hass(hass)
    api = MagicMock(spec=JournivApi)
    api.refresh_token = TEST_REFRESH_TOKEN
    api.refresh_access_token = AsyncMock()
    api.get_journals = AsyncMock(return_value=TEST_JOURNALS)

    with patch("custom_components.journiv.config_flow.JournivApi", return_value=api):
        result = await hass.config_entries.options.async_init(entry.entry_id)

    assert result["type"] is FlowResultType.FORM
    assert entry.data == {
        CONF_HOST: TEST_HOST,
        CONF_EMAIL: TEST_EMAIL,
        CONF_REFRESH_TOKEN: TEST_REFRESH_TOKEN,
    }


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
        pytest.param(
            "get_journals",
            RuntimeError("Unexpected response"),
            "unknown",
            id="unknown",
        ),
    ],
)
async def test_options_flow_error(
    hass: HomeAssistant,
    mock_setup_entry: AsyncMock,
    method: str,
    exception: Exception,
    reason: str,
) -> None:
    """Test errors while loading the options flow."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=TEST_EMAIL,
        unique_id=TEST_UNIQUE_ID,
        data=TEST_USER_INPUT,
        options={CONF_JOURNAL_IDS: [TEST_JOURNAL_ID]},
    )
    entry.add_to_hass(hass)

    with (
        patch(
            "custom_components.journiv.config_flow.JournivApi.authenticate",
            new_callable=AsyncMock,
            side_effect=[exception, None] if method == "authenticate" else None,
        ),
        patch(
            "custom_components.journiv.config_flow.JournivApi.get_journals",
            new_callable=AsyncMock,
            side_effect=(
                [exception, TEST_JOURNALS]
                if method == "get_journals"
                else [TEST_JOURNALS]
            ),
        ),
    ):
        result = await hass.config_entries.options.async_init(entry.entry_id)
        assert result["type"] is FlowResultType.FORM
        assert result["errors"] == {"base": reason}

        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {CONF_JOURNAL_IDS: []}
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {}

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_JOURNAL_IDS: [TEST_SECOND_JOURNAL_ID]}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == {CONF_JOURNAL_IDS: [TEST_SECOND_JOURNAL_ID]}
    assert len(mock_setup_entry.mock_calls) == 1
