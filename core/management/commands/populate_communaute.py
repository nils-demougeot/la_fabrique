"""
Commande de population de la base de données pour la section Communauté.
Crée des utilisateurs fictifs, des posts, des commentaires, des likes et des follows.

Usage: python manage.py populate_communaute
       python manage.py populate_communaute --reset  (repart de zéro)
"""
import random
from django.core.management.base import BaseCommand
from django.contrib.auth.hashers import make_password
from core.models import (Utilisateur, PostCommunaute, LikePost, SauvegardePost,
                          CommentairePost, Suivi, Hashtag)


FAKE_USERS = [
    {
        'username': 'sophie_couture',
        'email': 'sophie@example.com',
        'avatar': 'image 12.png',
        'bio': 'Upcycleuse passionnée depuis 10 ans. Je transforme les textiles oubliés en créations durables.',
        'niveau_couture': 'Confirmé',
    },
    {
        'username': 'marc_denim',
        'email': 'marc@example.com',
        'avatar': 'image 13.png',
        'bio': 'Fan de denim et de couture zéro déchet. Chaque jean a une deuxième vie.',
        'niveau_couture': 'Intermédiaire',
    },
    {
        'username': 'camille_vert',
        'email': 'camille@example.com',
        'avatar': 'image 14.png',
        'bio': 'Adepte de la teinture naturelle. J\'utilise des plantes et épices pour colorer mes créations.',
        'niveau_couture': 'Confirmé',
    },
    {
        'username': 'theo_reparation',
        'email': 'theo@example.com',
        'avatar': 'image 15.png',
        'bio': 'Réparer plutôt que jeter. Sashiko, kintsugi textile, et broderie visible.',
        'niveau_couture': 'Intermédiaire',
    },
    {
        'username': 'lea_faitmain',
        'email': 'lea@example.com',
        'avatar': 'image 16.png',
        'bio': 'Débutante enthousiaste ! J\'apprends à coudre et je partage mes projets.',
        'niveau_couture': 'Débutant',
    },
    {
        'username': 'hugo_zero_dechet',
        'email': 'hugo@example.com',
        'avatar': 'image 17.png',
        'bio': 'Mode durable et slow fashion. Chaque achat compte, chaque tissu aussi.',
        'niveau_couture': 'Confirmé',
    },
    {
        'username': 'emma_patron',
        'email': 'emma@example.com',
        'avatar': 'image 18.png',
        'bio': 'Créatrice de patrons. Je dessine, je coupe, j\'assemble et j\'enseigne.',
        'niveau_couture': 'Confirmé',
    },
    {
        'username': 'lucas_lin',
        'email': 'lucas@example.com',
        'avatar': 'image 19.png',
        'bio': 'Amoureux du lin et des matières naturelles. Confection artisanale.',
        'niveau_couture': 'Intermédiaire',
    },
]

HASHTAG_NAMES = [
    'zerodechet', 'upcycling', 'teinturenaturelle', 'faitmain',
    'modedurable', 'couture', 'recyclage', 'slowfashion',
    'denim', 'lin', 'sashiko', 'ecotextile',
]

