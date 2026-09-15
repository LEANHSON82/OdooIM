/** @odoo-module **/

import { Component, useState, useRef, onMounted, onWillUnmount } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { user } from "@web/core/user";

export class HomeMenu extends Component {
    static template = "im_web_backend_lab.HomeMenu";
    static props = {};

    setup() {
        this.menuService = useService("menu");
        this.actionService = useService("action");
        this.homeMenuService = useService("home_menu");
        this.user = user;

        this.state = useState({
            query: "",
            focusedIndex: -1,
        });

        this.searchRef = useRef("search");

        this._onKeydown = this._onKeydown.bind(this);

        onMounted(() => {
            this._focusSearch();
            document.addEventListener("keydown", this._onKeydown);
        });

        onWillUnmount(() => {
            document.removeEventListener("keydown", this._onKeydown);
        });
    }

    get apps() {
        const menus = this.menuService.getApps();
        const processed = menus.map((app) => {
            const item = { ...app };
            if (!item.webIconData && item.webIcon && typeof item.webIcon === "string") {
                const parts = item.webIcon.split(",");
                if (parts.length >= 3) {
                    item.webIconObj = {
                        iconClass: parts[0],
                        color: parts[1],
                        backgroundColor: parts[2],
                    };
                } else {
                    item.webIconData = "/web/static/img/default_icon_app.png";
                }
            } else if (!item.webIconData) {
                item.webIconData = "/web/static/img/default_icon_app.png";
            }
            return item;
        });
        if (!this.state.query) {
            return processed;
        }
        const query = this.state.query.toLowerCase().trim();
        return processed.filter((app) => {
            const name = (app.name || "").toLowerCase();
            return name.includes(query);
        });
    }

    _focusSearch() {
        if (this.searchRef.el) {
            this.searchRef.el.focus();
        }
    }

    _onSearchInput(ev) {
        this.state.query = ev.target.value;
        this.state.focusedIndex = -1;
    }

    _onSearchClear() {
        this.state.query = "";
        this.state.focusedIndex = -1;
        this._focusSearch();
    }

    _onAppClick(app) {
        this.menuService.selectMenu(app);
    }

    _onKeydown(ev) {
        if (!this.homeMenuService.isOpen) {
            return;
        }
        const apps = this.apps;
        const len = apps.length;

        switch (ev.key) {
            case "ArrowDown": {
                ev.preventDefault();
                const cols = this._getColCount();
                if (this.state.focusedIndex < 0) {
                    this.state.focusedIndex = 0;
                } else {
                    this.state.focusedIndex = Math.min(
                        this.state.focusedIndex + cols,
                        len - 1
                    );
                }
                break;
            }
            case "ArrowUp": {
                ev.preventDefault();
                const cols = this._getColCount();
                if (this.state.focusedIndex >= cols) {
                    this.state.focusedIndex -= cols;
                } else {
                    this.state.focusedIndex = -1;
                    this._focusSearch();
                }
                break;
            }
            case "ArrowRight":
                ev.preventDefault();
                if (this.state.focusedIndex < len - 1) {
                    this.state.focusedIndex++;
                }
                break;
            case "ArrowLeft":
                ev.preventDefault();
                if (this.state.focusedIndex > 0) {
                    this.state.focusedIndex--;
                }
                break;
            case "Enter":
                if (this.state.focusedIndex >= 0 && this.state.focusedIndex < len) {
                    ev.preventDefault();
                    this._onAppClick(apps[this.state.focusedIndex]);
                }
                break;
            case "Escape":
                ev.preventDefault();
                if (this.state.query) {
                    this._onSearchClear();
                } else {
                    this.homeMenuService.close();
                }
                break;
            case "Tab":
                ev.preventDefault();
                if (ev.shiftKey) {
                    this.state.focusedIndex = Math.max(this.state.focusedIndex - 1, 0);
                } else {
                    this.state.focusedIndex = Math.min(
                        this.state.focusedIndex + 1,
                        len - 1
                    );
                }
                break;
        }
    }

    _getColCount() {
        const width = window.innerWidth;
        if (width < 576) return 3;
        if (width < 768) return 4;
        return 6;
    }
}