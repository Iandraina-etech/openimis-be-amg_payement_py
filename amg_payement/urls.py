from django.urls import path
from . import views

app_name = 'amg_payement'


urlpatterns = [
    path('amg-pay/payments/initier-paiement', views.initier_paiement, name='initier_paiement'),
    path('amg-pay/holo/acceptpaiement', views.redirect_accept, name='holo_accept_alias'),
    path('amg-pay/holo/declinepaiement', views.redirect_decline, name='holo_decline_alias'),
    path('amg-pay/holo/cancelpaiement', views.redirect_cancel, name='holo_cancel_alias'),
    path('amg-pay/holo/notificationpaiement', views.api_notify, name='api_holo_notify_alias'),
]