"""hitweb URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/3.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import include, path
from hitapp import views
import hitweb

urlpatterns = [
    path('', views.dashboard, name='index'),
    path('dologin/', views.dologin, name='dologin'),
    path('logout/', views.logout, name='logout'),
    path('login/', views.showlogin, name='showlogin'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('runbot/', views.runhitbot, name='runhitbot'),
    path('stopbot/', views.stophitbot, name='stophitbot'),
    path('runstatus/', views.runstatus, name='runstatus'),
    path('manageproxies/', views.manageproxies, name='manageproxies'),
    path('addproxies/', views.addproxies, name='addproxies'),
    path('editproxies/', views.editproxies, name='editproxies'),
    path('deleteproxies/', views.deleteproxy, name='deleteproxy'),
    path('saveproxies/', views.saveproxy, name='saveproxy'),
    path('managekeys/', views.managekeys, name='managekeys'),
    path('adduser/', views.adduser, name='adduser'),
]


