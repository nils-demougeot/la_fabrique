from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('patrons/', views.patrons, name='patrons'),
    path('patrons/<int:pk>/', views.patron_detail, name='patron_detail'),
    path('patrons/<int:patron_pk>/etape/<int:etape_num>/', views.etape_projet, name='etape_projet'),
    path('patrons/<int:pk>/like/', views.toggle_like, name='toggle_like'),
    path('patrons/<int:pk>/terminer/', views.terminer_projet, name='terminer_projet'),
    path('patrons/<int:pk>/passeport/', views.passeport_circulaire, name='passeport_circulaire'),
    path('passeport/<int:patron_pk>/<int:user_pk>/', views.passeport_public, name='passeport_public'),
    path('qrcode/', views.qrcode_view, name='qrcode_view'),
    path('ajout_textile/', views.ajout_textile, name='ajout_textile'),
    path('communaute/', views.communaute, name='communaute'),
    path('communaute/creer/', views.creer_post, name='creer_post'),
    path('communaute/mes-posts/', views.mes_posts, name='mes_posts'),
    path('communaute/post/<int:pk>/', views.detail_post, name='detail_post'),
    path('communaute/post/<int:pk>/like/', views.toggle_like_post, name='toggle_like_post'),
    path('communaute/post/<int:pk>/sauvegarder/', views.toggle_sauvegarde, name='toggle_sauvegarde'),
    path('communaute/post/<int:pk>/commenter/', views.ajouter_commentaire, name='ajouter_commentaire'),
    path('communaute/post/<int:pk>/supprimer/', views.supprimer_post, name='supprimer_post'),
    path('communaute/profil/<int:pk>/', views.profil_utilisateur, name='profil_utilisateur'),
    path('communaute/profil/<int:pk>/suivre/', views.toggle_suivi, name='toggle_suivi'),
    path('mes-tissus/', views.mes_tissus, name='mes_tissus'),
    path('mes-tissus/<int:pk>/', views.detail_vetement, name='detail_vetement'),
    path('mes-tissus/supprimer/', views.supprimer_vetements, name='supprimer_vetements'),

    path('connexion/', auth_views.LoginView.as_view(template_name='core/connexion.html'), name='connexion'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),

    path('inscription/', views.inscription, name='inscription'),
    path('inscription/etape1/', views.inscription_etape1, name='inscription_etape1'),
    path('inscription/etape2/', views.inscription_etape2, name='inscription_etape2'),
    path('inscription/etape3/', views.inscription_etape3, name='inscription_etape3'),
]
