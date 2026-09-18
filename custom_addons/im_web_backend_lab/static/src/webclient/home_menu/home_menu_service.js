/** @odoo-module **/

import { registry } from "@web/core/registry";
import { reactive } from "@odoo/owl";

const homeMenuService = {
    dependencies: ["menu", "action"],
    start(env, { menu, action }) {
        const state = reactive({
            isOpen: false,
            hasHomeMenu: true,
        });

        function toggle() {
            state.isOpen = !state.isOpen;
            env.bus.trigger("HOME-MENU:TOGGLED");
        }

        function open() {
            if (!state.isOpen) {
                state.isOpen = true;
                env.bus.trigger("HOME-MENU:TOGGLED");
            }
        }

        function close() {
            if (state.isOpen) {
                state.isOpen = false;
                env.bus.trigger("HOME-MENU:TOGGLED");
            }
        }

        // Close the grid as soon as an action renders behind it.
        env.bus.addEventListener("ACTION_MANAGER:UPDATE", ({ detail }) => {
            if (detail && detail.Component && state.isOpen) {
                state.isOpen = false;
                env.bus.trigger("HOME-MENU:TOGGLED");
            }
        });

        return {
            get isOpen() {
                return state.isOpen;
            },
            get hasHomeMenu() {
                return state.hasHomeMenu;
            },
            toggle,
            open,
            close,
        };
    },
};

registry.category("services").add("home_menu", homeMenuService);