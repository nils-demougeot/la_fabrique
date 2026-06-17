from django.urls import path, reverse_lazy
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('patrons/', views.patrons, name='patrons'),
    path('patrons/creer/', views.creer_patron, name='creer_patron'),
    path('patrons/<int:pk>/', views.patron_detail, name='patron_detail'),
    path('patrons/<int:pk>/faisabilite/', views.faisabilite_patron, name='faisabilite_patron'),
    path('patrons/<int:pk>/patron.pdf', views.patron_pdf, name='patron_pdf'),
    path('patrons/<int:pk>/instructions.pdf', views.patron_instructions_pdf, name='patron_instructions_pdf'),
    path('patrons/<int:pk>/export.json', views.patron_export, name='patron_export'),
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

    path('acheter-badge/', views.acheter_badge, name='acheter_badge'),
    path('mon-profil/', views.mon_profil, name='mon_profil'),

    # Vérification d'e-mail
    path('verifier-email/<str:token>/', views.verifier_email, name='verifier_email'),
    path('renvoyer-verification/', views.renvoyer_verification, name='renvoyer_verification'),

    # RGPD
    path('politique-confidentialite/', views.politique_confidentialite, name='politique_confidentialite'),
    path('mon-profil/exporter-donnees/', views.exporter_donnees, name='exporter_donnees'),
    path('mon-profil/supprimer-compte/', views.supprimer_compte, name='supprimer_compte'),

    path('connexion/', auth_views.LoginView.as_view(template_name='core/connexion.html'), name='connexion'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),

    # Réinitialisation de mot de passe (noms standards utilisés par le lien e-mail)
    path('mot-de-passe-oublie/', auth_views.PasswordResetView.as_view(
        template_name='core/password_reset.html',
        email_template_name='core/password_reset_email.txt',
        subject_template_name='core/password_reset_subject.txt',
        success_url=reverse_lazy('password_reset_done'),
    ), name='password_reset'),
    path('mot-de-passe-oublie/envoye/', auth_views.PasswordResetDoneView.as_view(
        template_name='core/password_reset_done.html',
    ), name='password_reset_done'),
    path('reinitialiser/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(
        template_name='core/password_reset_confirm.html',
        success_url=reverse_lazy('password_reset_complete'),
    ), name='password_reset_confirm'),
    path('reinitialiser/termine/', auth_views.PasswordResetCompleteView.as_view(
        template_name='core/password_reset_complete.html',
    ), name='password_reset_complete'),

    path('inscription/', views.inscription, name='inscription'),
    path('inscription/etape1/', views.inscription_etape1, name='inscription_etape1'),
    path('inscription/etape2/', views.inscription_etape2, name='inscription_etape2'),
    path('inscription/etape3/', views.inscription_etape3, name='inscription_etape3'),
]
