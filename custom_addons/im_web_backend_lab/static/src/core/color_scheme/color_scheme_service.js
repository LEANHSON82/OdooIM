/** @odoo-module **/

import { registry } from "@web/core/registry";
import { browser } from "@web/core/browser/browser";
import { cookie } from "@web/core/browser/cookie";
import { session } from "@web/session";
import { user } from "@web/core/user";

const colorSchemeService = {
    start(env) {
        let currentScheme = _getEffectiveScheme();
        _applyScheme(currentScheme);

        function _getEffectiveScheme() {
            // Priority: cookie > session > system
            const cookieScheme = cookie.get("color_scheme");
            if (cookieScheme === "light" || cookieScheme === "dark") {
                return cookieScheme;
            }

            const sessionScheme = session.color_scheme;
            if (sessionScheme === "light" || sessionScheme === "dark") {
                return sessionScheme;
            }

            if (browser.matchMedia) {
                const prefersDark = browser.matchMedia("(prefers-color-scheme: dark)");
                if (prefersDark.matches) {
                    return "dark";
                }
            }
            return "light";
        }

        function _applyScheme(scheme) {
            document.documentElement.setAttribute("data-color-scheme", scheme);
            currentScheme = scheme;
        }

        async function switchScheme(preference) {
            let scheme;
            if (preference === "system") {
                const prefersDark =
                    browser.matchMedia &&
                    browser.matchMedia("(prefers-color-scheme: dark)").matches;
                scheme = prefersDark ? "dark" : "light";
                cookie.delete("color_scheme");
            } else {
                scheme = preference;
                cookie.set("color_scheme", scheme, 365 * 24 * 3600);
            }

            try {
                await user.setUserSettings("x_color_scheme", preference);
            } catch (e) {
                console.warn("Failed to save color scheme preference:", e);
            }

            if (scheme !== currentScheme) {
                _applyScheme(scheme);
                browser.location.reload();
            }
        }

        // Listen for OS preference changes
        if (browser.matchMedia) {
            const mql = browser.matchMedia("(prefers-color-scheme: dark)");
            mql.addEventListener("change", (ev) => {
                const cookieScheme = cookie.get("color_scheme");
                if (!cookieScheme) {
                    const scheme = ev.matches ? "dark" : "light";
                    if (scheme !== currentScheme) {
                        _applyScheme(scheme);
                        browser.location.reload();
                    }
                }
            });
        }

        return {
            get current() {
                return currentScheme;
            },
            switchScheme,
        };
    },
};

registry.category("services").add("color_scheme", colorSchemeService);