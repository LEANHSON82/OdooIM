/** @odoo-module **/

import { CalendarFormModel } from "@calendar/views/calendar_form/calendar_form_model";
import { patch } from "@web/core/utils/patch";

/**
 * Preserve Google Meet URLs returned by the server instead of letting the
 * calendar form turn them back into Discuss links.
 */
patch(CalendarFormModel.Record.prototype, {
    async setLocation() {
        if (this.resModel !== "calendar.event") {
            return super.setLocation(...arguments);
        }
        const videoLocation = await this.model.discussVideocallLocation;
        const isGoogleMeet = videoLocation && videoLocation.includes("meet.google.com");
        this.update({
            access_token: isGoogleMeet ? false : videoLocation.split("/").pop(),
            videocall_location: videoLocation,
            videocall_source: isGoogleMeet ? "google_meet" : "discuss",
        });
    },
});
