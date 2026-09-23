import { onWillUnmount } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { ListController } from "@web/views/list/list_controller";
import { listView } from "@web/views/list/list_view";

const POLL_DELAY = 3000;

// Lookups run in the background, so the list reloads itself.
export class BusinessStatusListController extends ListController {
    setup() {
        super.setup();
        this.polling = false;
        this.pollTimer = setInterval(() => this._pollQueue(), POLL_DELAY);
        onWillUnmount(() => clearInterval(this.pollTimer));
    }

    get queuedRecords() {
        return this._collectRecords(this.model.root).filter(
            (record) => record.data.state === "queued"
        );
    }

    // Records of the whole list, grouped lists included.
    _collectRecords(list) {
        const records = [...(list.records || [])];
        for (const group of list.groups || []) {
            records.push(...this._collectRecords(group.list));
        }
        return records;
    }

    async _pollQueue() {
        const queued = this.queuedRecords;
        if (this.polling || !queued.length) {
            return;
        }
        this.polling = true;
        try {
            const rows = await this.orm.read(
                "business.status.check",
                queued.map((record) => record.resId),
                ["state"]
            );
            if (rows.some((row) => row.state !== "queued")) {
                await this.model.load();
            } else if (await this.orm.call("business.status.check", "process_queue", [])) {
                // The cron may be off, so this screen runs the queue itself.
                await this.model.load();
            }
        } catch {
            // A failed poll must never break the screen.
        } finally {
            this.polling = false;
        }
    }
}

registry.category("views").add("business_status_list", {
    ...listView,
    Controller: BusinessStatusListController,
});
