import json
import logging
import requests
from datetime import date, datetime
# from django.conf import settings
from django.http import JsonResponse, HttpResponseForbidden, HttpResponseBadRequest
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from .models import Payment
from .utils import verify_signature, is_ip_whitelisted
from policy.models import Policy
from django.contrib.contenttypes.models import ContentType
from insuree.models import Insuree
from invoice.models import Invoice
from policy.values import policy_values
from .notification_client import PayementNotificationSender, PayementNotificationKeys
from datetime import datetime, timezone
from contribution.models import Premium
logger = logging.getLogger(__name__)


from core.models import ModuleConfiguration
from django.apps import apps
from .apps import DEFAULT_CONFIG, MODULE_NAME

cfg = ModuleConfiguration.get_or_default(MODULE_NAME,DEFAULT_CONFIG)

HOLO_BASE_URL = cfg["HOLO_BASE_URL"]
HOLO_MERCHANT_ID = cfg["HOLO_MERCHANT_ID"]
HOLO_CURRENCY = cfg["HOLO_CURRENCY"]
HOLO_ONLINE_ENDPOINT = cfg["HOLO_ONLINE_ENDPOINT"]
HOLO_FORCE_MANUAL = cfg["HOLO_FORCE_MANUAL"]
NOTIFY_URL = cfg["NOTIFY_URL"]
ACCEPT_URL = cfg["ACCEPT_URL"]
DECLINE_URL = cfg["DECLINE_URL"]
CANCEL_URL = cfg["CANCEL_URL"]


@require_http_methods(["GET"])
def initier_paiement(request):
    openimis_ref=""
    amount=0    
    policy_uuid = request.GET.get("policyUuid")
    if not policy_uuid or policy_uuid=="":
        ctx = {
            "erreur": "Référence de police invalide invalide",
        }
        return render(request, "payments/error.html", ctx)
    policy = Policy.objects.filter(uuid=policy_uuid, validity_to__isnull=True).first()
    if not policy:
        ctx = {
            "erreur": "Police d'assurance a activer non trouvee",
        }
        return render(request, "payments/error.html", ctx)
    else:
        family = policy.family
        head_insuree = family.head_insuree
        openimis_ref=head_insuree.chf_id
        invoice=None
        if head_insuree:
            insuree_content_type = ContentType.objects.get_for_model(Insuree)
            invoice_filter = {
                'subject_type': insuree_content_type,
                'subject_id': str(head_insuree.id), 
                'is_deleted': False
            }
            invoice = Invoice.objects.filter(**invoice_filter).first()
        if invoice:
            amount=invoice.amount_total
        else:
            amount=policy_values(policy, policy.family, policy,None)[0].value

    if not openimis_ref or openimis_ref=="":
        ctx = {
                    "erreur": "Pas d'assure chef de famille trouve ",
                }
        return render(request, "payments/error.html", ctx) 

    if not amount or  amount==0:
        ctx = {
                    "erreur": "Erreur lors du chargement du montant payer ou le regime d'assurances est de type AMS et ne necessite pas de payement",
                }
        return render(request, "payments/error.html", ctx)
            
    purchaseref = f"AMG-{openimis_ref}-{int(datetime.utcnow().timestamp())}"

    description = f"Cotisation AMG pour {openimis_ref} montant {amount} "

    
    payment = Payment.objects.create(
        purchaseref=purchaseref,
        openimis_ref=openimis_ref,
        policy_uuid=policy_uuid,
        amount=amount,
        description=description,
        currency=HOLO_CURRENCY,
        merchantid=HOLO_MERCHANT_ID,
        status="initiating",
    )

    session_error = ""
    try:
        holo_url = f"{HOLO_BASE_URL}{HOLO_ONLINE_ENDPOINT}?merchantid={HOLO_MERCHANT_ID}"
        resp = requests.get(holo_url, timeout=10)
        resp.raise_for_status()
        session_raw = resp.text.strip()
        # Réponse attendue: 'OK<SESSIONID>' ou 'OK <SESSIONID>' ; erreurs: 'NOK:...'
        if session_raw.upper().startswith('OK'):
            sessionid = session_raw[3:].strip()
            payment.sessionid = sessionid
            payment.status = "session_created"
            payment.save()
        else:
            logger.warning(f"HOLO session NOK: {session_raw}")
            session_error = session_raw
            sessionid = ""
    except Exception as e:
        logger.warning(f"Erreur session HOLO: {e}")
        session_error = str(e)
        sessionid = "" 


    form_ctx = {
        "action_url": f"{HOLO_BASE_URL}{HOLO_ONLINE_ENDPOINT}",
        "sessionid": sessionid,
        "merchantid": HOLO_MERCHANT_ID,
        "amount": amount,
        "currency": HOLO_CURRENCY,
        "purchaseref": purchaseref,
        "openimisRef": openimis_ref,
        "description": description,
        "acceptUrl": ACCEPT_URL,
        "declineUrl": DECLINE_URL,
        "cancelUrl": CANCEL_URL,
        "auto_submit": (not HOLO_FORCE_MANUAL) and bool(sessionid),
        "session_error": session_error,
    }

    return render(request, "payments/holo_auto_submit.html", form_ctx)


