/** @odoo-module **/

import { WebClient } from "@web/webclient/webclient";
import { ImNavBar } from "./navbar/navbar";
import { HomeMenu } from "./home_menu/home_menu";
import { useService, useBus } from "@web/core/utils/hooks";
import { useState } from "@odoo/owl";

export class ImWebClient extends WebClient {
    static template = "im_web_backend_lab.ImWebClient";
    static components = {
        ...WebClient.components,
        NavBar: ImNavBar,
        HomeMenu,
    };

    setup() {
        super.setup();
        this.homeMenuService = useService("home_menu");
        this.imState = useState({
            isHomeMenuOpen: false,
        });

        useBus(this.env.bus, "HOME-MENU:TOGGLED", () => {
            this._updateHomeMenuState(this.homeMenuService.isOpen);
        });

        useBus(this.env.bus, "ACTION_MANAGER:UPDATE", ({ detail }) => {
            if (detail && detail.Component) {
                this._updateHomeMenuState(false);
            }
        });
    }

    _updateHomeMenuState(isOpen) {
        this.imState.isHomeMenuOpen = isOpen;
        document.body.classList.toggle("o_home_menu_background", isOpen);
    }

    _loadDefaultApp() {
        this.homeMenuService.open();
        this._updateHomeMenuState(true);
    }
}