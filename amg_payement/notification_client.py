import logging
from amg_payement.notification_templates import PayementNotificationKeys,PayementNotificationTemplates
from policy_notification.notification_gateways.abstract_sms_gateway import NotificationGatewayAbs
from policy_notification.utils import get_notification_providers
from core.models import User
from core.models.user import UserRole, User, InteractiveUser, Role

logger = logging.getLogger(__name__)

class PayementNotificationClient:
    def __init__(self, provider):
        self.provider = provider
        self.templates = PayementNotificationTemplates()

    def get_context(self, insureeId,amount="",date="",purchaseref="",paymentref="",rejection_reason=""):
        context = {
            "InsureeUuid": insureeId,
            "Amount": amount,
            "Date": date,
            "PurchaseRef": purchaseref,
            "PaymentRef": paymentref,
            "RejectionReason": rejection_reason
            }
        return context

    def send_notification(self,insureeId,amount,date,purchaseref ,paymentref,rejection_reason,key,phone):
        template_attr = self.templates.template_for_key(key)
        if not template_attr:
            logger.error(f"Template {key} not found")
            return None

        context = self.get_context(insureeId,amount,date,purchaseref,paymentref,rejection_reason)
        if not phone or phone.strip() == "":
            logger.warning(f"No phone number")
            return None

        message = template_attr
        try:
            message = message % context
        except KeyError as e:
            logger.warning(f"Key {e} not found in template {key}. The message can't be formatted")

        return self.provider.send_notification(message, phone)


    
class PayementNotificationSender:
    @classmethod
    def send_payement_notifications(cls,insureeId,amount,date,purchaseref,paymentref,rejection_reason,key,phone): 
        print("mandeha le notif")
        providers = get_notification_providers()
        for provider in providers:
            client = PayementNotificationClient(provider=provider())
            client.send_notification(insureeId,amount,date,purchaseref,paymentref,rejection_reason,key,phone)