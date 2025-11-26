import json
import logging
import requests
from datetime import datetime
# from django.conf import settings
from django.http import JsonResponse, HttpResponseForbidden, HttpResponseBadRequest
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from .models import Payment
from .utils import verify_signature, is_ip_whitelisted

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
        openimis_ref = request.GET.get("openimis_ref")
        # beneficiary_id = request.GET.get("beneficiary_id")
        # description = request.GET.get("description") or "Cotisation AMG"
        lock_raw = (request.GET.get("lock") or "").lower()
        lock = lock_raw in ("1", "true", "oui", "yes")
        # prefill_present = any([amount, openimis_ref, beneficiary_id])
        prefill_present = any([amount, openimis_ref])
        ctx = {
            "amount_prefill": amount,
            "openimis_ref_prefill": openimis_ref,
            # "beneficiary_id_prefill": beneficiary_id,
            # "description_prefill": description,
            "locked": lock or prefill_present,
        }
        return render(request, "payments/initier_paiement.html", ctx)

    # POST: trigger initiation and render auto-submit form to HOLO
    amount = int(request.POST.get("amount", "0"))
    openimis_ref = request.POST.get("openimis_ref", "")
    description = f"Cotisation AMG pour {openimis_ref} montant {amount} "
    # beneficiary_id = request.POST.get("beneficiary_id", "")

    if amount <= 0 or not openimis_ref:
    # if amount <= 0 or not openimis_ref or not beneficiary_id:
        return HttpResponseBadRequest("Paramètres invalides")

    purchaseref = f"AMG-{openimis_ref}-{int(datetime.utcnow().timestamp())}"

    payment = Payment.objects.create(
        purchaseref=purchaseref,
        openimis_ref=openimis_ref,
        # beneficiary_id=beneficiary_id,
        amount=amount,
        description=description,
        currency=HOLO_CURRENCY,
        merchantid=HOLO_MERCHANT_ID,
        status="initiating",
    )

    # Call HOLO to get sessionid
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


@csrf_exempt
@require_http_methods(["POST"])
def api_initiate(request):
    try:
        data = json.loads(request.body.decode("utf-8"))
    except Exception:
        return HttpResponseBadRequest("JSON invalide")

    amount = int(data.get("amount", 0))
    openimis_ref = data.get("openimis_ref")
    description = data.get("description", "Cotisation AMG")
    # beneficiary_id = data.get("beneficiary_id")

    if amount <= 0 or not openimis_ref :
    # if amount <= 0 or not openimis_ref or not beneficiary_id:
        return HttpResponseBadRequest("Paramètres invalides")

    purchaseref = f"AMG-{openimis_ref}-{int(datetime.utcnow().timestamp())}"

    payment = Payment.objects.create(
        purchaseref=purchaseref,
        openimis_ref=openimis_ref,
        # beneficiary_id=beneficiary_id,
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

    redirect_form_data = {
        "sessionid": sessionid,
        "merchantid": HOLO_MERCHANT_ID,
        "amount": amount,
        "currency": HOLO_CURRENCY,
        "purchaseref": purchaseref,
        "description": description,
        "accepturl": ACCEPT_URL,
        "declineurl": DECLINE_URL,
        "cancelurl": CANCEL_URL,
    }

    return JsonResponse({
        "sessionid": sessionid,
        "merchantid": HOLO_MERCHANT_ID,
        "purchaseref": purchaseref,
        "redirect_form_data": redirect_form_data,
        "session_error": session_error,
    })


def redirect_accept(request):
    return render(request, "payments/redirect_accept.html", {})


def redirect_decline(request):
    return render(request, "payments/redirect_decline.html", {})


def redirect_cancel(request):
    return render(request, "payments/redirect_cancel.html", {})


@csrf_exempt
@require_http_methods(["POST"])
def api_notify(request):
    # IP whitelist check
    remote_addr = request.META.get('REMOTE_ADDR') or request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip()
    if remote_addr and not is_ip_whitelisted(remote_addr):
        logger.warning(f"Notify IP non autorisée: {remote_addr}")
        return HttpResponseForbidden("IP non autorisée")

    body = request.body
    try:
        payload = json.loads(body.decode("utf-8"))
    except Exception:
        return HttpResponseBadRequest("JSON invalide")

    ref_trans = payload.get("ref_trans")
    status = payload.get("status")
    amount_paid = int(payload.get("amount_paid", 0))
    msisdn = payload.get("msisdn")
    timestamp_str = payload.get("timestamp")
    merchantid = payload.get("merchantid")
    purchaseref = payload.get("purchaseref")
    signature = payload.get("signature", "")

    # Optional signature verification
    if signature and not verify_signature(body, signature):
        logger.error("Signature invalide")
        return HttpResponseForbidden("Signature invalide")

    try:
        payment = Payment.objects.get(purchaseref=purchaseref)
    except Payment.DoesNotExist:
        return HttpResponseBadRequest("purchaseref inconnu")

    # Validate merchant and amount
    if merchantid != HOLO_MERCHANT_ID:
        return HttpResponseForbidden("MerchantID invalide")
    if amount_paid != payment.amount:
        logger.warning("Montant payé ne correspond pas")
        # Mark dispute but continue to record

    payment.ref_trans = ref_trans or payment.ref_trans
    payment.msisdn = msisdn or payment.msisdn
    payment.timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00')) if timestamp_str else None

    normalized = (status or '').lower()
    if normalized in ("success", "accept"):
        payment.status = "paid"
        # Activate rights placeholder: in real openIMIS, trigger activation flow
        # logger.info(f"Activation des droits pour {payment.beneficiary_id} / {payment.purchaseref}")
        logger.info(f"Activation des droits pour  {payment.purchaseref}")
    elif normalized in ("decline", "fail"):
        payment.status = "declined"
    elif normalized == "cancel":
        payment.status = "cancelled"
    elif normalized == "timeout":
        payment.status = "timeout"
    else:
        payment.status = "error"

    payment.save()
    logger.info(f"Notify traité: {payment.purchaseref} -> {payment.status}")

    # Double journalisation (append JSON line)
    # try:
    #     with open(BASE_DIR / 'journal_notify.log', 'a', encoding='utf-8') as f:
    #         f.write(json.dumps(payload) + "\n")
    # except Exception as e:
    #     logger.error(f"Journalisation notify échouée: {e}")

    return JsonResponse({"status": "OK"})