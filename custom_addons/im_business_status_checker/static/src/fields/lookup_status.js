import { Component } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

const STATUS = {
    active: { label: "Đang hoạt động", cls: "text-bg-success" },
    suspended: { label: "Tạm ngừng kinh doanh", cls: "text-bg-warning" },
    inactive: { label: "Ngừng hoạt động", cls: "text-bg-danger" },
    other: { label: "Khác", cls: "text-bg-info" },
    unknown: { label: "Chưa rõ", cls: "text-bg-secondary" },
};

// One column for both the lookup state and the business status.
export class LookupStatusField extends Component {
    static template = "im_business_status_checker.LookupStatusField";
    static props = { ...standardFieldProps };

    get info() {
        const data = this.props.record.data;
        if (data.state === "queued") {
            return { kind: "wait", label: "Đang tra cứu…" };
        }
        if (data.state === "error") {
            return { kind: "badge", label: "Lỗi tra cứu", cls: "text-bg-danger", note: data.note };
        }
        if (data.state === "not_found") {
            return { kind: "badge", label: "Không tìm thấy", cls: "text-bg-secondary", note: data.note };
        }
        const status = STATUS[data.status] || STATUS.unknown;
        return { kind: "badge", label: status.label, cls: status.cls };
    }
}

registry.category("fields").add("lookup_status", {
    component: LookupStatusField,
});
