/** @odoo-module **/

import { NavBar } from "@web/webclient/navbar/navbar";
import { useService } from "@web/core/utils/hooks";

export class ImNavBar extends NavBar {
    static template = "im_web_backend_lab.ImNavBar";

    setup() {
        super.setup();
        this.homeMenuService = useService("home_menu");
    }

    get isHomeMenuOpen() {
        return this.homeMenuService.isOpen;
    }

    _onHomeMenuToggle() {
        if (this.homeMenuService.isOpen && !this.menuService.getCurrentApp()) {
            return;
        }
        this.homeMenuService.toggle();
        if (this.homeMenuService.isOpen) {
            window.history.pushState({}, "", "/odoo");
        }
    }
}