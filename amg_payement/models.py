from django.db import models


class Payment(models.Model):
    purchaseref = models.CharField(max_length=64, unique=True)
    openimis_ref = models.CharField(max_length=64)
    # beneficiary_id = models.CharField(max_length=64)
    amount = models.IntegerField()
    currency = models.IntegerField(default=174)
    description = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=32, default='initiated')
    ref_trans = models.CharField(max_length=128, blank=True)
    merchantid = models.CharField(max_length=32, blank=True)
    sessionid = models.CharField(max_length=128, blank=True)
    msisdn = models.CharField(max_length=32, blank=True)
    timestamp = models.DateTimeField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.purchaseref} ({self.status})"