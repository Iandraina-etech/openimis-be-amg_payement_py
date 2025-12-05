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


@require_http_methods(["GET", "POST"])
def initier_paiement(request):
    if request.method == "GET":
        amount = request.GET.get("amount")
        try :
            amount=float(amount)
            amount=int(amount)
        except :
            ctx = {
                "erreur": "montant invalide",
            }
            return render(request, "payments/error.html", ctx)       
        openimis_ref = request.GET.get("openimisRef")
        policy_uuid = request.GET.get("policyUuid")
        lock_raw = (request.GET.get("lock") or "").lower()
        lock = lock_raw in ("1", "true", "oui", "yes")
        prefill_present = any([amount, openimis_ref])
        if (amount == "" or int(amount) <= 0) or (openimis_ref == "" or not openimis_ref) or (policy_uuid == "" or not policy_uuid):
            ctx = {
                "erreur": "Paramètres invalides pour initier le paiement. Veuillez réessayer avec le bon lien.",
            }
            return render(request, "payments/error.html", ctx)
        insuree=Insuree.objects.filter(chf_id=openimis_ref,validity_to__isnull=True).first()
        if not insuree :
            ctx = {
                "erreur": "Assure a activer non trouvee",
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
                if int(invoice.amount_total) != int(amount):
                    ctx = {
                        "erreur": "Le montant fourni ne correspond pas au montant de la facture.",
                    }
                    return render(request, "payments/error.html", ctx)
            else:
                if int(amount)!=int(policy_values(policy, policy.family, policy,None)[0].value):
                    ctx = {
                        "erreur": "Le montant fourni ne correspond pas au montant de la prime.",
                    }
                    return render(request, "payments/error.html", ctx)
        ctx = {
            "amount_prefill": amount,
            "openimis_ref_prefill": openimis_ref,
            "policy_uuid_prefill": policy_uuid,
            "locked": lock or prefill_present,
        }
        return render(request, "payments/initier_paiement.html", ctx)

    # POST: trigger initiation and render auto-submit form to HOLO
    amount = int(request.POST.get("amount", "0"))
    openimis_ref = request.POST.get("openimis_ref", "")
    description = f"Cotisation AMG pour {openimis_ref} montant {amount} "
    policy_uuid = request.POST.get("policy_uuid", "")

    if (amount == "" or int(amount) <= 0) or (openimis_ref == "" or not openimis_ref) or (policy_uuid == "" or not policy_uuid):
            ctx = {
                "erreur": "Paramètres invalides pour initier le paiement. Veuillez réessayer avec le bon lien.",
            }
            return render(request, "payments/error.html", ctx)
    policy = Policy.objects.filter(uuid=policy_uuid, validity_to__isnull=True).first()
    insuree=Insuree.objects.filter(chf_id=openimis_ref,validity_to__isnull=True).first()
    if not insuree :
        ctx = {
            "erreur": "Assure a activer non trouvee",
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
            if int(invoice.amount_total) != int(amount):
                ctx = {
                    "erreur": "Le montant fourni ne correspond pas au montant de la facture.",
                }
                return render(request, "payments/error.html", ctx)
        else:
            if int(amount)!=int(policy_values(policy, policy.family, policy,None)[0].value):
                ctx = {
                    "erreur": "Le montant fourni ne correspond pas au montant de la prime.",
                }
                return render(request, "payments/error.html", ctx)      
    
    purchaseref = f"AMG//--//{openimis_ref}//--//{int(datetime.utcnow().timestamp())}"

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
        else:
            logger.error(f"HOLO session NOK: {session_raw}")
            session_error = session_raw
            sessionid = ""
    except Exception as e:
        logger.error(f"Erreur session HOLO: {e}")
        session_error = str(e)
        sessionid = ""

    payment.sessionid = sessionid
    payment.status = "session_created"
    payment.save()

    form_ctx = {
        "action_url": f"{HOLO_BASE_URL}{HOLO_ONLINE_ENDPOINT}",
        "sessionid": sessionid,
        "merchantid": HOLO_MERCHANT_ID,
        "amount": amount,
        "currency": HOLO_CURRENCY,
        "purchaseref": purchaseref,
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

    # IP whitelist check
    remote_addr = request.META.get('REMOTE_ADDR') or request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip()
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
    paymentref = payload.get("paymentref","") 
    payid = payload.get("payid","")
    ts = payload.get("timestamp","")
    ipaddr = payload.get("ipaddr","")
    error = payload.get("error","")
    reason = payload.get("reason","")

    if amount_str is None:
        return HttpResponseBadRequest("Missing amount parameter")

    try:
        amount=float(amount_str)
        amount = int(amount)
    except ValueError:
        return HttpResponseBadRequest("amount must be an integer")
    try:
        ts_int = int(ts)
        timestamp = datetime.fromtimestamp(ts_int, tz=timezone.utc)
    except (TypeError, ValueError):
        timestamp = datetime.now(timezone.utc)

    try:
        if status=="OK":
            payement=Payment.objects.filter(purchaseref=purchaseref).first()
            if not payement:
                return HttpResponseForbidden("Référence d'achat inconnue")        
            if not mobile or mobile=="":
                insuree=Insuree.objects.filter(chf_id=payement.openimis_ref,validity_to__isnull=True).first()
                if insuree and insuree.phone and insuree.phone!="":
                    mobile=insuree.phone
                if not mobile or mobile=="":
                    logger.exception("mobile does not exist")
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
                payement.reason="Montant du paiement incorrect"
                payement.save()
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
                payement.status="error"
                payement.reason="Aucune police d'assurance correspondante trouvee"
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
            payement=Payment.objects.filter(purchaseref=purchaseref).first()
            if not payement:
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
        logger.exception("Erreur api_notify")
        return HttpResponseBadRequest(f"Erreur serveur")
    return JsonResponse({"status": "OK"})