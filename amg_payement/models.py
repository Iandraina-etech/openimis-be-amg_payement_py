from django.db import models


class Payment(models.Model):
    purchaseref = models.CharField(max_length=64, unique=True)
    openimis_ref = models.CharField(max_length=64)
    # beneficiary_id = models.CharField(max_length=64)
    amount = models.IntegerField()
    currency = models.IntegerField(default=174)
    description = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=32, default='initiated')
    merchantid = models.CharField(max_length=32, blank=True)
    sessionid = models.CharField(max_length=128, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    clientid = models.CharField(max_length=255, blank=True,null=True)
    cname=models.CharField(max_length=255, blank=True,null=True)
    mobile=models.CharField(max_length=20, blank=True,null=True)
    paymentref=models.CharField(max_length=255, blank=True,null=True)
    payid=models.CharField(max_length=255, blank=True,null=True)
    timestamp=models.DateTimeField(blank=True,null=True)
    ipaddr=models.CharField(max_length=50, blank=True,null=True)
    status_return=models.CharField(max_length=50, blank=True,null=True)
    policy_uuid=models.CharField(max_length=255, blank=True,null=True)

    def __str__(self):
        return f"{self.purchaseref} ({self.status})"