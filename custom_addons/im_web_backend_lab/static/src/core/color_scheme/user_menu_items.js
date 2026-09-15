/** @odoo-module **/

import { registry } from "@web/core/registry";
import { _t } from "@web/core/l10n/translation";

function colorSchemeMenuItem(env) {
    const colorScheme = env.services.color_scheme;
    const isDark = colorScheme && colorScheme.current === "dark";

    return {
        type: "item",
        id: "color_scheme",
        description: isDark ? _t("Light Mode") : _t("Dark Mode"),
        callback: () => {
            const newScheme = isDark ? "light" : "dark";
            colorScheme.switchScheme(newScheme);
        },
        sequence: 35,
    };
}

registry.category("user_menuitems").add("color_scheme", colorSchemeMenuItem);