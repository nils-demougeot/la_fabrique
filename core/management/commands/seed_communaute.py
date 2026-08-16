"""Peuple la communauté « atelier » : saison, paliers, écussons, ligue,
quêtes, boutique, salons, événements, amies de démonstration.

    python manage.py seed_communaute --user testdesign

Idempotent : relancer la commande met à jour l'existant sans doublonner.
L'option ``--reset`` efface d'abord les contenus de démonstration.
"""

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from core import gamification as jeu
from core.models import (
    Amitie, AnnonceTroc, CoffreQuotidien, ContributionDefiVille, DefiVille,
    DeclarationM2, DisponibiliteEntraide, Duel, Ecusson, EcussonObtenu,
    EvenementCommunaute,
    InscriptionEvenement, MessageSalon, Notification, OffreBoutique, PalierSaison,
    ParticipationLigue, Patron, PieceDuel, Quete, QuestionEntraide,
    QueteUtilisateur, ReactionMessage, ReponseEntraide, Salon, Saison,
    TransactionPieces, Utilisateur,
)

# ── Couturières de démonstration ────────────────────────────────────────────
# (identifiant, prénom, nom, XP de saison, série, quartier, arrondissement,
#  teinte du jeton — reprise des maquettes)
AMIES = [
    ('sofia.d',  'Sofia',  'Delcourt', 1240, 21, 'Croix-Rousse', 'Lyon 1ᵉʳ', 't-or'),
    ('lea.p',    'Léa',    'Pontier',  1105,  9, 'Croix-Rousse', 'Lyon 4ᵉ',  't-vert'),
    ('thomas.b', 'Thomas', 'Berger',   1020,  4, 'Guillotière',  'Lyon 7ᵉ',  't-violet'),
    ('noor.k',   'Noor',   'Khalil',    960,  6, 'Vaise',        'Lyon 9ᵉ',  't-corail'),
    ('amine.r',  'Amine',  'Rachid',    880,  0, 'Guillotière',  'Lyon 7ᵉ',  't-or'),
    ('maya.j',   'Maya',   'Jourdan',   815,  3, 'Croix-Rousse', 'Lyon 4ᵉ',  't-vert'),
    ('chloe.v',  'Chloé',  'Vasseur',   780,  2, 'Vaise',        'Lyon 9ᵉ',  't-violet'),
    ('ines.b',   'Inès',   'Baroud',    742,  1, 'Guillotière',  'Lyon 3ᵉ',  't-corail'),
]

ECUSSONS = [
    # (code, nom, catégorie, rang, condition, icône, haut, bas, rareté)
    ('toile',      'Toile',       'matieres', 'toile', '148 pièces',  'toile',   '#6BE0A0', '#12633A', 38),
    ('denim',      'Denim',       'matieres', 'toile', '42 ourlets',  'aiguille', '#8FB4E0', '#3F5C82', 26),
    ('laine',      'Laine',       'matieres', 'laine', '20 aides',    'bobine',  '#D6C4FF', '#5B45B8', 17),
    ('braise-or',  "Braise d'or", 'matieres', 'or',    '30 jours',    'flamme-p', '#FFE9A8', '#C98A0E', 4),
    ('eclair',     'Éclair',      'defis',    'toile', '10 duels',    'eclair',  '#9FE8F5', '#2E7EA3', 22),
    ('etoile',     'Étoile',      'defis',    'laine', '5 patrons',   'etoile',  '#E3C4FF', '#7C3AED', 14),
    ('ruban',      'Ruban',       'defis',    'or',    '1re place',   'ruban',   '#FFC2DA', '#D6538C', 6),
    ('bobine',     'Bobine',      'entraide', 'toile', '50 m cousus', 'bobine',  '#B9CBE8', '#4A6A94', 31),
    ('mentor',     'Mentor',      'entraide', 'laine', '3 cours',     'mentor',  '#F0D08A', '#A9720E', 11),
    ('diamant',    'Diamant',     'entraide', 'or',    'Niv. 6',      'diamant', '#8DEDD9', '#1B8F7A', 3),
]

