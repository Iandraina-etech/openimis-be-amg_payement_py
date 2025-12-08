from django.apps import AppConfig

MODULE_NAME = "amg_payement"

DEFAULT_CONFIG = {
    "HOLO_BASE_URL": "https://26900.tagpay.fr",
    "HOLO_ONLINE_ENDPOINT": "/online/online.php",
    "HOLO_MERCHANT_ID": "2449462108576891",
    "HOLO_CURRENCY": 174,
    "HOLO_FORCE_MANUAL": False,
    "CALLBACK_DOMAIN": "https://dev.amg.km",
    "NOTIFY_URL": "https://dev.amg.km/amg-pay/holo/notificationpaiement",
    "ACCEPT_URL": "https://dev.amg.km/amg-pay/holo/acceptpaiement",
    "DECLINE_URL": "https://dev.amg.km/amg-pay/holo/declinepaiement",
    "CANCEL_URL": "https://dev.amg.km/amg-pay/holo/cancelpaiement",
    "IP_WHITELIST": ["3.6.76.175","54.38.250.251","5.135.34.227","176.31.43.71","135.125.248.117"],
    "SIGNING_SECRET": "change-me",
}

class AmgPayementConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = MODULE_NAME
    verbose_name = "AMG Payement"
    
    def ready(self):
        from core.models import ModuleConfiguration
        cfg = ModuleConfiguration.get_or_default(MODULE_NAME, DEFAULT_CONFIG)
        
        # Importer les signaux si vous en avez
        # from . import signals