POSTS_DATA = [
    {
        'titre': 'Tote bag en denim recyclé',
        'description': 'Récupéré trois vieux jeans pour créer ce sac solide du quotidien. Patron zéro déchet, tout a été utilisé ! La doublure vient d\'une vieille chemise.',
        'type_creation': 'upcycling',
        'niveau': 'intermediaire',
        'hashtags': ['zerodechet', 'denim', 'upcycling'],
        'user_key': 'marc_denim',
    },
    {
        'titre': 'Teinture à l\'écorce d\'oignon',
        'description': 'Expérience du week-end avec des restes de cuisine ! Cette vieille chemise en lin a maintenant un magnifique reflet doré naturel.',
        'type_creation': 'teinture',
        'niveau': 'debutant',
        'hashtags': ['teinturenaturelle', 'lin', 'zerodechet'],
        'user_key': 'camille_vert',
    },
    {
        'titre': 'Robe bohème upcyclée',
        'description': 'Transformé un rideau en lin en cette robe légère pour l\'été. La broderie florale est faite à la main avec des fils récupérés.',
        'type_creation': 'upcycling',
        'niveau': 'confirme',
        'hashtags': ['upcycling', 'lin', 'faitmain'],
        'user_key': 'sophie_couture',
    },
    {
        'titre': 'Réparation sashiko visible',
        'description': 'Mon jean préféré avait un trou au genou. Plutôt que le jeter, j\'ai pratiqué le sashiko — technique japonaise de broderie de réparation. Résultat unique !',
        'type_creation': 'reparation',
        'niveau': 'intermediaire',
        'hashtags': ['sashiko', 'denim', 'modedurable'],
        'user_key': 'theo_reparation',
    },
    {
        'titre': 'Mon premier coussin fait main',
        'description': 'Première réalisation ! Coussin en tissu récupéré d\'une veste trop grande. Bourrage avec des chutes de tissu. Fière du résultat !',
        'type_creation': 'fait-main',
        'niveau': 'debutant',
        'hashtags': ['faitmain', 'debutante', 'zerodechet'],
        'user_key': 'lea_faitmain',
    },
    {
        'titre': 'Collection capsule zéro déchet',
        'description': 'Voici ma mini collection printemps : top, pantalon et pochette, tout réalisé avec des vêtements déstructurés. Aucun tissu neuf utilisé.',
        'type_creation': 'upcycling',
        'niveau': 'confirme',
        'hashtags': ['zerodechet', 'slowfashion', 'upcycling'],
        'user_key': 'hugo_zero_dechet',
    },
    {
        'titre': 'Patron chemise oversize',
        'description': 'Je partage mon patron de chemise oversize gratuit. Dimensions pour 6 tailles, patron testé 3 fois. Parfait pour débuter la couture sérieuse.',
        'type_creation': 'patron',
        'niveau': 'intermediaire',
        'hashtags': ['couture', 'faitmain', 'patron'],
        'user_key': 'emma_patron',
    },
    {
        'titre': 'Veste en lin naturel',
        'description': 'Cette veste structure mon dressing d\'été. Lin lavé 100% non teint, doublure en mousseline de soie upcyclée. Couture entièrement à la main.',
        'type_creation': 'fait-main',
        'niveau': 'confirme',
        'hashtags': ['lin', 'faitmain', 'ecotextile'],
        'user_key': 'lucas_lin',
    },
    {
        'titre': 'Teinture à l\'indigo naturel',
        'description': 'Après 3 mois de fermentation, ma cuve d\'indigo naturel est enfin prête. Ces tee-shirts blancs recyclés ont maintenant une teinte bleu profond magnifique.',
        'type_creation': 'teinture',
        'niveau': 'confirme',
        'hashtags': ['teinturenaturelle', 'indigo', 'ecotextile'],
        'user_key': 'camille_vert',
    },
    {
        'titre': 'Jean transformé en short bermuda',
        'description': 'Solution anti-gaspillage préférée : le jean troué au genou devient un bermuda ! Bords effilochés, coutures renforcées avec du fil contrasté.',
        'type_creation': 'reparation',
        'niveau': 'debutant',
        'hashtags': ['denim', 'zerodechet', 'recyclage'],
        'user_key': 'marc_denim',
    },
    {
        'titre': 'Sac à dos en tapisserie vintage',
        'description': 'Récupéré un vieux siège de chaise en tapisserie provençale chez ma grand-mère. Maintenant c\'est un sac à dos unique et coloré !',
        'type_creation': 'upcycling',
        'niveau': 'confirme',
        'hashtags': ['upcycling', 'vintage', 'faitmain'],
        'user_key': 'sophie_couture',
    },
    {
        'titre': 'Écharpe en chutes de laine',
        'description': 'Accumulé des chutes de laine pendant 2 ans. Enfin j\'en ai fait cette écharpe rayée ! Tricot facile, parfait pour débuter.',
        'type_creation': 'fait-main',
        'niveau': 'debutant',
        'hashtags': ['tricot', 'zerodechet', 'faitmain'],
        'user_key': 'lea_faitmain',
    },
    {
        'titre': 'Ceinture denim origami',
        'description': 'Technique de pliage appliquée au tissu pour créer cette ceinture rigide. Récupéré la ceinture d\'un jean usagé comme base.',
        'type_creation': 'fait-main',
        'niveau': 'intermediaire',
        'hashtags': ['denim', 'faitmain', 'upcycling'],
        'user_key': 'theo_reparation',
    },
    {
        'titre': 'Patron robe trapèze intemporelle',
        'description': 'Je partage ce patron simple et élégant. Robe trapèze à manches 3/4, adaptable à toutes tailles. Testé sur 4 matières différentes.',
        'type_creation': 'patron',
        'niveau': 'debutant',
        'hashtags': ['patron', 'couture', 'faitmain'],
        'user_key': 'emma_patron',
    },
    {
        'titre': 'Chemise de travail en lin brut',
        'description': 'Inspiré des chemises de travail japonaises (work shirt). Lin brut non blanchi, coutures anglaises. Durée de vie : 20 ans minimum !',
        'type_creation': 'fait-main',
        'niveau': 'confirme',
        'hashtags': ['lin', 'slowfashion', 'faitmain'],
        'user_key': 'lucas_lin',
    },
]

