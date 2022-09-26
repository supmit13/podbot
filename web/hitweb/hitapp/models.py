from django.db import models
from django.contrib.auth.models import User

class HitManager(models.Model):
    platform = models.CharField(max_length=100, null=False, blank=False, default='')
    targeturl = models.TextField()
    targetcount = models.IntegerField(null=False, blank=False, default=1)
    actualcount = models.IntegerField(null=False, blank=False, default=1)
    starttime = models.DateTimeField(auto_now=True)
    endtime = models.DateTimeField(blank=True, null=True, default='0001-01-01 00:00:01')
    user = models.ForeignKey(User, on_delete=models.PROTECT)
    debugstatus = models.BooleanField(default=False)
    humanizestatus = models.BooleanField(default=False)
    loggingstatus = models.BooleanField(default=True)
    cleanupstatus = models.BooleanField(default=True)
    forcedstop = models.BooleanField(default=False)
    

    class Meta:
        verbose_name = "Hits Management Table"
        db_table = 'hitweb_manager'


class Proxies(models.Model):
    proxyip = models.CharField(max_length=16, null=False, blank=False, default='')
    proxyport = models.IntegerField(null=False, blank=False, default=3128)
    proxytype = models.CharField(max_length=10, null=False, blank=False, default='https')
    proxyurl = models.CharField(max_length=35, null=False, blank=False, default='')
    provider = models.CharField(max_length=20, null=False, blank=False, default='rayobyte')
    addedon = models.DateTimeField(auto_now=True)
    removedon = models.DateTimeField(default='0001-01-01 00:00:01')
    deleted = models.BooleanField(null=False, blank=False, default=False)


    class Meta:
        verbose_name = "Proxies Management Table"
        db_table = 'hitweb_proxies'


class ProxyUsage(models.Model):
    proxy = models.ForeignKey(Proxies, on_delete=models.PROTECT)
    hit = models.ForeignKey(HitManager, on_delete=models.PROTECT)

    class Meta:
        verbose_name = "Proxies Usage Table"
        db_table = 'hitweb_proxyusage'



