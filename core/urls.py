from django.urls import path, reverse_lazy
from django.contrib.auth import views as auth_views
from . import views
from . import views_communaute as vc

# Alias court pour le blocage de la communauté pendant la bêta.
_bloc_communaute = views.communaute_active_requise

urlpatterns = [
    path('', views.home, name='home'),
    path('service-worker.js', views.service_worker, name='service_worker'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('cours/', views.cours, name='cours'),
    path('patrons/', views.patrons, name='patrons'),
    path('patrons/creer/', views.creer_patron, name='creer_patron'),
    path('patrons/<int:pk>/', views.patron_detail, name='patron_detail'),
    path('patrons/<int:pk>/faisabilite/', views.faisabilite_patron, name='faisabilite_patron'),
    path('patrons/<int:pk>/plan-coupe/sauvegarder/', views.plan_coupe_save, name='plan_coupe_save'),
    path('patrons/<int:pk>/patron.pdf', views.patron_pdf, name='patron_pdf'),
    path('patrons/<int:pk>/instructions.pdf', views.patron_instructions_pdf, name='patron_instructions_pdf'),
    path('patrons/<int:pk>/export.json', views.patron_export, name='patron_export'),
    path('patrons/<int:patron_pk>/etape/<int:etape_num>/', views.etape_projet, name='etape_projet'),
    path('patrons/<int:patron_pk>/etape/<int:etape_num>/geste/<int:geste_num>/', views.etape_projet, name='etape_projet_geste'),
    path('patrons/<int:pk>/like/', views.toggle_like, name='toggle_like'),
    path('patrons/<int:pk>/terminer/', views.terminer_projet, name='terminer_projet'),
    path('patrons/<int:pk>/passeport/', views.passeport_circulaire, name='passeport_circulaire'),
    path('passeport/<int:patron_pk>/<int:user_pk>/', views.passeport_public, name='passeport_public'),
    path('qrcode/', views.qrcode_view, name='qrcode_view'),
    path('ajout_textile/', views.ajout_textile, name='ajout_textile'),
    path('ajout_textile/detourage-auto/', views.detourage_auto, name='detourage_auto'),
    # ── Communauté « atelier » (onglet Partage) ────────────────────────────
    # Page à trois onglets (Atelier / Amis / Entraide) + les dix écrans qui en
    # découlent. Le décorateur communaute_active_requise gouverne toujours
    # l'ouverture de la rubrique (réglage COMMUNAUTE_ACTIVE).
    path('communaute/', _bloc_communaute(vc.communaute), name='communaute'),
    path('communaute/progression/', _bloc_communaute(vc.progression), name='communaute_progression'),
    path('communaute/progression/vue/', _bloc_communaute(vc.progression_vue), name='communaute_progression_vue'),
    path('communaute/notifications/', _bloc_communaute(vc.notifications), name='communaute_notifications'),
    path('communaute/amies/', _bloc_communaute(vc.amies), name='communaute_amies'),
    path('communaute/amies/partager/', _bloc_communaute(vc.partager_code), name='communaute_partager_code'),
    path('communaute/messages/', _bloc_communaute(vc.messages_prives), name='communaute_messages'),
    path('communaute/messages/<int:pk>/ouvrir/', _bloc_communaute(vc.ouvrir_message_prive), name='communaute_ouvrir_mp'),
    path('communaute/amies/<int:pk>/inviter/', _bloc_communaute(vc.inviter_amie), name='communaute_inviter'),
    path('communaute/amies/demande/<int:pk>/', _bloc_communaute(vc.repondre_amitie), name='communaute_repondre_amitie'),
    path('communaute/couturiere/<int:pk>/', _bloc_communaute(vc.profil_couturiere), name='communaute_profil'),
    path('communaute/classement/', _bloc_communaute(vc.classement_complet), name='communaute_classement'),
    path('communaute/serie/', _bloc_communaute(vc.serie), name='communaute_serie'),
    path('communaute/serie/entretenir/', _bloc_communaute(vc.entretenir_serie), name='communaute_entretenir_serie'),
    path('communaute/boutique/', _bloc_communaute(vc.boutique), name='communaute_boutique'),
    path('communaute/boutique/<int:pk>/acheter/', _bloc_communaute(vc.acheter_offre), name='communaute_acheter'),
    path('communaute/coffre/', _bloc_communaute(vc.ouvrir_coffre), name='communaute_coffre_jour'),
    path('communaute/coffre/resultat/', _bloc_communaute(vc.coffre_resultat), name='communaute_coffre_resultat'),
    path('communaute/coffre/<int:pk>/', _bloc_communaute(vc.ouvrir_coffre), name='communaute_coffre'),
    path('communaute/ecussons/', _bloc_communaute(vc.ecussons), name='communaute_ecussons'),
    path('communaute/duel/<int:pk>/', _bloc_communaute(vc.duel), name='communaute_duel'),
    path('communaute/defier/<int:pk>/', _bloc_communaute(vc.defier), name='communaute_defier'),
    path('communaute/salon/<int:pk>/', _bloc_communaute(vc.salon), name='communaute_salon'),
    path('communaute/salon/<int:pk>/envoyer/', _bloc_communaute(vc.envoyer_message), name='communaute_envoyer_message'),
    path('communaute/message/<int:pk>/reagir/', _bloc_communaute(vc.reagir_message), name='communaute_reagir'),
    path('communaute/evenement/<int:pk>/', _bloc_communaute(vc.evenement), name='communaute_evenement'),
    path('communaute/evenement/<int:pk>/inscription/', _bloc_communaute(vc.basculer_inscription), name='communaute_inscription'),
    path('communaute/quetes/', _bloc_communaute(vc.quetes), name='communaute_quetes'),
    path('communaute/fin-de-saison/', _bloc_communaute(vc.fin_saison), name='communaute_fin_saison'),
    path('communaute/fin-de-saison/reclamer/', _bloc_communaute(vc.reclamer_fin_saison), name='communaute_reclamer_saison'),
    path('communaute/defi-ville/', _bloc_communaute(vc.defi_ville), name='communaute_defi_ville'),
    path('communaute/declarer-m2/', _bloc_communaute(vc.declarer_m2), name='communaute_declarer_m2'),
    path('communaute/salons/', _bloc_communaute(vc.salons), name='communaute_salons'),
    path('communaute/salons/creer/', _bloc_communaute(vc.creer_salon), name='communaute_creer_salon'),
    path('communaute/salon/<int:pk>/rejoindre/', _bloc_communaute(vc.rejoindre_salon), name='communaute_rejoindre_salon'),
    path('communaute/question/', _bloc_communaute(vc.poser_question), name='communaute_poser_question'),
    path('communaute/question/<int:pk>/', _bloc_communaute(vc.question), name='communaute_question'),
    path('communaute/question/<int:pk>/repondre/', _bloc_communaute(vc.repondre_question), name='communaute_repondre'),
    path('communaute/reponse/<int:pk>/valider/', _bloc_communaute(vc.valider_reponse), name='communaute_valider_reponse'),
    path('communaute/troc/<int:pk>/prendre/', _bloc_communaute(vc.prendre_annonce), name='communaute_prendre_annonce'),
    path('communaute/amies/ajouter/', _bloc_communaute(vc.ajouter_amie), name='communaute_ajouter_amie'),

    # Journal de créations (ancienne communauté photo) — toujours accessible.
    path('communaute/creer/', _bloc_communaute(views.creer_post), name='creer_post'),
    path('communaute/mes-posts/', _bloc_communaute(views.mes_posts), name='mes_posts'),
    path('communaute/post/<int:pk>/', _bloc_communaute(views.detail_post), name='detail_post'),
    path('communaute/post/<int:pk>/like/', _bloc_communaute(views.toggle_like_post), name='toggle_like_post'),
    path('communaute/post/<int:pk>/sauvegarder/', _bloc_communaute(views.toggle_sauvegarde), name='toggle_sauvegarde'),
    path('communaute/post/<int:pk>/commenter/', _bloc_communaute(views.ajouter_commentaire), name='ajouter_commentaire'),
    path('communaute/post/<int:pk>/supprimer/', _bloc_communaute(views.supprimer_post), name='supprimer_post'),
    path('communaute/profil/<int:pk>/', _bloc_communaute(views.profil_utilisateur), name='profil_utilisateur'),
    path('communaute/profil/<int:pk>/suivre/', _bloc_communaute(views.toggle_suivi), name='toggle_suivi'),
    path('mes-tissus/', views.mes_tissus, name='mes_tissus'),
    path('mes-tissus/<int:pk>/', views.detail_vetement, name='detail_vetement'),
    path('mes-tissus/supprimer/', views.supprimer_vetements, name='supprimer_vetements'),

    path('acheter-badge/', views.acheter_badge, name='acheter_badge'),
    path('mon-profil/', views.mon_profil, name='mon_profil'),

    # Vérification d'e-mail
    path('verifier-email/<str:token>/', views.verifier_email, name='verifier_email'),
    path('renvoyer-verification/', views.renvoyer_verification, name='renvoyer_verification'),
    path('diagnostic-email/', views.diagnostic_email, name='diagnostic_email'),  # superadmin uniquement

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
    path('inscription/bienvenue/', views.inscription_bienvenue, name='inscription_bienvenue'),
]