COMMENTS_TEMPLATES = [
    "Magnifique réalisation ! La technique est vraiment bien maîtrisée.",
    "Super projet ! Quelle matière as-tu utilisée pour la doublure ?",
    "J'adore l'idée, je vais m'en inspirer pour mes prochains projets.",
    "Le résultat est bluffant, on ne dirait pas que c'est recyclé !",
    "Bravo ! Combien de temps t'a pris cette création ?",
    "Très beau travail. Le choix des couleurs est parfait.",
    "Génial ! Est-ce que tu partages le patron ?",
    "Inspirant ! La façon dont tu as géré les coutures est impeccable.",
    "Belle idée de réutiliser ce tissu. Durable et stylé !",
    "Wow, quel talent ! J'espère arriver à ce niveau un jour.",
    "La technique de teinture donne un résultat très naturel.",
    "J'ai essayé quelque chose de similaire, le résultat est toujours unique.",
    "Ça donne envie de se lancer ! Merci pour l'inspiration.",
    "Le rendu final est vraiment pro. Bravo !",
    "Super projet zéro déchet ! Chaque geste compte.",
    "J'aime beaucoup la texture du tissu. Quelle matière ?",
    "Vraiment inspirant pour un débutant comme moi !",
    "Ces couleurs sont magnifiques ! La teinture naturelle, c'est magique.",
]


