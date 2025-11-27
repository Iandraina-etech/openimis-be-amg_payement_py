from enum import Enum
from django.utils.translation import gettext as _

class PayementNotificationKeys(str, Enum):
    ON_APPROVED = "payement.sms_on_approved"
    ON_REJECTED = "payement.sms_on_rejected"
    ON_CANCEL = "payement.sms_on_cancel"
    WRONG_AMOUNT = "payement.wrong_amount"

class PayementNotificationTemplates:
    def template_for_key(self, key: PayementNotificationKeys):
        return _(key.value)
