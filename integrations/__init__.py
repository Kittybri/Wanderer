"""Optional external-service adapters; unconfigured services remain disabled."""

from .services import (
    AsyncJSONClient, GitHubIssueService, GoogleCalendarService, GoogleSheetsService,
    GoogleTasksService, IntegrationAuthError, IntegrationConfig, IntegrationError,
    LetterboxdService, MyAnimeListService, SpotifyService, SteamService,
    load_integration_config,
)

__all__ = [name for name in globals() if not name.startswith("_")]