class Command(BaseCommand):
    help = 'Peuple la base de données avec des données fictives pour la communauté'

    def add_arguments(self, parser):
        parser.add_argument('--reset', action='store_true',
                            help='Supprime toutes les données communauté avant de repeupler')

    def handle(self, *args, **options):
        if options['reset']:
            self.stdout.write('Suppression des données existantes...')
            PostCommunaute.objects.all().delete()
            Hashtag.objects.all().delete()
            Suivi.objects.all().delete()
            Utilisateur.objects.filter(username__in=[u['username'] for u in FAKE_USERS]).delete()
            self.stdout.write(self.style.WARNING('Données supprimées.'))

        # 1. Créer les hashtags
        self.stdout.write('Création des hashtags...')
        hashtags = {}
        for nom in HASHTAG_NAMES:
            h, _ = Hashtag.objects.get_or_create(nom=nom)
            hashtags[nom] = h
        self.stdout.write(self.style.SUCCESS(f'  {len(hashtags)} hashtags créés/récupérés'))

        # 2. Créer les utilisateurs fictifs
        self.stdout.write('Création des utilisateurs fictifs...')
        users = {}
        password_hash = make_password('motdepasse123')
        for u_data in FAKE_USERS:
            user, created = Utilisateur.objects.get_or_create(
                username=u_data['username'],
                defaults={
                    'email': u_data['email'],
                    'password': password_hash,
                    'avatar': u_data['avatar'],
                    'bio': u_data['bio'],
                    'niveau_couture': u_data['niveau_couture'],
                    'consentementRGPD': True,
                    'soldePieces': random.randint(50, 300),
                }
            )
            users[u_data['username']] = user
            if created:
                self.stdout.write(f'  + {user.username}')
            else:
                self.stdout.write(f'  ~ {user.username} (existant)')
        self.stdout.write(self.style.SUCCESS(f'  {len(users)} utilisateurs prêts'))

        # 3. Créer les posts
        self.stdout.write('Création des posts...')
        posts = []
        from django.utils import timezone
        from datetime import timedelta

        # Seulement 5 posts ont une vraie photo ; les autres sont texte uniquement
        POST_IMAGES = {
            'Tote bag en denim recyclé':    'posts/real-upcycling.jpg',
            "Teinture à l'écorce d'oignon": 'posts/real-teinture.jpg',
            'Réparation sashiko visible':   'posts/real-reparation.jpg',
            'Patron chemise oversize':      'posts/real-patron.jpg',
            'Veste en lin naturel':         'posts/real-fait-main.jpg',
        }

        for i, p_data in enumerate(POSTS_DATA):
            user = users.get(p_data['user_key'])
            if not user:
                continue

            days_ago = random.randint(0, 30)
            hours_ago = random.randint(0, 23)
            created_at = timezone.now() - timedelta(days=days_ago, hours=hours_ago)

            image_path = POST_IMAGES.get(p_data['titre'], '')

            post, created = PostCommunaute.objects.get_or_create(
                utilisateur=user,
                titre=p_data['titre'],
                defaults={
                    'description': p_data['description'],
                    'type_creation': p_data['type_creation'],
                    'niveau': p_data['niveau'],
                    'nb_vues': random.randint(10, 500),
                    'image': image_path,
                }
            )
            if created:
                post.date_creation = created_at
                post.save(update_fields=['date_creation', 'nb_vues'])
                for tag_nom in p_data.get('hashtags', []):
                    if tag_nom in hashtags:
                        post.hashtags.add(hashtags[tag_nom])
                self.stdout.write(f'  + "{post.titre[:40]}" {"[photo]" if image_path else "[texte]"}')
            posts.append(post)

        self.stdout.write(self.style.SUCCESS(f'  {len(posts)} posts prêts'))

        # 4. Créer les likes
        self.stdout.write('Création des likes...')
        all_users = list(users.values())
        likes_count = 0
        for post in posts:
            likers = random.sample(all_users, k=random.randint(1, min(len(all_users), 6)))
            for liker in likers:
                if liker != post.utilisateur:
                    _, created = LikePost.objects.get_or_create(utilisateur=liker, post=post)
                    if created:
                        likes_count += 1
        self.stdout.write(self.style.SUCCESS(f'  {likes_count} likes créés'))

        # 5. Créer les commentaires
        self.stdout.write('Création des commentaires...')
        comments_count = 0
        for post in posts:
            nb_comments = random.randint(1, 4)
            commenters = random.sample(all_users, k=min(nb_comments, len(all_users)))
            for commenter in commenters:
                contenu = random.choice(COMMENTS_TEMPLATES)
                _, created = CommentairePost.objects.get_or_create(
                    utilisateur=commenter, post=post, contenu=contenu,
                )
                if created:
                    comments_count += 1
        self.stdout.write(self.style.SUCCESS(f'  {comments_count} commentaires créés'))

        # 6. Créer les relations de suivi
        self.stdout.write('Création des relations de suivi...')
        follows_count = 0
        for user in all_users:
            to_follow = random.sample(
                [u for u in all_users if u != user],
                k=random.randint(2, min(5, len(all_users) - 1))
            )
            for target in to_follow:
                _, created = Suivi.objects.get_or_create(suiveur=user, suivi=target)
                if created:
                    follows_count += 1
        self.stdout.write(self.style.SUCCESS(f'  {follows_count} relations de suivi créées'))

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('Base de donnees communaute peuplee avec succes !'))
        self.stdout.write('')
        self.stdout.write('Comptes créés (mot de passe: motdepasse123):')
        for u_data in FAKE_USERS:
            self.stdout.write(f'  - {u_data["username"]}')
