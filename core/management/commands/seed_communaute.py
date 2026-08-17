"""Peuple la communauté « atelier » : saison, ligue, écussons, quêtes,
boutique, amitiés, salons et conversations, duels, défi de ville, agenda,
entraide, troc, notifications.

    python manage.py seed_communaute --user testdesign   # une joueuse précise
    python manage.py seed_communaute --tous              # tous les vrais comptes
    python manage.py seed_communaute                     # le premier compte trouvé

Idempotent : relancer la commande met à jour l'existant sans doublonner. C'est
ce qui permet de l'appeler à chaque déploiement (`build.sh`) sans rien casser.
``--reset`` efface d'abord les contenus de démonstration — à réserver au
local : en ligne, il emporterait les vraies conversations.

Le monde de démonstration (comptes voisins, saison, salons publics, agenda,
entraide, troc) est commun à tout le monde ; seul le *rattachement* — amitiés,
inscription à la ligue, duel, appartenance aux salons — est propre à chaque
joueuse. D'où la séparation `_monde()` / `_rattacher(compte)`.
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

# ── Couturières et couturiers de démonstration ──────────────────────────────
# (identifiant, prénom, nom, XP de saison, série, quartier, arrondissement,
#  teinte du jeton, ligue). Les XP dessinent un classement crédible : un écart
# resserré en haut, puis une longue traîne.
AMIES = [
    ('sofia.d',   'Sofia',   'Delcourt',  1240, 21, 'Croix-Rousse', 'Lyon 1ᵉʳ', 't-or',     'or'),
    ('lea.p',     'Léa',     'Pontier',   1105,  9, 'Croix-Rousse', 'Lyon 4ᵉ',  't-vert',   'or'),
    ('thomas.b',  'Thomas',  'Berger',    1020,  4, 'Guillotière',  'Lyon 7ᵉ',  't-violet', 'or'),
    ('noor.k',    'Noor',    'Khalil',     960,  6, 'Vaise',        'Lyon 9ᵉ',  't-corail', 'or'),
    ('amine.r',   'Amine',   'Rachid',     880,  0, 'Guillotière',  'Lyon 7ᵉ',  't-or',     'or'),
    ('maya.j',    'Maya',    'Jourdan',    815,  3, 'Croix-Rousse', 'Lyon 4ᵉ',  't-vert',   'or'),
    ('chloe.v',   'Chloé',   'Vasseur',    780,  2, 'Vaise',        'Lyon 9ᵉ',  't-violet', 'or'),
    ('ines.b',    'Inès',    'Baroud',     742,  1, 'Guillotière',  'Lyon 3ᵉ',  't-corail', 'or'),
    ('hugo.m',    'Hugo',    'Marchand',   688, 11, 'Part-Dieu',    'Lyon 3ᵉ',  't-vert',   'or'),
    ('yasmine.t', 'Yasmine', 'Tazi',       640,  5, 'Croix-Rousse', 'Lyon 1ᵉʳ', 't-or',     'or'),
    ('paul.g',    'Paul',    'Gauthier',   594,  0, 'Vaise',        'Lyon 9ᵉ',  't-violet', 'or'),
    ('sarah.l',   'Sarah',   'Lemoine',    530,  7, 'Part-Dieu',    'Lyon 6ᵉ',  't-corail', 'or'),
    ('elias.n',   'Élias',   'Nguyen',     468,  2, 'Guillotière',  'Lyon 7ᵉ',  't-vert',   'or'),
    ('camille.r', 'Camille', 'Roux',       402,  0, 'Croix-Rousse', 'Lyon 4ᵉ',  't-or',     'or'),
    # Deux comptes en ligue supérieure : le classement n'est pas le monde entier.
    ('julie.f',   'Julie',   'Ferrand',   2140, 34, 'Presqu\'île',  'Lyon 2ᵉ',  't-or',     'platine'),
    ('karim.b',   'Karim',   'Belaïd',    1980, 28, 'Part-Dieu',    'Lyon 6ᵉ',  't-violet', 'platine'),
]

# Amitiés scellées d'office, invitations laissées en attente, et le reste :
# des « personnes autour » qu'on peut découvrir et ajouter.
AMIES_ACCEPTEES = {'sofia.d', 'lea.p', 'thomas.b', 'noor.k', 'amine.r',
                   'maya.j', 'hugo.m', 'yasmine.t'}
AMIES_EN_ATTENTE = {'chloe.v', 'ines.b'}

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
     'jour', 1, 15, 0, 1, 'Ouvrir un salon', 'communaute_salons'),
    ('etape-projet', 'Terminer une étape de projet', 'Reprends là où tu en étais',
     'jour', 1, 40, 0, 2, 'Reprendre le projet', 'patrons'),
    ('aider-couturiere', 'Aider 3 couturiers', 'Réponds à trois questions',
     'semaine', 3, 0, 80, 0, 'Voir les questions', 'communaute'),
]


class Command(BaseCommand):
    help = "Peuple la communauté « atelier » (saison, ligue, salons, duels, agenda…)."

    def add_arguments(self, parser):
        parser.add_argument('--user', default=None,
                            help="Identifiant de la joueuse principale.")
        parser.add_argument('--tous', action='store_true',
                            help="Rattache TOUS les comptes réels au monde de démonstration "
                                 "(mode déploiement).")
        parser.add_argument('--reset', action='store_true',
                            help="Efface les contenus de démonstration avant de recréer. "
                                 "À ne pas utiliser en ligne.")

    @transaction.atomic
    def handle(self, *args, **options):
        if options['reset']:
            self._reset()

        # ── Le monde, commun à tout le monde ──
        self.ecussons = self._ecussons()
        self.saison = self._saison()
        self._paliers(self.saison, self.ecussons)
        self._quetes()
        self._boutique(self.ecussons)
        self.amies = self._amies()
        self.defi = self._defi_ville()
        self.evenements = self._evenements()
        self._entraide()
        self._troc()
        self._duels_entre_voisins()
        self._salons_publics()

        # ── Puis chaque joueuse est rattachée à ce monde ──
        for compte in self._joueuses(options):
            self._rattacher(compte)
            self.stdout.write(f"  rattachée : {compte.username}")

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
    def _joueuses(self, options):
        """Comptes à rattacher au monde de démonstration.

        `--tous` vise tous les comptes réels — c'est le mode du déploiement :
        personne ne doit tomber sur une communauté vide à la première visite.
        """
        demo = {identifiant for identifiant, *_ in AMIES}

        if options['user']:
            return [Utilisateur.objects.get(username=options['user'])]

        # Les comptes d'administration restent hors du jeu, comme dans le
        # classement : ils gonfleraient la ligue avec des lignes fantômes.
        reels = (Utilisateur.objects
                 .exclude(username__in=demo)
                 .exclude(is_superuser=True)
                 .exclude(is_staff=True)
                 .order_by('pk'))
        if options['tous']:
            return list(reels)

        joueuse = reels.first() or Utilisateur.objects.order_by('pk').first()
        if not joueuse:
            raise SystemExit("Aucun compte en base : crée d'abord un utilisateur.")
        return [joueuse]

    def _amies(self):
        """Les comptes voisins, créés ou remis à jour. Retourne un dict par
        identifiant — tout le reste du peuplement s'y réfère par son nom."""
        comptes = {}
        for (identifiant, prenom, nom, xp, serie, quartier,
             arrondissement, teinte, ligue) in AMIES:
            compte, cree = Utilisateur.objects.get_or_create(
                username=identifiant,
                defaults={'first_name': prenom, 'last_name': nom,
                          'email': f"{identifiant}@exemple.fr", 'email_verifie': True},
            )
            if cree:
                # Comptes de décor : aucune connexion possible.
                compte.set_unusable_password()
                compte.first_name, compte.last_name = prenom, nom
                compte.soldePieces = 120
                compte.save()

            profil = jeu.profil_de(compte)
            profil.serie_actuelle = serie
            profil.serie_record = max(serie + 3, profil.serie_record)
            profil.ville = 'Lyon'
            profil.quartier = quartier
            profil.arrondissement = arrondissement
            profil.teinte = teinte
            profil.derniere_activite = timezone.localdate() if serie else None
            profil.xp_total = xp + 2400
            profil.save()

            if self.saison:
                ParticipationLigue.objects.update_or_create(
                    utilisateur=compte, saison=self.saison,
                    defaults={'ligue': ligue, 'xp_saison': xp,
                              'pieces_finies': max(2, xp // 220),
                              'm2_sauves': round(xp / 260, 1)},
                )
            comptes[identifiant] = compte
        return comptes

    # ── Rattachement d'une joueuse au monde ────────────────────────────────
    def _rattacher(self, moi):
        self._profil_joueuse(moi)
        self._ligue(moi)
        self._ecussons_obtenus(moi)
        self._amities(moi)
        self._duel_en_cours(moi)
        self._duel_termine(moi)
        self._contribution_defi(moi)
        self._salons_de(moi)
        self._inscriptions(moi)
        self._transactions(moi)
        self._notifications(moi)

    def _profil_joueuse(self, moi):
        """Donne un état de départ crédible — sans écraser ce qui existe déjà.

        En ligne, la commande passe sur de vrais comptes : une série ou un
        solde gagnés pour de bon ne doivent pas être remplacés par du décor.
        """
        if not moi.first_name:
            moi.first_name, moi.last_name = 'Camille', 'Moreau'
            moi.save(update_fields=['first_name', 'last_name'])

        profil = jeu.profil_de(moi)
        # Le niveau ne vient PAS d'ici : il se calcule sur les CP d'atelier
        # (tissus, étapes, projets). `xp_total` reste le cumul d'XP gagnée,
        # que seule la ligue exploite.
        profil.xp_total = max(profil.xp_total, 3740)
        profil.serie_actuelle = max(profil.serie_actuelle, 12)
        profil.serie_record = max(profil.serie_record, 19)
        profil.gels = max(profil.gels, 2)
        profil.ville = profil.ville or 'Lyon'
        profil.quartier = profil.quartier or 'Croix-Rousse'
        profil.arrondissement = profil.arrondissement or 'Lyon 4ᵉ'
        profil.teinte = profil.teinte or 't-violet'
        profil.derniere_activite = timezone.localdate()

        # Calendrier de la semaine : les jours écoulés sont faits, sauf mercredi.
        aujourdhui = timezone.localdate()
        faits = [j for j in range(aujourdhui.weekday()) if j != 2]
        profil.jours_semaine = ','.join(str(j) for j in faits)
        profil.semaine_cle = jeu._cle_semaine(aujourdhui)
        profil.save()

        if moi.soldePieces < 100:
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

        recompenses = [
            ('Coffre de 15 pièces', 'Bienvenue dans la saison', 15, 0, None, None),
            ('Écusson « premier ourlet »', 'Écusson « premier ourlet »', 0, 0, None, ecussons.get('denim')),
            ('Coffre de 40 pièces', '+ patron « sac banane »', 40, 0, patron, None),
            ('Un gel de série de plus', 'Un gel de série de plus', 0, 1, None, None),
            ('Coffre de 90 pièces', 'Le grand coffre de fin', 90, 0, None, ecussons.get('ruban')),
        ]
        seuils = [seuil for seuil, _ in jeu.NIVEAUX_ATELIER[1:]]

        for numero, (seuil, lot) in enumerate(zip(seuils, recompenses), start=1):
            titre, detail, pieces, gels, patron_lie, ecusson = lot
            PalierSaison.objects.update_or_create(
                saison=saison, numero=numero,
                defaults={'points_requis': seuil, 'titre': titre, 'detail': detail,
                          'pieces': pieces, 'gels': gels,
                          'patron': patron_lie, 'ecusson': ecusson},
            )

    def _ligue(self, moi):
        """Inscrit la joueuse en ligue Or, dans le haut du peloton.

        Le score est dérivé de la clé du compte plutôt que fixé : en mode
        `--tous`, un score unique mettrait tous les comptes réels à égalité, et
        le classement afficherait une colonne de valeurs identiques.
        """
        xp = 1180 - (moi.pk * 53) % 300
        participation, cree = ParticipationLigue.objects.get_or_create(
            utilisateur=moi, saison=self.saison,
            defaults={'ligue': 'or', 'xp_saison': xp,
                      'pieces_finies': 6, 'm2_sauves': 4.8},
        )
        # La commande est rejouée à chaque déploiement : un `update` écraserait
        # l'XP réellement gagnée depuis. On ne fait que relever un plancher.
        if not cree and participation.xp_saison < xp:
            participation.xp_saison = xp
            participation.save(update_fields=['xp_saison'])

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

        # Écussons encore secrets, affichés « ? » sur l'écran de collection.
        for code, nom in [('secret-1', 'Secret'), ('secret-2', '?')]:
            ecusson, _ = Ecusson.objects.update_or_create(
                code=code,
                defaults={'nom': nom, 'categorie': 'defis', 'rang': 'toile',
                          'secret': True, 'ordre': 90, 'icone': 'etoile',
                          'condition': '', 'couleur_haut': '#EDE4D6', 'couleur_bas': '#B0A493'},
            )
            catalogue[code] = ecusson

        ecusson, _ = Ecusson.objects.update_or_create(
            code='verrouille-1',
            defaults={'nom': 'Verrouillé', 'categorie': 'defis', 'rang': 'toile',
                      'condition': '80 XP', 'ordre': 95, 'icone': 'cadenas',
                      'couleur_haut': '#EDE4D6', 'couleur_bas': '#B0A493'},
        )
        catalogue['verrouille-1'] = ecusson

        saison, _ = Ecusson.objects.update_or_create(
            code='saison-03',
            defaults={'nom': 'Saison 03', 'categorie': 'defis', 'rang': 'or',
                      'condition': 'Saison 03', 'icone': 'etoile', 'ordre': 50,
                      'couleur_haut': '#FFF3C4', 'couleur_bas': '#D9930F',
                      'description': "Cousu sur ta carte d'atelier."},
        )
        catalogue['saison-03'] = saison
        return catalogue

    def _ecussons_obtenus(self, moi):
        # Le diamant et les secrets restent à décrocher : la collection doit
        # montrer des cases vides, pas un sans-faute.
        for code in ('toile', 'denim', 'laine', 'braise-or', 'eclair',
                     'etoile', 'ruban', 'bobine', 'mentor'):
            if code in self.ecussons:
                EcussonObtenu.objects.get_or_create(
                    utilisateur=moi, ecusson=self.ecussons[code])

        # Les voisines aussi en portent : un profil visité doit avoir sa vitrine.
        vitrines = {
            'sofia.d': ('toile', 'denim', 'braise-or', 'mentor', 'ruban'),
            'lea.p': ('toile', 'laine', 'bobine'),
            'thomas.b': ('denim', 'eclair'),
            'noor.k': ('toile', 'etoile', 'mentor'),
            'julie.f': ('toile', 'denim', 'laine', 'braise-or', 'ruban', 'diamant'),
        }
        for identifiant, codes in vitrines.items():
            compte = self.amies.get(identifiant)
            if not compte:
                continue
            for code in codes:
                if code in self.ecussons:
                    EcussonObtenu.objects.get_or_create(
                        utilisateur=compte, ecusson=self.ecussons[code])

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
    def _amities(self, moi):
        """Huit amitiés scellées, deux invitations laissées en attente, et le
        reste des comptes laissé à découvrir dans « Trouver des amies »."""
        for identifiant, compte in self.amies.items():
            if compte.pk == moi.pk:
                continue
            if identifiant in AMIES_ACCEPTEES:
                Amitie.objects.get_or_create(de=moi, vers=compte,
                                             defaults={'acceptee': True})
            elif identifiant in AMIES_EN_ATTENTE:
                # Invitation reçue : c'est le voisin qui a invité la joueuse.
                Amitie.objects.get_or_create(de=compte, vers=moi,
                                             defaults={'acceptee': False})

        # Les voisins sont aussi amis entre eux : sans cela, leurs profils
        # afficheraient tous « 0 ami ».
        entre_voisins = [
            ('sofia.d', 'lea.p'), ('sofia.d', 'noor.k'), ('sofia.d', 'maya.j'),
            ('lea.p', 'thomas.b'), ('lea.p', 'yasmine.t'), ('thomas.b', 'amine.r'),
            ('noor.k', 'hugo.m'), ('maya.j', 'chloe.v'), ('amine.r', 'elias.n'),
            ('hugo.m', 'sarah.l'), ('yasmine.t', 'ines.b'), ('paul.g', 'camille.r'),
        ]
        for un, autre in entre_voisins:
            a, b = self.amies.get(un), self.amies.get(autre)
            if a and b:
                Amitie.objects.get_or_create(de=a, vers=b, defaults={'acceptee': True})

    def _notifications(self, moi):
        """Quelques notifications d'exemple, si la boîte est vide."""
        if Notification.objects.filter(destinataire=moi).exists():
            return
        maintenant = timezone.now()

        lignes = [
            ('salon', "Sofia t'a citée dans « Denim Croix-Rousse »",
             'Tu avais bien un reste de toile écrue ?', '/communaute/salons/', 'sofia.d', 12),
            ('amitie_demande', "Chloé veut t'ajouter", 'Accepte pour comparer vos semaines.',
             '/communaute/amies/', 'chloe.v', 40),
            ('duel', "Noor t'a défié", '18 h pour coudre le plus de pièces.',
             None, 'noor.k', 180),
            ('coffre', 'Coffre du jour débloqué', 'Toutes tes quêtes sont faites · 30 pièces.',
             '/communaute/quetes/', None, 420),
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
                emetteur=self.amies.get(auteur), lue=minutes > 1000,
            )
            Notification.objects.filter(pk=notification.pk).update(
                date_creation=maintenant - timedelta(minutes=minutes))

    # ── Duels ──────────────────────────────────────────────────────────────
    def _duel_en_cours(self, moi):
        noor = self.amies.get('noor.k')
        if not noor:
            return
        duel, cree = Duel.objects.get_or_create(
            joueuse_a=moi, joueuse_b=noor, statut='en_cours',
            defaults={'score_a': 3, 'score_b': 2, 'mise_pieces': 20, 'xp_gain': 60,
                      'date_fin': timezone.now() + timedelta(hours=18)},
        )
        if cree:
            for compte, titre, surface, motif in [
                (moi, 'Trousse en denim', 0.4, 'denim'),
                (noor, 'Coussin en lin', 0.7, 'lin'),
                (moi, 'Tote bag rayé', 1.1, 'toile'),
                (noor, 'Chouchous ×3', 0.2, 'vert'),
                (moi, 'Housse de coussin', 0.6, 'laine'),
            ]:
                PieceDuel.objects.create(duel=duel, utilisateur=compte,
                                         titre=titre, surface_m2=surface, motif=motif)

    def _duel_termine(self, moi):
        """Un duel déjà joué : l'historique ne doit pas être vide."""
        thomas = self.amies.get('thomas.b')
        if not thomas:
            return
        duel, cree = Duel.objects.get_or_create(
            joueuse_a=moi, joueuse_b=thomas, statut='termine',
            defaults={'score_a': 5, 'score_b': 4, 'mise_pieces': 20, 'xp_gain': 60,
                      'date_fin': timezone.now() - timedelta(days=3)},
        )
        if cree:
            Duel.objects.filter(pk=duel.pk).update(
                date_debut=timezone.now() - timedelta(days=4))
            for compte, titre, surface, motif in [
                (moi, 'Sac à vrac ×2', 0.5, 'toile'),
                (thomas, 'Tablier', 0.9, 'lin'),
                (moi, 'Bandeau', 0.1, 'vert'),
            ]:
                PieceDuel.objects.create(duel=duel, utilisateur=compte,
                                         titre=titre, surface_m2=surface, motif=motif)

    def _duels_entre_voisins(self):
        """Des duels auxquels la joueuse ne participe pas : le quartier vit
        sans elle, et les profils visités ont un duel à montrer."""
        paires = [('sofia.d', 'lea.p', 4, 6, 'en_cours'),
                  ('maya.j', 'amine.r', 2, 2, 'en_cours'),
                  ('hugo.m', 'yasmine.t', 7, 3, 'termine')]
        for un, autre, score_a, score_b, statut in paires:
            a, b = self.amies.get(un), self.amies.get(autre)
            if not (a and b):
                continue
            fin = (timezone.now() + timedelta(hours=9) if statut == 'en_cours'
                   else timezone.now() - timedelta(days=2))
            Duel.objects.get_or_create(
                joueuse_a=a, joueuse_b=b, statut=statut,
                defaults={'score_a': score_a, 'score_b': score_b,
                          'mise_pieces': 20, 'xp_gain': 60, 'date_fin': fin},
            )

    # ── Défi de ville ──────────────────────────────────────────────────────
    def _defi_ville(self):
        defi, _ = DefiVille.objects.update_or_create(
            ville='Lyon',
            defaults={'titre': '500 m² recousus avant la fin du mois',
                      'objectif_m2': 500, 'actif': True,
                      'date_fin': timezone.localdate() + timedelta(days=6)},
        )

        # Chaque voisin contribue selon son quartier : c'est ce qui fait le
        # classement des quartiers de l'écran de défi.
        # Total visé ≈ 340 m² sur 500 : le défi doit être en cours, ni au point
        # mort ni déjà gagné — c'est là qu'il donne envie de déclarer ses m².
        volumes = {'Croix-Rousse': 96.4, 'Guillotière': 84.0,
                   'Vaise': 71.5, 'Part-Dieu': 52.3, 'Presqu\'île': 28.6}
        par_quartier = {}
        for compte in self.amies.values():
            quartier = jeu.profil_de(compte).quartier
            par_quartier.setdefault(quartier, []).append(compte)

        for quartier, comptes in par_quartier.items():
            total = volumes.get(quartier, 40.0)
            # Un dégradé : la première contributrice pèse plus lourd. Les poids
            # sont normalisés, sinon le total du quartier dériverait.
            poids = [1.4 if rang == 0 else (0.8 if rang > 2 else 1.0)
                     for rang in range(len(comptes))]
            somme = sum(poids)
            for compte, part in zip(comptes, poids):
                ContributionDefiVille.objects.update_or_create(
                    defi=defi, utilisateur=compte,
                    defaults={'quartier': quartier, 'm2': round(total * part / somme, 1)},
                )
        return defi

    def _contribution_defi(self, moi):
        profil = jeu.profil_de(moi)
        # Même prudence que pour la ligue : les m² déclarés pour de vrai ne
        # doivent pas être ramenés à la valeur de démonstration.
        ContributionDefiVille.objects.get_or_create(
            defi=self.defi, utilisateur=moi,
            defaults={'quartier': profil.quartier, 'm2': 4.8},
        )
        # Journal correspondant : le cumul ci-dessus doit être justifiable.
        if not DeclarationM2.objects.filter(defi=self.defi, utilisateur=moi).exists():
            for surface, commentaire, jours in [
                (1.1, 'Tote bag rayé', 1),
                (0.4, 'Trousse en denim', 4),
                (2.3, 'Rideau recoupé', 9),
                (1.0, 'Coussin en lin', 14),
            ]:
                declaration = DeclarationM2.objects.create(
                    defi=self.defi, utilisateur=moi, m2=surface,
                    quartier=profil.quartier, commentaire=commentaire)
                DeclarationM2.objects.filter(pk=declaration.pk).update(
                    date_declaration=timezone.now() - timedelta(days=jours))

    # ── Salons et conversations ────────────────────────────────────────────
    def _message(self, salon, auteur, contenu='', minutes=0, type_message='texte',
                 piece=None, motifs='', reactions=()):
        """Un message daté, avec sa pièce jointe et ses réactions.

        Les messages sont posés à rebours (`minutes` avant maintenant) pour que
        le fil se lise dans un ordre plausible plutôt que d'être tout entier
        horodaté à la seconde du peuplement.
        """
        champ = {
            'patron': 'patron', 'etape': 'etape', 'tissu': 'vetement',
            'defi_ville': 'defi_ville', 'duel': 'duel', 'troc': 'annonce',
            'evenement': 'evenement', 'ecusson': 'ecusson',
        }.get(type_message)
        if champ and piece is None:
            # Pièce absente de cette base : le message vaut mieux en texte seul
            # qu'en carte vide.
            type_message = 'texte'
            champ = None

        message = MessageSalon(salon=salon, auteur=auteur, contenu=contenu,
                               type_message=type_message, motifs=motifs)
        if champ:
            setattr(message, champ, piece)
        message.save()
        MessageSalon.objects.filter(pk=message.pk).update(
            date_envoi=timezone.now() - timedelta(minutes=minutes))

        for identifiant, emoji in reactions:
            compte = self.amies.get(identifiant)
            if compte:
                ReactionMessage.objects.get_or_create(
                    message=message, utilisateur=compte, emoji=emoji)
        return message

    def _salons_publics(self):
        """Trois salons ouverts, avec de vraies conversations."""
        aide = self.amies
        patron = Patron.objects.order_by('pk').first()
        etape = patron.etapes.order_by('numero').first() if patron else None
        evenement = self.evenements.get('repair')
        ecusson = self.ecussons.get('braise-or')

        # ── Salon de quartier ──
        quartier, _ = Salon.objects.update_or_create(
            nom='Denim Croix-Rousse',
            defaults={'type_salon': 'quartier', 'motif': 'denim',
                      'description': 'Le salon des amateurs de denim du 4ᵉ',
                      'defi_titre': 'Défi coop du salon',
                      'defi_objectif_m2': 40, 'defi_avance_m2': 27.5,
                      'defi_echeance': timezone.localdate() + timedelta(days=3)},
        )
        quartier.membres.add(*[c for c in aide.values()][:10])
        if not quartier.messages.exists():
            self._message(quartier, aide['sofia.d'], minutes=320,
                          contenu="J'ai doublé la poche arrière, ça tient nickel avec du fil 40.",
                          reactions=[('lea.p', '🔥'), ('maya.j', '👏'), ('hugo.m', '❤️')])
            self._message(quartier, aide['sofia.d'], minutes=318,
                          type_message='photos', motifs='denim,laine')
            self._message(quartier, aide['lea.p'], minutes=300,
                          contenu="@Sofia tu prends quelle longueur de point pour la surpiqûre ?")
            self._message(quartier, aide['sofia.d'], minutes=294,
                          contenu="3,5 mm, et je ralentis à fond dans les épaisseurs.",
                          reactions=[('lea.p', '💡')])
            self._message(quartier, aide['thomas.b'], minutes=210,
                          contenu="Je me lance sur celui-ci ce week-end, quelqu'un l'a déjà fait ?",
                          type_message='patron', piece=patron,
                          reactions=[('noor.k', '🔥'), ('maya.j', '❤️')])
            self._message(quartier, aide['noor.k'], minutes=150,
                          contenu="Moi ! L'étape des angles m'a pris deux soirées.",
                          type_message='etape', piece=etape)
            self._message(quartier, aide['maya.j'], minutes=64,
                          contenu="On en est où du défi coop ? Il me reste 2 m² de toile.",
                          reactions=[('hugo.m', '👏')])
            self._message(quartier, aide['hugo.m'], minutes=30,
                          contenu="27,5 m² sur 40. Faisable avant mercredi si on s'y met.",
                          type_message='defi_ville', piece=self.defi)

        # ── Salon SOS ──
        sos, _ = Salon.objects.update_or_create(
            nom='Salon SOS en direct',
            defaults={'type_salon': 'sos', 'motif': 'lin',
                      'description': 'Réponses immédiates, à toute heure'},
        )
        sos.membres.add(*aide.values())
        if not sos.messages.exists():
            self._message(sos, aide['amine.r'], minutes=52,
                          contenu="SOS : ma canette fait des boucles sous le tissu, "
                                  "j'ai déjà renfilé deux fois.")
            self._message(sos, aide['lea.p'], minutes=48,
                          contenu="Neuf fois sur dix c'est le fil supérieur mal engagé "
                                  "dans les disques de tension. Refais-le pied relevé.",
                          reactions=[('amine.r', '💡'), ('sofia.d', '👏')])
            self._message(sos, aide['amine.r'], minutes=41,
                          contenu="C'était ça. Merci !", reactions=[('lea.p', '❤️')])
            self._message(sos, aide['elias.n'], minutes=16,
                          contenu="Quelqu'un a une astuce pour couper du velours "
                                  "sans que ça glisse ?")

        # ── Salon thématique ──
        theme, _ = Salon.objects.update_or_create(
            nom='Zéro déchet Lyon',
            defaults={'type_salon': 'theme', 'motif': 'vert',
                      'description': 'Chutes, restes et récup : rien ne se perd',
                      'defi_titre': 'Zéro chute du mois',
                      'defi_objectif_m2': 25, 'defi_avance_m2': 9.5,
                      'defi_echeance': timezone.localdate() + timedelta(days=11)},
        )
        theme.membres.add(*[c for c in aide.values()][:8])
        if not theme.messages.exists():
            self._message(theme, aide['yasmine.t'], minutes=1440,
                          contenu="Je garde toutes mes chutes de moins de 10 cm "
                                  "pour du patchwork. Qui fait pareil ?")
            self._message(theme, aide['sarah.l'], minutes=1380,
                          contenu="Moi je bourre des coussins avec. Zéro poubelle depuis mars.",
                          reactions=[('yasmine.t', '👏'), ('paul.g', '🔥')])
            self._message(theme, aide['paul.g'], minutes=420,
                          contenu="Le repair café serait l'occasion d'échanger nos bacs à chutes.",
                          type_message='evenement', piece=evenement,
                          reactions=[('sarah.l', '❤️')])
            self._message(theme, aide['sofia.d'], minutes=95,
                          contenu="Décroché après 30 jours d'affilée 🔥",
                          type_message='ecusson', piece=ecusson,
                          reactions=[('yasmine.t', '👏'), ('lea.p', '🔥'), ('paul.g', '👏')])

    def _salons_de(self, moi):
        """Rattache la joueuse aux salons publics, et lui ouvre un salon privé."""
        for salon in Salon.objects.filter(type_salon__in=('quartier', 'sos', 'theme')):
            salon.membres.add(moi)

        prive, cree = Salon.objects.get_or_create(
            nom='Les cousettes du mardi', createur=moi,
            defaults={'type_salon': 'prive', 'motif': 'laine',
                      'description': 'Le petit groupe du mardi soir'},
        )
        invitees = [self.amies[i] for i in ('sofia.d', 'lea.p', 'maya.j')
                    if i in self.amies]
        prive.membres.add(moi, *invitees)

        if cree and invitees:
            annonce = AnnonceTroc.objects.filter(sens='donne').first()
            self._message(prive, invitees[0], minutes=210,
                          contenu="Mardi 20 h chez moi, j'ai la surjeteuse !",
                          reactions=[('maya.j', '❤️'), ('lea.p', '👏')])
            self._message(prive, moi, minutes=180,
                          contenu="Parfait. J'apporte du café et mes chutes de denim.")
            self._message(prive, invitees[1], minutes=140,
                          contenu="Je ramène ça si quelqu'un en veut.",
                          type_message='troc', piece=annonce)
            self._message(prive, invitees[2], minutes=25,
                          contenu="À mardi alors 🪡", reactions=[('sofia.d', '🔥')])

    # ── Agenda ─────────────────────────────────────────────────────────────
    def _evenements(self):
        aujourdhui = timezone.localdate()
        agenda = {}

        agenda['live'], _ = EvenementCommunaute.objects.update_or_create(
            titre='Live : poser une fermeture',
            defaults={'format_evenement': 'en_ligne',
                      'date_evenement': aujourdhui + timedelta(days=2),
                      'heure_debut': '19h', 'heure_fin': '19h45',
                      'duree': '45 min', 'xp_gain': 30, 'motif': 'denim',
                      'animatrice': self.amies.get('noor.k'),
                      'accroche': '45 min · en direct',
                      'description': "Une heure pour dompter la fermeture éclair, "
                                     "de la pose du pied presseur à la finition."},
        )

        agenda['repair'], _ = EvenementCommunaute.objects.update_or_create(
            titre='Repair café du quartier',
            defaults={'format_evenement': 'presentiel',
                      'date_evenement': aujourdhui + timedelta(days=8),
                      'heure_debut': '14h', 'heure_fin': '18h',
                      'lieu': 'MJC Croix-Rousse', 'adresse': '12 rue des Pierres Plantées',
                      'distance_km': 1.2, 'machines_dispo': 12, 'xp_gain': 50,
                      'motif': 'denim', 'accroche': '12 machines · surjeteuse dispo',
                      'animatrice': self.amies.get('sofia.d'),
                      'description': "Quatre heures d'atelier ouvert dans la cour de la MJC. "
                                     "Surjeteuse, machine à boutonnière et deux couturiers "
                                     "confirmés sur place. Apporte tes pièces à réparer et "
                                     "de quoi grignoter."},
        )

        agenda['atelier'], _ = EvenementCommunaute.objects.update_or_create(
            titre='Atelier teinture végétale',
            defaults={'format_evenement': 'presentiel',
                      'date_evenement': aujourdhui + timedelta(days=5),
                      'heure_debut': '10h', 'heure_fin': '13h',
                      'lieu': 'Jardin partagé de la Guillotière',
                      'adresse': '4 rue Sébastien Gryphe',
                      'distance_km': 3.4, 'machines_dispo': 0, 'xp_gain': 40,
                      'motif': 'vert', 'accroche': 'Pelures d\'oignon et garance',
                      'animatrice': self.amies.get('maya.j'),
                      'description': "Trois heures pour teindre coton et lin avec ce qui "
                                     "traîne en cuisine. Viens avec un textile clair, "
                                     "lavé et non traité."},
        )

        agenda['marathon'], _ = EvenementCommunaute.objects.update_or_create(
            titre='48 h zéro chute',
            defaults={'format_evenement': 'marathon',
                      'date_evenement': aujourdhui + timedelta(days=15),
                      'heure_debut': '', 'heure_fin': '',
                      'xp_gain': 120, 'motif': 'toile',
                      'accroche': 'Défi collectif · toute la ville',
                      'description': '500 m² recousus en un week-end. Équipes de 4.'},
        )

        agenda['visio'], _ = EvenementCommunaute.objects.update_or_create(
            titre='Lecture de patron : les crans',
            defaults={'format_evenement': 'en_ligne',
                      'date_evenement': aujourdhui + timedelta(days=11),
                      'heure_debut': '18h30', 'heure_fin': '19h15',
                      'duree': '45 min', 'xp_gain': 30, 'motif': 'lin',
                      'animatrice': self.amies.get('thomas.b'),
                      'accroche': '45 min · en direct',
                      'description': "Décoder les symboles d'un patron commercial : "
                                     "crans, droit-fil, valeurs de couture."},
        )

        # Les voisins remplissent les listes d'inscrits.
        voisins = list(self.amies.values())
        for cle, nombre in (('live', 12), ('repair', 9), ('atelier', 6),
                            ('marathon', 14), ('visio', 5)):
            for compte in voisins[:nombre]:
                InscriptionEvenement.objects.get_or_create(
                    utilisateur=compte, evenement=agenda[cle])
        return agenda

    def _inscriptions(self, moi):
        """La joueuse est déjà inscrite à deux rendez-vous."""
        for cle in ('live', 'repair'):
            evenement = self.evenements.get(cle)
            if evenement:
                InscriptionEvenement.objects.get_or_create(
                    utilisateur=moi, evenement=evenement)

    # ── Entraide ───────────────────────────────────────────────────────────
    def _entraide(self):
        aide = self.amies
        maintenant = timezone.now()

        # (auteur, contenu, tags, motif, résolue, [(auteur réponse, texte, validée, cœurs)], minutes)
        fils = [
            ('amine.r', "Mon fil casse à chaque passage sur l'ourlet du jean. Une idée ?",
             'denim,machine', '', False, [], 35),
            ('chloe.v', "Ce coton est-il assez solide pour un tote qui portera des courses ?",
             'coton', 'laine', False, [], 95),
            ('elias.n', "Comment éviter que le velours glisse à la coupe ?",
             'velours,coupe', '', False, [], 180),
            ('maya.j', 'Comment rattraper une couture qui gondole sur du jersey ?',
             'jersey', 'lin', True,
             [('sofia.d', 'Aiguille jersey 80 et point zigzag très serré, sans tirer le tissu.', True, 18),
              ('lea.p', "Et si tu as une surjeteuse, différentiel à 1,5 : ça règle le problème à la source.", False, 7)],
             1400),
            ('sarah.l', "Quelle doublure pour une veste en lin d'été ?",
             'lin,doublure', '', True,
             [('thomas.b', 'Cupro ou bemberg : ça respire et ça ne colle pas à la peau.', True, 12)],
             2900),
            ('paul.g', "Ma machine saute des points sur trois épaisseurs de denim, "
                       "j'ai changé l'aiguille pourtant.",
             'denim,machine', 'denim', False,
             [('sofia.d', "Aiguille jeans 100 ET ralentir. Le volant à la main sur les surépaisseurs.", False, 9),
              ('noor.k', 'Vérifie aussi que le pied est bien à plat, une cale en carton aide beaucoup.', False, 4)],
             620),
        ]

        for identifiant, contenu, tags, motif, resolue, reponses, minutes in fils:
            auteur = aide.get(identifiant)
            if not auteur or QuestionEntraide.objects.filter(
                    auteur=auteur, contenu=contenu).exists():
                continue
            question = QuestionEntraide.objects.create(
                auteur=auteur, contenu=contenu, tags=tags, motif=motif,
                resolue=resolue, xp_gain=15)
            QuestionEntraide.objects.filter(pk=question.pk).update(
                date_creation=maintenant - timedelta(minutes=minutes))

            for rang, (repondant, texte, validee, coeurs) in enumerate(reponses):
                compte = aide.get(repondant)
                if not compte:
                    continue
                reponse = ReponseEntraide.objects.create(
                    question=question, auteur=compte, contenu=texte,
                    validee=validee, coeurs=coeurs)
                ReponseEntraide.objects.filter(pk=reponse.pk).update(
                    date_creation=maintenant - timedelta(minutes=max(1, minutes - 20 * (rang + 1))))

        for identifiant, specialites in [('sofia.d', 'Denim, fermetures'),
                                         ('lea.p', 'Jersey, surjeteuse'),
                                         ('thomas.b', 'Patrons, coupe'),
                                         ('noor.k', 'Doublures, finitions'),
                                         ('maya.j', 'Teinture, matières'),
                                         ('hugo.m', 'Machines, réglages')]:
            compte = aide.get(identifiant)
            if compte:
                DisponibiliteEntraide.objects.update_or_create(
                    utilisateur=compte,
                    defaults={'specialites': specialites, 'en_ligne': True,
                              'delai_reponse_min': 5})

    def _troc(self):
        aide = self.amies
        annonces = [
            ('lea.p', '1,4 m² de velours côtelé vert à donner', 'donne', 1.4, 800, 'vert'),
            ('thomas.b', 'du denim brut', 'cherche', 0.6, 1400, 'denim'),
            ('sofia.d', '3 m² de toile de coton écrue', 'donne', 3.0, 450, 'toile'),
            ('yasmine.t', 'des chutes de jersey rayé', 'cherche', 0.4, 2100, 'lin'),
            ('hugo.m', "0,8 m² de laine bouillie grise", 'donne', 0.8, 1200, 'laine'),
            ('sarah.l', 'une fermeture invisible 40 cm', 'cherche', 0.1, 700, 'lin'),
        ]
        for identifiant, titre, sens, surface, distance, motif in annonces:
            compte = aide.get(identifiant)
            if compte and not AnnonceTroc.objects.filter(auteur=compte, titre=titre).exists():
                annonce = AnnonceTroc.objects.create(
                    auteur=compte, titre=titre, sens=sens, surface_m2=surface,
                    distance_m=distance, motif=motif)
                AnnonceTroc.objects.filter(pk=annonce.pk).update(
                    date_creation=timezone.now() - timedelta(hours=distance // 200))

    def _transactions(self, moi):
        if TransactionPieces.objects.filter(utilisateur=moi).exists():
            return
        maintenant = timezone.now()
        for libelle, montant, icone, jours in [
            ('Gel de série ×1', -40, 'gel', 3),
            ('Patron sac banane', -90, 'patron', 9),
            ('Quête : analyser un vêtement', 20, 'piece', 1),
            ('Coffre du jour', 30, 'coffre', 2),
            ('Duel gagné contre Thomas', 40, 'eclair', 3),
            ('Réponse retenue', 15, 'piece', 5),
        ]:
            transaction_obj = TransactionPieces.objects.create(
                utilisateur=moi, libelle=libelle, montant=montant, icone=icone)
            TransactionPieces.objects.filter(pk=transaction_obj.pk).update(
                date_transaction=maintenant - timedelta(days=jours))