# (code, libellé, détail, période, objectif, XP, pièces, ordre, bouton, route)
QUETES = [
    ('analyser-vetement', 'Analyser un vêtement', 'Ajoute un tissu à ta banque',
     'jour', 1, 20, 0, 0, 'Ajouter un tissu', 'ajout_textile'),
    ('repondre-salon', 'Répondre dans un salon', 'Un message dans un salon suffit',
     'jour', 1, 15, 0, 1, 'Ouvrir un salon', 'communaute'),
    ('etape-projet', 'Terminer une étape de projet', 'Reprends là où tu en étais',
     'jour', 1, 40, 0, 2, 'Reprendre le projet', 'patrons'),
    ('aider-couturiere', 'Aider 3 couturiers', 'Réponds à trois questions',
     'semaine', 3, 0, 80, 0, 'Voir les questions', 'communaute'),
]


class Command(BaseCommand):
    help = "Peuple la communauté « atelier » (saison, ligue, écussons, salons, événements)."

    def add_arguments(self, parser):
        parser.add_argument('--user', default=None,
                            help="Identifiant de la joueuse principale (défaut : le premier compte non-admin).")
        parser.add_argument('--reset', action='store_true',
                            help="Efface les contenus de démonstration avant de recréer.")

    @transaction.atomic
    def handle(self, *args, **options):
        if options['reset']:
            self._reset()

        moi = self._joueuse_principale(options['user'])
        self.stdout.write(f"Joueuse principale : {moi.username}")

        ecussons = self._ecussons()
        saison = self._saison()
        paliers = self._paliers(saison, ecussons)
        self._quetes()
        self._boutique(ecussons)

        amies = self._amies()
        self._profil_principal(moi)
        self._ligue(saison, moi, amies)
        self._ecussons_obtenus(moi, ecussons)
        self._amities(moi, amies)
        self._duel(moi, amies)
        self._defi_ville(moi, amies)
        self._salons(moi, amies)
        self._evenements(moi, amies)
        self._entraide(moi, amies)
        self._troc(amies)
        self._transactions(moi)
        self._notifications(moi, amies)

        self.stdout.write(self.style.SUCCESS(
            "Communauté peuplée. Ouvre /communaute/ pour voir le résultat."
        ))

    # ── Remise à zéro ──────────────────────────────────────────────────────
    def _reset(self):
        # PalierReclame et EcussonObtenu disparaissent en cascade avec
        # PalierSaison ; l'avancement des quêtes et les coffres du jour, eux,
        # survivraient et fausseraient une démonstration relancée le même jour
        # (les récompenses ne seraient versées qu'une fois).
        for modele in (ReactionMessage, MessageSalon, Salon, InscriptionEvenement,
                       EvenementCommunaute,
                       PieceDuel, Duel, ReponseEntraide, QuestionEntraide, AnnonceTroc,
                       ContributionDefiVille, DeclarationM2, DefiVille, OffreBoutique,
                       PalierSaison,
                       ParticipationLigue, Saison, DisponibiliteEntraide, Amitie,
                       TransactionPieces, QueteUtilisateur, CoffreQuotidien,
                       Notification):
            modele.objects.all().delete()
        self.stdout.write("Contenus de démonstration effacés.")

    # ── Comptes ────────────────────────────────────────────────────────────
    def _joueuse_principale(self, identifiant):
        if identifiant:
            return Utilisateur.objects.get(username=identifiant)
        joueuse = Utilisateur.objects.filter(is_superuser=False).order_by('pk').first()
        if not joueuse:
            joueuse = Utilisateur.objects.order_by('pk').first()
        if not joueuse:
            raise SystemExit("Aucun compte en base : crée d'abord un utilisateur.")
        return joueuse

    def _amies(self):
        comptes = []
        for identifiant, prenom, nom, xp, serie, quartier, arrondissement, teinte in AMIES:
            compte, cree = Utilisateur.objects.get_or_create(
                username=identifiant,
                defaults={'first_name': prenom, 'last_name': nom,
                          'email': f"{identifiant}@exemple.fr", 'email_verifie': True},
            )
            if cree:
                compte.set_unusable_password()
                compte.first_name, compte.last_name = prenom, nom
                compte.soldePieces = 120
                compte.save()

            profil = jeu.profil_de(compte)
            profil.serie_actuelle = serie
            profil.serie_record = max(serie, profil.serie_record, serie + 3)
            profil.quartier = quartier
            profil.arrondissement = arrondissement
            profil.teinte = teinte
            profil.derniere_activite = timezone.localdate() if serie else None
            profil.xp_total = xp + 2400
            profil.save()
            comptes.append((compte, xp))
        return comptes

    def _profil_principal(self, moi):
        """Aligne la joueuse principale sur l'état montré par les maquettes."""
        # Sans prénom, les jetons ronds afficheraient les deux premières
        # lettres de l'identifiant : on donne un état civil à la joueuse.
        if not moi.first_name:
            moi.first_name, moi.last_name = 'Camille', 'Moreau'
            moi.save(update_fields=['first_name', 'last_name'])

        profil = jeu.profil_de(moi)
        # Le niveau ne vient PAS d'ici : il se calcule sur les CP d'atelier
        # (tissus, étapes, projets). `xp_total` reste le cumul d'XP gagnée,
        # que seule la ligue exploite.
        profil.xp_total = 3740
        profil.serie_actuelle = 12
        profil.serie_record = 19
        profil.gels = 2
        profil.ville = 'Lyon'
        profil.quartier = 'Croix-Rousse'
        profil.arrondissement = 'Lyon 4ᵉ'
        profil.teinte = 't-violet'
        profil.derniere_activite = timezone.localdate()
        # Calendrier de la semaine : lundi→samedi faits, mercredi gelé.
        aujourdhui = timezone.localdate()
        faits = [j for j in range(aujourdhui.weekday()) if j != 2]
        profil.jours_semaine = ','.join(str(j) for j in faits)
        profil.semaine_cle = jeu._cle_semaine(aujourdhui)
        profil.save()

        moi.soldePieces = 248
        moi.save(update_fields=['soldePieces'])

    # ── Saison, paliers, ligue ─────────────────────────────────────────────
    def _saison(self):
        aujourdhui = timezone.localdate()
        saison, _ = Saison.objects.update_or_create(
            numero=3,
            defaults={'nom': 'Toile', 'active': True,
                      'date_debut': aujourdhui - timedelta(days=42),
                      'date_fin': aujourdhui + timedelta(days=18)},
        )
        Saison.objects.exclude(pk=saison.pk).update(active=False)
        return saison

    def _paliers(self, saison, ecussons):
        """Un palier par montée de niveau : les seuils sont ceux du barème
        d'atelier (`gamification.NIVEAUX_ATELIER`), pas des valeurs choisies à
        part — franchir un niveau ouvre un coffre."""
        patron = Patron.objects.order_by('pk').first()

        # (récompense) indexée sur le niveau atteint, du 2 au 6.
        recompenses = [
            ('Coffre de 15 pièces', 'Bienvenue dans la saison', 15, 0, None, None),
            ('Écusson « premier ourlet »', 'Écusson « premier ourlet »', 0, 0, None, ecussons.get('denim')),
            ('Coffre de 40 pièces', '+ patron « sac banane »', 40, 0, patron, None),
            ('Un gel de série de plus', 'Un gel de série de plus', 0, 1, None, None),
            ('Coffre de 90 pièces', 'Le grand coffre de fin', 90, 0, None, ecussons.get('ruban')),
        ]
        # Seuils des niveaux 2→6 : 120, 320, 620, 1000, 1500 CP.
        seuils = [seuil for seuil, _ in jeu.NIVEAUX_ATELIER[1:]]

        paliers = {}
        for numero, (seuil, lot) in enumerate(zip(seuils, recompenses), start=1):
            titre, detail, pieces, gels, patron_lie, ecusson = lot
            palier, _ = PalierSaison.objects.update_or_create(
                saison=saison, numero=numero,
                defaults={'points_requis': seuil, 'titre': titre, 'detail': detail,
                          'pieces': pieces, 'gels': gels,
                          'patron': patron_lie, 'ecusson': ecusson},
            )
            paliers[numero] = palier
        return paliers

    def _ligue(self, saison, moi, amies):
        ParticipationLigue.objects.update_or_create(
            utilisateur=moi, saison=saison,
            defaults={'ligue': 'or', 'xp_saison': 1070,
                      'pieces_finies': 6, 'm2_sauves': 4.8},
        )
        for compte, xp in amies:
            ParticipationLigue.objects.update_or_create(
                utilisateur=compte, saison=saison,
                defaults={'ligue': 'or', 'xp_saison': xp,
                          'pieces_finies': 4, 'm2_sauves': 3.2},
            )

    # ── Écussons ───────────────────────────────────────────────────────────
    def _ecussons(self):
        catalogue = {}
        for ordre, (code, nom, categorie, rang, condition, icone, haut, bas, rarete) in enumerate(ECUSSONS):
            ecusson, _ = Ecusson.objects.update_or_create(
                code=code,
                defaults={'nom': nom, 'categorie': categorie, 'rang': rang,
                          'condition': condition, 'icone': icone,
                          'couleur_haut': haut, 'couleur_bas': bas,
                          'rarete': rarete, 'ordre': ordre,
                          'description': f"{nom} — {condition}."},
            )
            catalogue[code] = ecusson

        # Écussons encore secrets, affichés « ? » sur l'écran 45e.
        for code, nom in [('secret-1', 'Secret'), ('secret-2', '?')]:
            ecusson, _ = Ecusson.objects.update_or_create(
                code=code,
                defaults={'nom': nom, 'categorie': 'defis', 'rang': 'toile',
                          'secret': True, 'ordre': 90, 'icone': 'etoile',
                          'condition': '', 'couleur_haut': '#EDE4D6', 'couleur_bas': '#B0A493'},
            )
            catalogue[code] = ecusson

        # Écusson verrouillé montrant son coût en XP.
        ecusson, _ = Ecusson.objects.update_or_create(
            code='verrouille-1',
            defaults={'nom': 'Verrouillé', 'categorie': 'defis', 'rang': 'toile',
                      'condition': '80 XP', 'ordre': 95, 'icone': 'cadenas',
                      'couleur_haut': '#EDE4D6', 'couleur_bas': '#B0A493'},
        )
        catalogue['verrouille-1'] = ecusson

        Ecusson.objects.update_or_create(
            code='saison-03',
            defaults={'nom': 'Saison 03', 'categorie': 'defis', 'rang': 'or',
                      'condition': 'Saison 03', 'icone': 'etoile', 'ordre': 50,
                      'couleur_haut': '#FFF3C4', 'couleur_bas': '#D9930F',
                      'description': "Cousu sur ta carte d'atelier."},
        )
        return catalogue

    def _ecussons_obtenus(self, moi, ecussons):
        # Le diamant (niveau 10) et les secrets restent à décrocher : la
        # collection doit montrer des cases vides, pas un sans-faute.
        for code in ('toile', 'denim', 'laine', 'braise-or', 'eclair',
                     'etoile', 'ruban', 'bobine', 'mentor'):
            if code in ecussons:
                EcussonObtenu.objects.get_or_create(utilisateur=moi, ecusson=ecussons[code])

    # ── Quêtes et boutique ─────────────────────────────────────────────────
    def _quetes(self):
        for (code, libelle, detail, periode, objectif, xp, pieces, ordre,
             cta_libelle, cta_route) in QUETES:
            Quete.objects.update_or_create(
                code=code,
                defaults={'libelle': libelle, 'detail': detail, 'periode': periode,
                          'objectif': objectif, 'xp': xp, 'pieces': pieces,
                          'ordre': ordre, 'active': True,
                          'cta_libelle': cta_libelle, 'cta_route': cta_route},
            )

    def _boutique(self, ecussons):
        patrons = list(Patron.objects.order_by('pk')[:3])
        OffreBoutique.objects.update_or_create(
            code='pack-denim',
            defaults={'nom': 'Pack « 3 patrons denim »', 'categorie': 'pack',
                      'prix_pieces': 120, 'prix_barre': 180, 'motif': 'denim',
                      'mise_en_avant': True, 'ordre': 0,
                      'fin_offre': timezone.now() + timedelta(hours=14)},
        )
        catalogue_patrons = [
            ('patron-tote', 'Patron tote XL', 60, 'toile', 0),
            ('patron-robe', 'Robe portefeuille', 85, 'lin', 0),
            ('patron-chemise', 'Chemise oversize', 70, 'denim', 0),
            ('patron-jupe', 'Jupe plissée', 95, 'laine', 4),
        ]
        for ordre, (code, nom, prix, motif, niveau) in enumerate(catalogue_patrons):
            OffreBoutique.objects.update_or_create(
                code=code,
                defaults={'nom': nom, 'categorie': 'patron', 'prix_pieces': prix,
                          'motif': motif, 'niveau_requis': niveau, 'ordre': ordre,
                          'patron': patrons[ordre] if ordre < len(patrons) else None},
            )
        for ordre, (code, nom, quantite, prix, remise) in enumerate([
            ('gel-1', 'Gel ×1', 1, 40, ''),
            ('gel-3', 'Gel ×3', 3, 108, '-10%'),
            ('gel-5', 'Gel ×5', 5, 160, '-20%'),
        ]):
            OffreBoutique.objects.update_or_create(
                code=code,
                defaults={'nom': nom, 'categorie': 'gel', 'prix_pieces': prix,
                          'quantite_gels': quantite, 'remise': remise, 'ordre': ordre},
            )
        for ordre, (code, nom, ecusson_code, prix, niveau) in enumerate([
            ('ecusson-etoile', 'Étoile', 'etoile', 150, 0),
            ('ecusson-eclair', 'Éclair', 'eclair', 180, 0),
            ('ecusson-diamant', 'Diamant', 'diamant', 240, 6),
        ]):
            OffreBoutique.objects.update_or_create(
                code=code,
                defaults={'nom': nom, 'categorie': 'ecusson', 'prix_pieces': prix,
                          'niveau_requis': niveau, 'ordre': ordre,
                          'ecusson': ecussons.get(ecusson_code)},
            )

    # ── Liens sociaux ──────────────────────────────────────────────────────
    def _amities(self, moi, amies):
        """Six amitiés scellées, et deux invitations laissées en attente pour
        que l'écran « Trouver des amies » ait quelque chose à traiter."""
        en_attente = {'chloe.v', 'ines.b'}
        for compte, _ in amies:
            if compte.username in en_attente:
                # Invitation reçue : c'est `compte` qui a invité la joueuse.
                Amitie.objects.get_or_create(
                    de=compte, vers=moi, defaults={'acceptee': False})
            else:
                Amitie.objects.get_or_create(
                    de=moi, vers=compte, defaults={'acceptee': True})

    def _notifications(self, moi, amies):
        """Quelques notifications d'exemple, si la boîte est vide."""
        if Notification.objects.filter(destinataire=moi).exists():
            return
        par_nom = {c.username: c for c, _ in amies}
        maintenant = timezone.now()

        lignes = [
            ('amitie_demande', "Chloé veut t'ajouter", 'Accepte pour comparer vos semaines.',
             '/communaute/amies/', 'chloe.v', 40),
            ('duel', "Noor t'a défié", '18 h pour coudre le plus de pièces.',
             None, 'noor.k', 180),
            ('reponse', 'Sofia a répondu à ta question',
             'Aiguille jersey 80 et point zigzag serré.',
             '/communaute/?onglet=entraide', 'sofia.d', 1500),
            ('evenement', 'Repair café dans 8 jours', 'MJC Croix-Rousse · 14h',
             None, None, 3000),
        ]
        for type_notif, titre, detail, lien, auteur, minutes in lignes:
            notification = Notification.objects.create(
                destinataire=moi, type_notif=type_notif, titre=titre,
                detail=detail, lien=lien or '',
                emetteur=par_nom.get(auteur), lue=minutes > 1000,
            )
            Notification.objects.filter(pk=notification.pk).update(
                date_creation=maintenant - timedelta(minutes=minutes))

    def _duel(self, moi, amies):
        noor = next((c for c, _ in amies if c.username == 'noor.k'), None)
        if not noor:
            return
        duel, cree = Duel.objects.get_or_create(
            joueuse_a=moi, joueuse_b=noor, statut='en_cours',
            defaults={'score_a': 3, 'score_b': 2, 'mise_pieces': 20, 'xp_gain': 60,
                      'date_fin': timezone.now() + timedelta(hours=18)},
        )
        if cree:
            PieceDuel.objects.create(duel=duel, utilisateur=moi,
                                     titre='Trousse en denim', surface_m2=0.4, motif='denim')
            PieceDuel.objects.create(duel=duel, utilisateur=noor,
                                     titre='Coussin en lin', surface_m2=0.7, motif='lin')
            PieceDuel.objects.create(duel=duel, utilisateur=moi,
                                     titre='Tote bag rayé', surface_m2=1.1, motif='toile')

    # ── Défi de ville ──────────────────────────────────────────────────────
    def _defi_ville(self, moi, amies):
        defi, _ = DefiVille.objects.update_or_create(
            ville='Lyon',
            defaults={'titre': '500 m² recousus avant la fin du mois',
                      'objectif_m2': 500, 'actif': True,
                      'date_fin': timezone.localdate() + timedelta(days=6)},
        )
        ContributionDefiVille.objects.update_or_create(
            defi=defi, utilisateur=moi,
            defaults={'quartier': 'Croix-Rousse', 'm2': 4.8},
        )
        # Journal correspondant : le cumul ci-dessus doit être justifiable.
        if not DeclarationM2.objects.filter(defi=defi, utilisateur=moi).exists():
            for surface, commentaire, jours in [
                (1.1, 'Tote bag rayé', 1),
                (0.4, 'Trousse en denim', 4),
                (2.3, 'Rideau recoupé', 9),
                (1.0, 'Coussin en lin', 14),
            ]:
                declaration = DeclarationM2.objects.create(
                    defi=defi, utilisateur=moi, m2=surface,
                    quartier='Croix-Rousse', commentaire=commentaire)
                DeclarationM2.objects.filter(pk=declaration.pk).update(
                    date_declaration=timezone.now() - timedelta(days=jours))
        # Répartition qui reproduit les cartes de la maquette (128 / 119 / 94).
        volumes = {'Croix-Rousse': 123.2, 'Guillotière': 119.0, 'Vaise': 94.0}
        for quartier, total in volumes.items():
            comptes = [c for c, _ in amies if jeu.profil_de(c).quartier == quartier]
            if not comptes:
                continue
            part = total / len(comptes)
            for compte in comptes:
                ContributionDefiVille.objects.update_or_create(
                    defi=defi, utilisateur=compte,
                    defaults={'quartier': quartier, 'm2': round(part, 1)},
                )

    # ── Salons ─────────────────────────────────────────────────────────────
    def _salons(self, moi, amies):
        par_nom = {c.username: c for c, _ in amies}

        salon, cree = Salon.objects.update_or_create(
            nom='Denim Croix-Rousse',
            defaults={'type_salon': 'quartier', 'motif': 'denim',
                      'description': 'Le salon des amatrices de denim du 4ᵉ',
                      'defi_titre': 'Défi coop du salon',
                      'defi_objectif_m2': 40, 'defi_avance_m2': 27.5,
                      'defi_echeance': timezone.localdate() + timedelta(days=3)},
        )
        salon.membres.add(moi, *[c for c, _ in amies])

        if not salon.messages.exists():
            sofia, lea = par_nom.get('sofia.d'), par_nom.get('lea.p')
            if sofia:
                premier = MessageSalon.objects.create(
                    salon=salon, auteur=sofia,
                    contenu="J'ai doublé la poche arrière, ça tient nickel avec du fil 40.")
                # Quelques réactions déjà posées : le fil vide ne montrerait
                # pas à quoi servent les pastilles.
                for compte, emoji in ((moi, '❤️'), (lea, '🔥'), (sofia, '💡')):
                    if compte:
                        ReactionMessage.objects.get_or_create(
                            message=premier, utilisateur=compte, emoji=emoji)
                MessageSalon.objects.create(
                    salon=salon, auteur=sofia, type_message='photos',
                    motifs='denim,laine')
            MessageSalon.objects.create(
                salon=salon, auteur=moi,
                contenu="Ah super, je vais tenter ça sur ma trousse ce soir.")
            if lea:
                annonce = AnnonceTroc.objects.create(
                    auteur=lea, titre='1,4 m² de velours vert à donner',
                    sens='donne', surface_m2=1.4, distance_m=800, motif='vert')
                MessageSalon.objects.create(
                    salon=salon, auteur=lea, type_message='troc', annonce=annonce,
                    contenu=annonce.titre)

        sos, _ = Salon.objects.update_or_create(
            nom='Salon SOS en direct',
            defaults={'type_salon': 'sos', 'motif': 'lin',
                      'description': 'Réponses immédiates, à toute heure'},
        )
        sos.membres.add(moi, *[c for c, _ in amies])

    # ── Événements ─────────────────────────────────────────────────────────
    def _evenements(self, moi, amies):
        par_nom = {c.username: c for c, _ in amies}
        aujourdhui = timezone.localdate()

        live, _ = EvenementCommunaute.objects.update_or_create(
            titre='Live : poser une fermeture',
            defaults={'format_evenement': 'en_ligne',
                      'date_evenement': aujourdhui + timedelta(days=2),
                      'heure_debut': '19h', 'heure_fin': '19h45',
                      'duree': '45 min', 'xp_gain': 30, 'motif': 'denim',
                      'animatrice': par_nom.get('noor.k'),
                      'accroche': '45 min · en direct',
                      'description': "Une heure pour dompter la fermeture éclair, "
                                     "de la pose du pied presseur à la finition."},
        )

        repair, _ = EvenementCommunaute.objects.update_or_create(
            titre='Repair café du quartier',
            defaults={'format_evenement': 'presentiel',
                      'date_evenement': aujourdhui + timedelta(days=8),
                      'heure_debut': '14h', 'heure_fin': '18h',
                      'lieu': 'MJC Croix-Rousse', 'adresse': '12 rue des Pierres Plantées',
                      'distance_km': 1.2, 'machines_dispo': 12, 'xp_gain': 50,
                      'motif': 'denim', 'accroche': '12 machines · surjeteuse dispo',
                      'description': "Quatre heures d'atelier ouvert dans la cour de la MJC. "
                                     "Surjeteuse, machine à boutonnière et deux couturiers "
                                     "confirmés sur place. Apporte tes pièces à réparer et "
                                     "de quoi grignoter."},
        )

        EvenementCommunaute.objects.update_or_create(
            titre='48 h zéro chute',
            defaults={'format_evenement': 'marathon',
                      'date_evenement': aujourdhui + timedelta(days=15),
                      'heure_debut': '', 'heure_fin': '',
                      'xp_gain': 120, 'motif': 'toile',
                      'accroche': 'Défi collectif · toute la ville',
                      'description': '500 m² recousus en un week-end. Équipes de 4.'},
        )

        for evenement, comptes in ((live, [c for c, _ in amies]),
                                   (repair, [c for c, _ in amies][:9])):
            for compte in comptes:
                InscriptionEvenement.objects.get_or_create(
                    utilisateur=compte, evenement=evenement)

    # ── Entraide ───────────────────────────────────────────────────────────
    def _entraide(self, moi, amies):
        par_nom = {c.username: c for c, _ in amies}

        if not QuestionEntraide.objects.exists():
            amine = par_nom.get('amine.r')
            if amine:
                QuestionEntraide.objects.create(
                    auteur=amine, tags='denim,machine', xp_gain=15,
                    contenu="Mon fil casse à chaque passage sur l'ourlet du jean. Une idée ?")

            maya = par_nom.get('maya.j')
            if maya:
                question = QuestionEntraide.objects.create(
                    auteur=maya, tags='jersey', motif='lin', resolue=True,
                    contenu='Comment rattraper une couture qui gondole sur du jersey ?')
                sofia = par_nom.get('sofia.d')
                if sofia:
                    ReponseEntraide.objects.create(
                        question=question, auteur=sofia, validee=True, coeurs=18,
                        contenu='Aiguille jersey 80 et point zigzag très serré, sans tirer le tissu.')

            chloe = par_nom.get('chloe.v')
            if chloe:
                QuestionEntraide.objects.create(
                    auteur=chloe, tags='coton', motif='laine',
                    contenu='Ce coton est-il assez solide pour un tote ?')

        for identifiant, specialites in [('sofia.d', 'Denim, fermetures'),
                                         ('lea.p', 'Jersey, surjeteuse'),
                                         ('thomas.b', 'Patrons, coupe')]:
            compte = par_nom.get(identifiant)
            if compte:
                DisponibiliteEntraide.objects.update_or_create(
                    utilisateur=compte,
                    defaults={'specialites': specialites, 'en_ligne': True})

    def _troc(self, amies):
        par_nom = {c.username: c for c, _ in amies}
        lea, thomas = par_nom.get('lea.p'), par_nom.get('thomas.b')
        if lea and not AnnonceTroc.objects.filter(auteur=lea, sens='donne').exists():
            AnnonceTroc.objects.create(
                auteur=lea, titre='1,4 m² de velours côtelé vert à donner',
                sens='donne', surface_m2=1.4, distance_m=800, motif='vert')
        if thomas and not AnnonceTroc.objects.filter(auteur=thomas).exists():
            AnnonceTroc.objects.create(
                auteur=thomas, titre='du denim brut', sens='cherche',
                surface_m2=0.6, distance_m=1400, motif='denim')

    def _transactions(self, moi):
        if TransactionPieces.objects.filter(utilisateur=moi).exists():
            return
        maintenant = timezone.now()
        for libelle, montant, icone, jours in [
            ('Gel de série ×1', -40, 'gel', 3),
            ('Patron sac banane', -90, 'patron', 9),
            ('Quête : analyser un vêtement', 20, 'piece', 1),
            ('Coffre du jour', 30, 'coffre', 2),
        ]:
            transaction_obj = TransactionPieces.objects.create(
                utilisateur=moi, libelle=libelle, montant=montant, icone=icone)
            TransactionPieces.objects.filter(pk=transaction_obj.pk).update(
                date_transaction=maintenant - timedelta(days=jours))
