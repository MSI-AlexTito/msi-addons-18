/** @odoo-module **/
import { patch } from "@web/core/utils/patch";
import { SubscriptionManager } from "@web_enterprise/webclient/home_menu/enterprise_subscription_service";
import { enterpriseSubscriptionService } from "@web_enterprise/webclient/home_menu/enterprise_subscription_service";
import { ExpirationPanel } from "@web_enterprise/webclient/home_menu/expiration_panel";

const { DateTime } = luxon;

patch(SubscriptionManager.prototype, {
    
    get daysLeft() {
        return 999;
    },
    
    get unregistered() {
        return false;
    },
    
    get formattedExpirationDate() {
        return "Development Mode";
    },
    
    hideWarning() {
        this.isWarningHidden = true;
        return;
    }
});

patch(enterpriseSubscriptionService, {
    start(env, { orm, notification }) {
        const manager = super.start(env, { orm, notification });
        
        // Modificar el manager después de su creación
		manager.expirationDate = DateTime.utc().plus({ days: 999 });
		manager.expirationReason = "development";
		manager.warningType = null;
		manager.lastRequestStatus = "success";
		manager.isWarningHidden = true;
        
        return manager;
    }
});

// Patch del ExpirationPanel
patch(ExpirationPanel.prototype, {
    
    get alertType() {
        return "success"; // Siempre verde en desarrollo
    },
    
    get expirationMessage() {
        return "Development Mode - License checks bypassed for local development";
    },
    
    get buttonText() {
        return "Development Mode";
    }
});

    