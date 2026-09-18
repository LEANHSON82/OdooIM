import uuid
import logging
from datetime import datetime, timedelta, timezone

from odoo import models, api
from odoo.addons.google_calendar.models.google_sync import google_calendar_token

_logger = logging.getLogger(__name__)


class CalendarEvent(models.Model):
    _inherit = 'calendar.event'

    @api.model
    def get_discuss_videocall_location(self):
        """Override: try to create a Google Meet link instead of Discuss."""
        user = self.env.user
        try:
            with google_calendar_token(user) as token:
                if token:
                    meet_url = self._create_google_meet_link(token)
                    if meet_url:
                        return meet_url
        except Exception as error:
            _logger.warning(
                "Failed to get a Google Calendar token for Meet link creation: %s",
                error,
            )
        return super().get_discuss_videocall_location()

    @api.model
    def get_videocall_source(self):
        """Return the videocall source type for the current user."""
        user = self.env.user
        if user.sudo().google_calendar_token:
            return 'google_meet'
        return 'discuss'

    def _create_google_meet_link(self, token):
        """Create a temporary Google Calendar event to get a Meet link.

        Google has no endpoint that mints a bare Meet link. The only way
        is to create an event asking for conferenceData, read the link
        back, then delete that throwaway event.
        """
        try:
            from odoo.addons.google_calendar.utils.google_calendar import GoogleCalendarService
            google_service = self.env['google.service']
            cal_service = GoogleCalendarService(google_service)

            # Naive UTC: the dateTime values below append their own 'Z'.
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            values = {
                'summary': 'Odoo Meeting',
                'start': {'dateTime': now.isoformat() + 'Z'},
                'end': {'dateTime': (now + timedelta(hours=1)).isoformat() + 'Z'},
                'conferenceData': {
                    'createRequest': {
                        'requestId': uuid.uuid4().hex,
                        'conferenceSolutionKey': {'type': 'hangoutsMeet'},
                    }
                },
            }

            result = cal_service.insert(
                values, token=token, timeout=10, need_video_call=True
            )

            if result:
                conference_data = result.get('conferenceData', {})
                entry_points = conference_data.get('entryPoints', [])
                video_entries = [
                    ep for ep in entry_points
                    if ep.get('entryPointType') == 'video'
                ]
                meet_url = video_entries[0].get('uri') if video_entries else None

                # Drop the throwaway event; a failure here only leaves
                # one stray hour on the user's Google calendar.
                google_event_id = result.get('id')
                if google_event_id:
                    try:
                        cal_service.delete(google_event_id, token=token, timeout=5)
                    except Exception:
                        pass

                if meet_url:
                    _logger.info("Google Meet link created: %s", meet_url)
                    return meet_url

        except Exception as e:
            _logger.warning("Failed to create Google Meet link: %s", e)

        return False

    def _google_values(self):
        """Override to always request conferenceData for new events."""
        values = super()._google_values()
        if not self.google_id:
            values['conferenceData'] = {
                'createRequest': {
                    'requestId': uuid.uuid4().hex,
                    'conferenceSolutionKey': {'type': 'hangoutsMeet'},
                }
            }
        return values
