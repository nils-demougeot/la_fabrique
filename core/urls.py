from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('ajout_textile/', views.ajout_textile, name='ajout_textile'),

    path('connexion/', auth_views.LoginView.as_view(template_name='core/connexion.html'), name='connexion'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),

    path('inscription/', views.inscription, name='inscription'),
    path('inscription/etape1/', views.inscription_etape1, name='inscription_etape1'),
    path('inscription/etape2/', views.inscription_etape2, name='inscription_etape2'),
    path('inscription/etape3/', views.inscription_etape3, name='inscription_etape3'),
]
