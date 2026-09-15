/** @odoo-module */

/**
 * InMotion Entry Point — replaces CE main.js
 * Loads ImWebClient instead of WebClient.
 */

import { startWebClient } from "@web/start";
import { ImWebClient } from "./webclient/im_webclient";

startWebClient(ImWebClient);