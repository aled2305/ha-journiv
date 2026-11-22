"""API client for Journiv."""

from typing import Any, NotRequired, TypedDict

from aiohttp import ClientError, ClientSession


class JournivApiError(Exception):
    """Base exception for Journiv API errors."""


class JournivAuthenticationError(JournivApiError):
    """Authentication failed."""


class JournivConnectionError(JournivApiError):
    """Unable to connect to Journiv."""


class JournivJournal(TypedDict):
    """A Journiv journal returned by the API."""

    id: str
    title: str
    entry_count: int
    total_words: int
    last_entry_at: str | None
    is_favorite: bool
    is_archived: bool


class JournivUser(TypedDict):
    """A Journiv user profile."""

    id: str
    email: str
    name: NotRequired[str | None]


class JournivWritingAnalytics(TypedDict):
    """Account-level writing analytics."""

    current_streak: int
    longest_streak: int
    total_entries: int
    total_words: int
    average_words_per_entry: float
    last_entry_date: NotRequired[str]


class JournivMostFrequentMood(TypedDict):
    """Most frequently logged mood."""

    name: str
    category: str
    count: int


class JournivMoodStatistics(TypedDict):
    """Account-level mood statistics for the default 30-day window."""

    total_logs: int
    most_frequent_mood: NotRequired[JournivMostFrequentMood]


class JournivMoodStreak(TypedDict):
    """Account-level mood logging streak."""

    current_streak: int
    total_days_logged: int
    last_logged_date: NotRequired[str]


class JournivApi:
    """Client for the Journiv REST API."""

    def __init__(
        self,
        session: ClientSession,
        host: str,
    ) -> None:
        """Initialize the API client."""
        self.session = session
        self.host = host.rstrip("/")
        self.access_token: str | None = None
        self.refresh_token: str | None = None

    async def authenticate(
        self,
        email: str,
        password: str,
    ) -> dict[str, Any]:
        """Authenticate with Journiv."""

        url = f"{self.host}/api/v1/auth/login"

        try:
            async with self.session.post(
                url,
                json={
                    "email": email,
                    "password": password,
                },
                headers={
                    "X-Journiv-Client": "legacy",
                },
            ) as response:
                if response.status == 401:
                    raise JournivAuthenticationError("Invalid email or password")

                response.raise_for_status()
                data = await response.json()

                self.access_token = data["access_token"]
                self.refresh_token = data.get("refresh_token")

                return data

        except ClientError as err:
            raise JournivConnectionError("Unable to communicate with Journiv") from err

    async def get_current_user(self) -> JournivUser:
        """Retrieve the authenticated user."""

        if not self.access_token:
            raise JournivAuthenticationError("Not authenticated")

        url = f"{self.host}/api/v1/users/me"

        try:
            async with self.session.get(
                url,
                headers={
                    "Authorization": f"Bearer {self.access_token}",
                },
            ) as response:
                if response.status == 401:
                    raise JournivAuthenticationError("Access token expired or invalid")

                response.raise_for_status()

                data: JournivUser = await response.json()
                return data

        except ClientError as err:
            raise JournivConnectionError("Unable to communicate with Journiv") from err

    async def refresh_access_token(self, refresh_token: str) -> None:
        """Refresh the access token."""
        url = f"{self.host}/api/v1/auth/refresh"

        try:
            async with self.session.post(
                url,
                json={"refresh_token": refresh_token},
            ) as response:
                if response.status == 401:
                    raise JournivAuthenticationError("Refresh token expired or invalid")

                response.raise_for_status()
                data = await response.json()

                self.access_token = data["access_token"]
                self.refresh_token = refresh_token

        except ClientError as err:
            raise JournivConnectionError("Unable to communicate with Journiv") from err

    async def get_journals(self) -> list[JournivJournal]:
        """Retrieve the authenticated user's active journals."""

        if not self.access_token:
            raise JournivAuthenticationError("Not authenticated")

        url = f"{self.host}/api/v1/journals/"

        try:
            async with self.session.get(
                url,
                headers={
                    "Authorization": f"Bearer {self.access_token}",
                },
            ) as response:
                if response.status == 401:
                    raise JournivAuthenticationError("Access token expired or invalid")

                response.raise_for_status()

                data: list[JournivJournal] = await response.json()
                return data

        except ClientError as err:
            raise JournivConnectionError("Unable to communicate with Journiv") from err

    async def get_writing_analytics(self) -> JournivWritingAnalytics:
        """Retrieve account-level writing analytics."""
        data: JournivWritingAnalytics = await self._async_get_authenticated(
            "/api/v1/analytics/writing-streak"
        )
        return data

    async def get_mood_statistics(self) -> JournivMoodStatistics:
        """Retrieve account-level mood statistics."""
        data: JournivMoodStatistics = await self._async_get_authenticated(
            "/api/v1/moods/analytics/statistics"
        )
        return data

    async def get_mood_streak(self) -> JournivMoodStreak:
        """Retrieve the account-level mood logging streak."""
        data: JournivMoodStreak = await self._async_get_authenticated(
            "/api/v1/moods/analytics/streak"
        )
        return data

    async def _async_get_authenticated(self, path: str) -> Any:
        """Get an authenticated API resource."""
        if not self.access_token:
            raise JournivAuthenticationError("Not authenticated")

        try:
            async with self.session.get(
                f"{self.host}{path}",
                headers={"Authorization": f"Bearer {self.access_token}"},
            ) as response:
                if response.status == 401:
                    raise JournivAuthenticationError("Access token expired or invalid")

                response.raise_for_status()
                return await response.json()

        except ClientError as err:
            raise JournivConnectionError("Unable to communicate with Journiv") from err
