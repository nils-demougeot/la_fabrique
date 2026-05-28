from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('patrons/', views.patrons, name='patrons'),
    path('patrons/<int:pk>/', views.patron_detail, name='patron_detail'),
    path('patrons/<int:patron_pk>/etape/<int:etape_num>/', views.etape_projet, name='etape_projet'),
    path('ajout_textile/', views.ajout_textile, name='ajout_textile'),
    path('communaute/', views.communaute, name='communaute'),

    path('connexion/', auth_views.LoginView.as_view(template_name='core/connexion.html'), name='connexion'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),

    path('inscription/', views.inscription, name='inscription'),
    path('inscription/etape1/', views.inscription_etape1, name='inscription_etape1'),
    path('inscription/etape2/', views.inscription_etape2, name='inscription_etape2'),
    path('inscription/etape3/', views.inscription_etape3, name='inscription_etape3'),

    path('camera-demo/', views.camera_demo, name='camera_demo'),
]