def redirect_accept(request):
    return render(request, "payments/redirect_accept.html", {})


def redirect_decline(request):
    return render(request, "payments/redirect_decline.html", {})


def redirect_cancel(request):
    return render(request, "payments/redirect_cancel.html", {})


@csrf_exempt
@require_http_methods(["GET"])
def api_notify(request):

    logger.warning(f"REMOTE_ADDR: {request.META.get('REMOTE_ADDR')}")
    logger.warning(f"HTTP_X_REAL_IP: {request.META.get('HTTP_X_REAL_IP')}")
    logger.warning(f"HTTP_X_FORWARDED_FOR: {request.META.get('HTTP_X_FORWARDED_FOR')}")
    remote_addr = (
        request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip() or 
        (request.META.get('HTTP_X_REAL_IP') or '').strip() or 
        request.META.get('REMOTE_ADDR', '')
    )
    if remote_addr and not is_ip_whitelisted(remote_addr):
        logger.warning(f"Notify IP non autorisée: {remote_addr}")
        return HttpResponseForbidden("IP non autorisée")

    payload = request.GET

    purchaseref = payload.get("purchaseref")
    amount_str = payload.get("amount")   # string attendue
    currency = payload.get("currency")
    status = payload.get("status")
    clientid = payload.get("clientid","")
    cname = payload.get("cname","")
    mobile = payload.get("mobile","")
    if mobile and len(mobile)>3 and mobile.startswith("269"):
        mobile = mobile[3:]
    paymentref = payload.get("paymentref","") 
    payid = payload.get("payid","")
    ts = payload.get("timestamp","")
    ipaddr = payload.get("ipaddr","")
    error = payload.get("error","")
    reason = payload.get("reason","")

    if status == "NOK":
        logger.warning(f"Payment not approved, status: {status}, error: {error}, reason: {reason}")
        payement=Payment.objects.filter(purchaseref=purchaseref).first()
        if not payement:
            logger.warning(f"Référence d'achat inconnue {purchaseref}")
            return HttpResponseForbidden("Référence d'achat inconnue")
        payement.status="error"
        payement.status_return=status
        payement.error=error
        payement.reason=reason
        payement.clientid=clientid
        payement.cname=cname
        payement.mobile=mobile
        payement.paymentref=paymentref
        payement.payid=payid
        payement.timestamp=timestamp
        payement.ipaddr=ipaddr
        payement.save()
        if mobile:
            if payement.error and "CANCEL" in payement.error.upper():
                logger.warning("Paiement annulé par l'utilisateur")
                PayementNotificationSender.send_payement_notifications(
                    insureeId=payement.openimis_ref,
                    amount=amount,
                    date=timestamp,
                    purchaseref=purchaseref,
                    paymentref=paymentref,
                    rejection_reason=f"",
                    key=PayementNotificationKeys.ON_CANCEL,
                    phone=mobile
                )
            else :
                logger.warning("Paiement rejeté")
                PayementNotificationSender.send_payement_notifications(
                    insureeId=payement.openimis_ref,
                    amount=amount,
                    date=timestamp,
                    purchaseref=purchaseref,
                    paymentref=paymentref,
                    rejection_reason=f"Erreur : {payement.error} , raison du rejet :{payement.reason}",
                    key=PayementNotificationKeys.ON_REJECTED,
                    phone=mobile
                )

    if amount_str is None:
        logger.warning("Missing amount parameter in notify")
        return HttpResponseBadRequest("Missing amount parameter")

    try:
        amount=float(amount_str)
        amount = int(amount)
    except ValueError:
        logger.warning("amount must be an integer")
        return HttpResponseBadRequest("amount must be an integer")
    try:
        ts_int = int(ts)
        timestamp = datetime.fromtimestamp(ts_int, tz=timezone.utc)
    except (TypeError, ValueError):
        logger.warning("Invalid timestamp format, using current time")
        timestamp = datetime.now(timezone.utc)

    try:
        if status=="OK":
            payement=Payment.objects.filter(purchaseref=purchaseref).first()
            if not payement:
                logger.warning(f"Référence d'achat inconnue {purchaseref}")
                return HttpResponseForbidden("Référence d'achat inconnue")        
            if not mobile or mobile=="":
                insuree=Insuree.objects.filter(chf_id=payement.openimis_ref,validity_to__isnull=True).first()
                if insuree and insuree.phone and insuree.phone!="":
                    mobile=insuree.phone
                if not mobile or mobile=="":
                    # logger.exception("mobile does not exist")
                    logger.warning("Phone does not existe")
                    return HttpResponseBadRequest(f"Phone does not existe")
                    
            payement.clientid=clientid
            payement.cname=cname
            payement.mobile=mobile
            payement.paymentref=paymentref
            payement.payid=payid
            payement.timestamp=timestamp
            payement.ipaddr=ipaddr
            payement.status_return=status
            if int(amount)!=int(payement.amount):
                payement.status_return="NOK"
                payement.status="error"
                payement.reason=f"Montant du paiement incorrect {amount} verse, {payement.amount} attendu "
                payement.save()
                logger.warning("Montant du paiement incorrect ver1")
                if mobile:
                    PayementNotificationSender.send_payement_notifications(
                        insureeId=payement.openimis_ref,
                        amount=amount,
                        date=timestamp,
                        purchaseref=purchaseref,
                        paymentref=paymentref,
                        rejection_reason=f"Montant du paiement incorrect {amount} verse, {payement.amount} attendu ",
                        key=PayementNotificationKeys.WRONG_AMOUNT,
                        phone=mobile
                    )
                return HttpResponseForbidden("Montant du paiement incorrect")
            payement.save()
            policy = Policy.objects.filter(uuid=payement.policy_uuid, validity_to__isnull=True).first()
            if policy:
                family = policy.family
                head_insuree = family.head_insuree
                invoice=None
                if head_insuree:
                    insuree_content_type = ContentType.objects.get_for_model(Insuree)
                    invoice_filter = {
                        'subject_type': insuree_content_type,
                        'subject_id': str(head_insuree.id), 
                        'is_deleted': False
                    }
                    invoice = Invoice.objects.filter(**invoice_filter).first()
                if invoice:
                    if int(invoice.amount_total) <= int(payement.amount):
                        policy.status=Policy.STATUS_ACTIVE
                        policy.save()
                        payement.status="paid"
                        payement.save()
                        premium=Premium()
                        premium.policy=policy
                        premium.amount=payement.amount
                        premium.receipt=purchaseref
                        premium.pay_date = date.today()
                        premium.pay_type="M"
                        premium.audit_user_id=2
                        premium.save()
                        logger.warning("Paiement approuve et police activee")
                        PayementNotificationSender.send_payement_notifications(
                            insureeId=payement.openimis_ref,
                            amount=amount,
                            date=timestamp,
                            purchaseref=purchaseref,
                            paymentref=paymentref,
                            rejection_reason="",
                            key=PayementNotificationKeys.ON_APPROVED,
                            phone=mobile
                        )
                    else:
                        # status="NOK"
                        payement.status_return="NOK"
                        payement.status="error"
                        payement.reason="Montant du paiement incorrect"
                        payement.save()
                        logger.warning("Montant du paiement incorrect par rapport a la facture")
                        logger.warning(f"invoice amount total: {invoice.amount_total}, payment amount: {payement.amount}")
                        if mobile:
                            PayementNotificationSender.send_payement_notifications(
                                insureeId=payement.openimis_ref,
                                amount=amount,
                                date=timestamp,
                                purchaseref=purchaseref,
                                paymentref=paymentref,
                                rejection_reason=f"Montant du paiement incorrect {payement.amount} verse, {invoice.amount_total} attendu ",
                                key=PayementNotificationKeys.WRONG_AMOUNT,
                                phone=mobile
                            )
                else:
                    if int(payement.amount)>=int(policy_values(policy, policy.family, policy,None)[0].value):
                        policy.status=Policy.STATUS_ACTIVE
                        policy.save()
                        payement.status="paid"
                        payement.save()
                        premium=Premium()
                        premium.policy=policy
                        premium.amount=payement.amount
                        premium.receipt=purchaseref
                        premium.pay_date = date.today()
                        premium.pay_type="M"
                        premium.audit_user_id=2
                        premium.save()
                        logger.warning("Paiement approuve et police activee")
                        PayementNotificationSender.send_payement_notifications(
                            insureeId=payement.openimis_ref,
                            amount=amount,
                            date=timestamp,
                            purchaseref=purchaseref,
                            paymentref=paymentref,
                            rejection_reason="",
                            key=PayementNotificationKeys.ON_APPROVED,
                            phone=mobile
                        )
                    else:
                        # status="NOK"
                        payement.status_return="NOK"
                        payement.status="error"
                        payement.reason="Montant du paiement incorrect"
                        payement.save()
                        logger.warning("Montant du paiement incorrect par rapport a la prime")
                        logger.warning(f"policy premium amount: {policy_values(policy, policy.family, policy,None)[0].value}, payment amount: {payement.amount}")
                        if mobile:
                            PayementNotificationSender.send_payement_notifications(
                                insureeId=payement.openimis_ref,
                                amount=amount,
                                date=timestamp,
                                purchaseref=purchaseref,
                                paymentref=paymentref,
                                rejection_reason=f"Montant du paiement incorrect {payement.amount} verse, {policy_values(policy, policy.family, policy,None)[0].value} attendu ",
                                key=PayementNotificationKeys.WRONG_AMOUNT,
                                phone=mobile
                            )
            else:
                payement.status_return="NOK"
                payement.status="error"
                payement.reason="Aucune police d'assurance correspondante trouvee"
                logger.warning("Aucune police d'assurance correspondante trouvee")
                payement.save()
                logger.warning("Aucune police d'assurance correspondante trouvee"+payement.policy_uuid)
                if mobile:
                    PayementNotificationSender.send_payement_notifications(
                        insureeId=payement.openimis_ref,
                        amount=amount,
                        date=timestamp,
                        purchaseref=purchaseref,
                        paymentref=paymentref,
                        rejection_reason=f"Aucune police d'assurance correspondante trouvee ",
                        key=PayementNotificationKeys.WRONG_AMOUNT,
                        phone=mobile
                    )
                return HttpResponseForbidden("pas de police d'assurance correspondante trouvee")
        else:
            logger.warning(f"Payment not approved, status: {status}, error: {error}, reason: {reason}")
            payement=Payment.objects.filter(purchaseref=purchaseref).first()
            if not payement:
                logger.warning("Référence d'achat inconnue")
                return HttpResponseForbidden("Référence d'achat inconnue")
            payement.status="error"
            payement.status_return=status
            payement.error=error
            payement.reason=reason
            payement.clientid=clientid
            payement.cname=cname
            payement.mobile=mobile
            payement.paymentref=paymentref
            payement.payid=payid
            payement.timestamp=timestamp
            payement.ipaddr=ipaddr
            payement.save()
            if mobile:
                if payement.error and "CANCEL" in payement.error.upper():
                    logger.warning("Paiement annulé par l'utilisateur")
                    PayementNotificationSender.send_payement_notifications(
                        insureeId=payement.openimis_ref,
                        amount=amount,
                        date=timestamp,
                        purchaseref=purchaseref,
                        paymentref=paymentref,
                        rejection_reason=f"",
                        key=PayementNotificationKeys.ON_CANCEL,
                        phone=mobile
                    )
                else :
                    logger.warning("Paiement rejeté")
                    PayementNotificationSender.send_payement_notifications(
                        insureeId=payement.openimis_ref,
                        amount=amount,
                        date=timestamp,
                        purchaseref=purchaseref,
                        paymentref=paymentref,
                        rejection_reason=f"Erreur : {payement.error} , raison du rejet :{payement.reason}",
                        key=PayementNotificationKeys.ON_REJECTED,
                        phone=mobile
                    )
    except Exception as e:
        logger.warning(f"Erreur api_notify: {e}")
        logger.exception("Erreur api_notify")
        return HttpResponseBadRequest(f"Erreur serveur")
    return JsonResponse({"status": "OK"})