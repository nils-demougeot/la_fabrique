import urllib.request
import urllib.error
import os
from django.conf import settings
from django.core.management.base import BaseCommand
from django.core.files.base import ContentFile
from django.db import transaction
from core.models import Patron, EtapePatron, Tutoriel


PATRONS_DATA = [
    {
        'titre': 'Tote bag XXL',
        'description': (
            'Grand sac cabas polyvalent et résistant, idéal pour le marché, la plage ou le quotidien. '
            'Ce projet débutant vous initie aux coutures droites, à la construction d\'un fond structuré '
            'et à la fixation d\'anses solides. Résultat durable garanti en moins de deux heures !'
        ),
        'typeObjet': 'Sac',
        'surfaceMin': 0.5,
        'surfaceMax': 1.0,
        'estPremium': False,
        'difficulte': 1,
        'duree': '2h',
        'materiel': 'Ciseaux de couture, Machine à coudre, Fil, Épingles, Craie de couture, Fer à repasser',
        'matiere_requise': 'coton,lin,jean,toile',
        'photo_url': 'https://images.unsplash.com/photo-1591348278863-a8fb3887e2aa?w=800&h=600&fit=crop&q=80',
        'photo_name': 'patron_tote_bag_xxl.jpg',
        'cloudinary_url': 'https://res.cloudinary.com/dh1i1pzbv/image/upload/v1780491684/patrons/patron_tote_bag_xxl.jpg',
        'etapes': [
            {
                'numero': 1,
                'titre': 'Préparation et découpe du tissu',
                'description': (
                    'Lavez et repassez votre tissu avant de commencer — cela évite les rétrécissements après confection. '
                    'Posez-le bien à plat sur votre table de coupe. Tracez à la craie de couture : deux rectangles de 42 × 48 cm '
                    'pour le corps du sac, et deux bandes de 10 × 65 cm pour les anses. '
                    'Vérifiez le sens du droit fil (parallèle à la lisière) avant chaque découpe. '
                    'Découpez soigneusement avec des ciseaux de couture, en coupant d\'un seul geste continu pour un bord propre.'
                ),
                'video_url': 'https://www.youtube.com/watch?v=BaSmyabj9Hk',
                'conseil': (
                    'Gardez toutes les chutes : un coin du sac, une petite poche intérieure ou un détail appliqué '
                    'peuvent transformer un sac basique en pièce unique.'
                ),
                'materiaux_etape': 'Ciseaux de couture, Craie de couture, Règle plate, Fer à repasser',
            },
            {
                'numero': 2,
                'titre': 'Confection des anses',
                'description': (
                    'Pliez chaque bande d\'anse en deux dans le sens de la longueur, endroit contre endroit. '
                    'Cousez le long côté à 1 cm du bord avec un point droit solide. '
                    'Attachez une épingle de sûreté à une extrémité, glissez-la à l\'intérieur du tube '
                    'et faites-la coulisser vers l\'autre bout pour retourner l\'anse à l\'endroit. '
                    'Repassez bien à plat en centrant la couture au milieu de l\'anse. '
                    'Surpiquez à 3 mm de chaque bord sur toute la longueur pour rigidifier l\'anse.'
                ),
                'video_url': None,
                'conseil': (
                    'Si le tissu est épais, glissez un peu de rembourrage mousse fin ou doublez le tissu '
                    'pour des anses confortables qui ne coupent pas les mains.'
                ),
                'materiaux_etape': 'Machine à coudre, Fil, Épingle de sûreté, Fer à repasser',
            },
            {
                'numero': 3,
                'titre': 'Assemblage du corps du sac',
                'description': (
                    'Placez les deux rectangles endroit contre endroit et épinglez les trois côtés '
                    '(les deux flancs et le fond). Cousez à 1,5 cm du bord avec un point droit, '
                    'en faisant des points arrière au début et à la fin de chaque couture. '
                    'Repassez les marges de couture ouvertes avec le fer pour un bel aplat. '
                    'Pour créer des coins plats qui donnent du volume au fond : pincez chaque angle '
                    'en formant un triangle, alignez la couture du flanc avec la couture du fond, '
                    'et cousez perpendiculairement à 5 cm de la pointe. Coupez l\'excédent à 1 cm.'
                ),
                'video_url': None,
                'conseil': (
                    'La profondeur des coins détermine la largeur du fond : 5 cm de couture = 10 cm de fond. '
                    'Adaptez cette valeur à la capacité souhaitée.'
                ),
                'materiaux_etape': 'Machine à coudre, Fil, Épingles, Ciseaux, Fer à repasser',
            },
            {
                'numero': 4,
                'titre': 'Fixation des anses et ourlet supérieur',
                'description': (
                    'Retournez le sac à l\'endroit. Positionnez les anses à 10 cm des coutures latérales, '
                    'en les faisant rentrer de 4 cm dans le sac. Épinglez-les bien droites. '
                    'Repliez le bord supérieur du sac de 1 cm vers l\'envers, repassez, '
                    'puis repliez à nouveau de 3 cm et épinglez en emprisonnant les extrémités des anses. '
                    'Cousez tout le tour à 0,3 cm du bord replié, puis ajoutez une deuxième rangée de couture à 2,7 cm.'
                ),
                'video_url': None,
                'conseil': (
                    'Faites un carré renforcé en X sur chaque point d\'attache des anses : '
                    'c\'est la technique professionnelle pour les sacs destinés à supporter un poids quotidien.'
                ),
                'materiaux_etape': 'Machine à coudre, Fil, Épingles, Fer à repasser',
            },
            {
                'numero': 5,
                'titre': 'Contrôle et finitions',
                'description': (
                    'Retournez le sac sur l\'envers et inspectez toutes les coutures : '
                    'vérifiez qu\'aucun point n\'a sauté et que les marges sont bien ouvertes. '
                    'Passez une flamme (briquet) brièvement sur les éventuels fils qui dépassent '
                    'si votre tissu est synthétique, ou coupez-les au ras pour les fibres naturelles. '
                    'Retournez à l\'endroit, repassez une dernière fois et remplissez le sac '
                    'd\'un peu de papier de soie pour lui donner sa forme pendant le séchage.'
                ),
                'video_url': None,
                'conseil': (
                    'Pour imperméabiliser légèrement votre tote bag en coton, vaporisez un imperméabilisant '
                    'textile en spray (disponible en droguerie) à 20 cm de distance.'
                ),
                'materiaux_etape': 'Ciseaux, Fer à repasser',
            },
        ],
        'tutoriels': [
            {
                'titre': 'Tote bag grand format — tutoriel débutant',
                'typeTutoriel': 'video',
                'urlVideoOuArticle': 'https://www.youtube.com/watch?v=BaSmyabj9Hk',
                'source': 'YouTube',
                'description': 'Tutoriel vidéo complet de A à Z : découpe, assemblage et finitions expliqués pas à pas.',
            },
            {
                'titre': 'Guide PDF patron tote bag XXL',
                'typeTutoriel': 'pdf',
                'urlVideoOuArticle': 'https://www.couturefacile.com/patrons/tote-bag-xxl.pdf',
                'source': 'Couture Facile',
                'description': 'Patron PDF téléchargeable avec toutes les mesures, les repères de couture et conseils sur le choix du tissu.',
            },
        ],
    },

    {
        'titre': 'Pochette zippée bicolore',
        'description': (
            'Petite pochette pratique avec fermeture éclair, parfaite pour ranger cosmétiques, '
            'câbles ou affaires de voyage. Ce projet initie à la pose de fermeture éclair, '
            'technique redoutée mais simple une fois le truc compris ! Idéal pour valoriser '
            'les chutes de tissu colorées.'
        ),
        'typeObjet': 'Pochette',
        'surfaceMin': 0.15,
        'surfaceMax': 0.35,
        'estPremium': False,
        'difficulte': 1,
        'duree': '1h',
        'materiel': 'Ciseaux, Machine à coudre, Fil, Épingles, Épingle de sûreté',
        'matiere_requise': '',
        'photo_url': 'https://images.unsplash.com/photo-1584917865442-de89df76afd3?w=800&h=600&fit=crop&q=80',
        'photo_name': 'patron_pochette_zippee.jpg',
        'cloudinary_url': 'https://res.cloudinary.com/dh1i1pzbv/image/upload/v1780491742/patrons/patron_pochette_zippee.jpg',
        'etapes': [
            {
                'numero': 1,
                'titre': 'Découpe des pièces',
                'description': (
                    'Découpez deux rectangles identiques de 22 × 18 cm dans votre tissu principal '
                    'et deux rectangles de même taille dans la doublure. '
                    'Repassez tous les rectangles pour les aplatir parfaitement. '
                    'Si vous faites une pochette bicolore, utilisez deux tissus différents pour l\'avant et l\'arrière.'
                ),
                'video_url': None,
                'conseil': (
                    'Coupez les rectangles de doublure 1 cm plus petits en largeur pour éviter '
                    'que la doublure dépasse à l\'extérieur après retournement.'
                ),
                'materiaux_etape': 'Ciseaux, Fer à repasser, Craie de couture',
            },
            {
                'numero': 2,
                'titre': 'Pose de la fermeture éclair',
                'description': (
                    'Posez un rectangle de tissu principal endroit vers le haut. '
                    'Déposez la fermeture éclair face vers le bas, dents alignées sur le bord supérieur. '
                    'Posez un rectangle de doublure endroit vers le bas par-dessus (sandwich). '
                    'Épinglez les trois couches et cousez à 0,7 cm du bord avec un pied zipper. '
                    'Ouvrez le tout à plat, repassez les tissus away du zip et surpiquez à 3 mm du zip. '
                    'Répétez l\'opération pour l\'autre côté de la fermeture éclair.'
                ),
                'video_url': 'https://www.youtube.com/watch?v=CfbVgG4JSJA',
                'conseil': (
                    'La règle d\'or : ouvrez la fermeture éclair à moitié avant de coudre le tour. '
                    'Sinon, vous ne pourrez pas retourner la pochette !'
                ),
                'materiaux_etape': 'Machine à coudre, Pied zipper, Fil, Épingles, Fer à repasser',
            },
            {
                'numero': 3,
                'titre': 'Assemblage de la pochette',
                'description': (
                    'Retournez l\'ensemble à plat, tissu principal contre tissu principal '
                    'et doublure contre doublure. Vérifiez que la fermeture éclair est entrouverte. '
                    'Épinglez tout le tour en laissant une ouverture de 8 cm dans la doublure (côté bas). '
                    'Cousez le tour à 1 cm du bord, en renforçant les points d\'arrêt près du zip. '
                    'Coupez les coins en diagonale à 2 mm de la couture pour réduire le volume.'
                ),
                'video_url': None,
                'conseil': (
                    'Ne cousez pas trop près des dents de la fermeture éclair. '
                    'Le pied zipper vous permet de coudre à exactement la bonne distance.'
                ),
                'materiaux_etape': 'Machine à coudre, Fil, Épingles, Ciseaux',
            },
            {
                'numero': 4,
                'titre': 'Retournement et finitions',
                'description': (
                    'Retournez la pochette à l\'endroit en passant par l\'ouverture laissée dans la doublure. '
                    'Poussez bien les coins avec un stylo à capuchon pour les obtenir bien pointus. '
                    'Glissez la doublure à l\'intérieur de la pochette. '
                    'Refermez l\'ouverture de la doublure en cousant à la machine ou à la main au point glissé. '
                    'Repassez la pochette à froid pour l\'aplatir. Testez la fermeture éclair et c\'est prêt !'
                ),
                'video_url': None,
                'conseil': (
                    'Si la fermeture éclair tire en arrière une fois la pochette retournée, '
                    'cousez un crochet de décoration sur le curseur pour faciliter l\'ouverture.'
                ),
                'materiaux_etape': 'Fer à repasser, Ciseaux, Aiguille, Fil',
            },
        ],
        'tutoriels': [
            {
                'titre': 'Poser une fermeture éclair sans stress',
                'typeTutoriel': 'video',
                'urlVideoOuArticle': 'https://www.youtube.com/watch?v=CfbVgG4JSJA',
                'source': 'YouTube',
                'description': 'Toutes les astuces pour aligner et coudre un zip parfaitement, même pour les débutants.',
            },
        ],
    },

    {
        'titre': 'Coussin patchwork bohème',
        'description': (
            'Coussin décoratif en patchwork composé de carrés et de rectangles de tissus dépareillés. '
            'La technique du patchwork permet de créer des motifs géométriques saisissants '
            'tout en valorisant les plus petites chutes de tissu. '
            'Un projet qui transforme le désordre du tiroir à chutes en objet de décoration élégant.'
        ),
        'typeObjet': 'Coussin',
        'surfaceMin': 0.4,
        'surfaceMax': 0.9,
        'estPremium': False,
        'difficulte': 2,
        'duree': '3h30',
        'materiel': 'Ciseaux, Machine à coudre, Fil, Épingles, Règle de patchwork, Craie de couture, Fer à repasser',
        'matiere_requise': 'coton,lin',
        'photo_url': 'https://images.unsplash.com/photo-1558618666-fcd25c85cd64?w=800&h=600&fit=crop&q=80',
        'photo_name': 'patron_coussin_patchwork.jpg',
        'cloudinary_url': 'https://res.cloudinary.com/dh1i1pzbv/image/upload/v1780491743/patrons/patron_coussin_patchwork.jpg',
        'etapes': [
            {
                'numero': 1,
                'titre': 'Sélection et organisation des tissus',
                'description': (
                    'Choisissez 6 à 9 tissus différents qui s\'harmonisent — par exemple trois tons d\'une même couleur '
                    'plus deux ou trois tissus imprimés neutres. '
                    'Posez-les côte à côte sur votre table et faites des tests de combinaisons. '
                    'L\'harmonie idéale repose sur une alternance de tissus imprimés et de tissus unis, '
                    'avec une progression de clair à foncé ou un contraste marqué.'
                ),
                'video_url': None,
                'conseil': (
                    'Photographiez vos tests d\'agencement avec votre téléphone pour vous souvenir '
                    'des combinaisons qui vous plaisent avant de couper quoi que ce soit.'
                ),
                'materiaux_etape': '',
            },
            {
                'numero': 2,
                'titre': 'Découpe des carrés de patchwork',
                'description': (
                    'Tracez et découpez 25 carrés de 12 × 12 cm (pour un coussin 50 × 50 cm fini). '
                    'Marquez au dos de chaque carré un repère pour le sens du fil. '
                    'Si vous utilisez des imprimés directionnels (fleurs, rayures), '
                    'coupez tous les carrés dans le même sens. '
                    'Organisez vos carrés sur la table dans la disposition finale : 5 rangées de 5.'
                ),
                'video_url': 'https://www.youtube.com/watch?v=_mFd8FHIZM4',
                'conseil': (
                    'Coupez des carrés légèrement plus grands (13 cm) si c\'est votre premier patchwork : '
                    'vous récupérerez les imperfections dans les marges de couture de 1,5 cm.'
                ),
                'materiaux_etape': 'Ciseaux, Règle de patchwork, Craie de couture',
            },
            {
                'numero': 3,
                'titre': 'Assemblage des rangées',
                'description': (
                    'Assemblez les carrés rangée par rangée : placez le premier et le deuxième carré '
                    'endroit contre endroit et cousez le bord droit à exactement 1 cm. '
                    'Continuez jusqu\'à compléter la rangée de 5 carrés. '
                    'Repassez toutes les marges de couture d\'une rangée dans le même sens, '
                    'et en sens inverse pour la rangée suivante — les coutures s\'emboîteront parfaitement.'
                ),
                'video_url': None,
                'conseil': (
                    'Numérotez vos rangées avec des petits papiers épinglés pour ne pas les mélanger '
                    'une fois assemblées. Le sens des marges repassées est CRUCIAL pour les intersections plates.'
                ),
                'materiaux_etape': 'Machine à coudre, Fil, Épingles, Fer à repasser',
            },
            {
                'numero': 4,
                'titre': 'Assemblage du panneau complet',
                'description': (
                    'Posez la rangée 1 et la rangée 2 endroit contre endroit. '
                    'Alignez soigneusement les intersections : les marges repassées en sens opposés '
                    'vont s\'emboîter et créer un point de jonction parfait. '
                    'Épinglez juste avant chaque intersection. '
                    'Cousez à 1 cm et vérifiez que les carrés sont bien alignés en ouvrant le tissu. '
                    'Continuez jusqu\'à assembler les 5 rangées. Repassez à plat.'
                ),
                'video_url': None,
                'conseil': (
                    'Si une intersection est décalée, décousez uniquement les 3 cm autour du problème '
                    'et recousez. Inutile de défaire toute la couture !'
                ),
                'materiaux_etape': 'Machine à coudre, Fil, Épingles, Fer à repasser',
            },
            {
                'numero': 5,
                'titre': 'Montage du coussin',
                'description': (
                    'Découpez un carré de 52 × 52 cm dans un tissu de dos uni ou complémentaire. '
                    'Placez le panneau patchwork et le dos endroit contre endroit. '
                    'Épinglez tout le pourtour en laissant une ouverture de 20 cm sur un côté. '
                    'Cousez à 1 cm, faites des points d\'arrêt, coupez les coins en biais. '
                    'Retournez à l\'endroit, remplissez de rembourrage ou glissez un coussin de 50 cm. '
                    'Fermez l\'ouverture au point glissé invisible.'
                ),
                'video_url': None,
                'conseil': (
                    'Bourrez le coussin plus que vous ne le pensez nécessaire : '
                    'il perdra 10 à 15 % de son gonflant après quelques semaines.'
                ),
                'materiaux_etape': 'Machine à coudre, Fil, Épingles, Ciseaux, Aiguille',
            },
            {
                'numero': 6,
                'titre': 'Finitions et points décoratifs',
                'description': (
                    'Optionnellement, ajoutez un point de quilting (couture décorative) '
                    'à travers les trois couches (patchwork, rembourrage, dos) '
                    'en suivant les lignes de couture du patchwork ou en créant un motif libre. '
                    'Vous pouvez aussi ajouter des boutons, du ruban ou des pompons sur les coins '
                    'pour personnaliser votre création.'
                ),
                'video_url': None,
                'conseil': (
                    'Un fil de quilting légèrement différent du fil d\'assemblage crée un joli contraste visuel '
                    'et met en valeur le travail du patchwork.'
                ),
                'materiaux_etape': 'Aiguille, Fil décoratif, Ciseaux',
            },
        ],
        'tutoriels': [
            {
                'titre': 'Patchwork en 9 blocs pour débutants',
                'typeTutoriel': 'article',
                'urlVideoOuArticle': 'https://www.maison-victor.com/tutos/patchwork-9-blocs',
                'source': 'La Maison Victor',
                'description': 'Guide illustré complet sur les bases du patchwork : harmonie des couleurs, découpe précise et assemblage sans faux plis.',
            },
            {
                'titre': 'Coussin patchwork géométrique — vidéo',
                'typeTutoriel': 'video',
                'urlVideoOuArticle': 'https://www.youtube.com/watch?v=_mFd8FHIZM4',
                'source': 'YouTube',
                'description': 'Assemblage en temps réel de 25 carrés avec démonstration des techniques d\'intersection.',
            },
        ],
    },

    {
        'titre': 'Tablier de cuisine élégant',
        'description': (
            'Tablier de cuisine ajusté avec une grande poche kangourou et des bretelles croisées dans le dos. '
            'Facile à coudre mais très gratifiant, ce projet transforme un grand morceau de tissu '
            'en un accessoire du quotidien solide et stylé. '
            'Parfait pour les tissus épais comme la toile, le jean ou le lin.'
        ),
        'typeObjet': 'Tablier',
        'surfaceMin': 0.6,
        'surfaceMax': 1.2,
        'estPremium': False,
        'difficulte': 1,
        'duree': '2h',
        'materiel': 'Ciseaux, Machine à coudre, Fil, Épingles, Fer à repasser, Décimètre, Craie de couture',
        'matiere_requise': 'coton,lin,toile,jean',
        'photo_url': 'https://images.unsplash.com/photo-1556912167-f556f1f39fdf?w=800&h=600&fit=crop&q=80',
        'photo_name': 'patron_tablier_cuisine.jpg',
        'cloudinary_url': 'https://res.cloudinary.com/dh1i1pzbv/image/upload/v1780491744/patrons/patron_tablier_cuisine.jpg',
        'etapes': [
            {
                'numero': 1,
                'titre': 'Tracé et découpe du tablier',
                'description': (
                    'Tracez le patron du tablier directement sur le tissu à la craie. '
                    'Dimensions : un rectangle de 65 × 80 cm pour le corps. '
                    'Arrondissez les deux coins supérieurs en traçant une courbe de 15 cm de rayon. '
                    'Découpez l\'échancrure du col (demi-cercle de 10 cm de rayon centré en haut). '
                    'Découpez ensuite un rectangle de 40 × 25 cm pour la grande poche avant.'
                ),
                'video_url': None,
                'conseil': (
                    'Pliez votre tissu en deux pour découper le tablier : vous obtiendrez une symétrie parfaite '
                    'sans avoir à tracer les deux côtés séparément.'
                ),
                'materiaux_etape': 'Ciseaux, Craie de couture, Décimètre, Règle',
            },
            {
                'numero': 2,
                'titre': 'Confection et pose de la poche',
                'description': (
                    'Repliez le bord supérieur de la poche de 1 cm puis de 2 cm et cousez. '
                    'Repassez les trois autres côtés avec 1 cm de surplus vers l\'envers. '
                    'Centrez la poche à 20 cm du bas du tablier et épinglez. '
                    'Cousez le bas et les deux côtés de la poche à 2 mm du bord replié. '
                    'Optionnel : cousez une couture verticale au centre de la poche '
                    'pour créer deux compartiments séparés.'
                ),
                'video_url': None,
                'conseil': (
                    'Renforcez les coins supérieurs de la poche avec un petit triangle cousu '
                    'ou un point en X : c\'est à ces endroits que les poches se déchirent en premier.'
                ),
                'materiaux_etape': 'Machine à coudre, Fil, Épingles, Fer à repasser',
            },
            {
                'numero': 3,
                'titre': 'Finition des bords du tablier',
                'description': (
                    'Repliez tout le pourtour du tablier (sauf le haut) de 1 cm puis de 2 cm vers l\'envers. '
                    'Épinglez et cousez à 1,8 cm du bord. '
                    'Pour le haut et l\'échancrure du col : coupez des encoches dans les courbes tous les 1 cm '
                    'pour permettre au tissu de s\'arrondir sans faire de plis. '
                    'Repassez soigneusement après chaque rempli pour des bords bien plats.'
                ),
                'video_url': None,
                'conseil': (
                    'Sur les tissus épais, utilisez un marteau de couture pour aplatir les ourlets '
                    'avant de piquer à la machine. Cela évite que la machine "saute" au-dessus du tissu épais.'
                ),
                'materiaux_etape': 'Machine à coudre, Fil, Épingles, Ciseaux, Fer à repasser',
            },
            {
                'numero': 4,
                'titre': 'Pose des bretelles et du lien de taille',
                'description': (
                    'Coupez une bande de 8 × 90 cm pour le lien de cou et deux bandes de 6 × 70 cm pour les liens de taille. '
                    'Confectionnez-les comme des anses (pliées, cousues, retournées, surpiquées). '
                    'Glissez les extrémités des liens sous l\'ourlet du tablier à l\'emplacement prévu '
                    'et cousez un carré renforcé en X à chaque point d\'attache. '
                    'Testez le tablier sur vous avant de coudre définitivement pour ajuster la longueur des bretelles.'
                ),
                'video_url': 'https://www.youtube.com/watch?v=Qlbq5nOhBb0',
                'conseil': (
                    'Pour un tablier à bretelles croisées dans le dos, attachez les liens de taille '
                    'à l\'avant après les avoir croisés dans le dos — très confortable et ajustable.'
                ),
                'materiaux_etape': 'Machine à coudre, Fil, Épingles, Ciseaux, Fer à repasser',
            },
        ],
        'tutoriels': [
            {
                'titre': 'Tablier de cuisine DIY — tuto vidéo',
                'typeTutoriel': 'video',
                'urlVideoOuArticle': 'https://www.youtube.com/watch?v=Qlbq5nOhBb0',
                'source': 'YouTube',
                'description': 'Tutoriel vidéo complet avec démonstration de la poche kangourou et des bretelles croisées.',
            },
            {
                'titre': 'Patron PDF tablier avec poches',
                'typeTutoriel': 'pdf',
                'urlVideoOuArticle': 'https://www.couturefacile.com/patrons/tablier-cuisine.pdf',
                'source': 'Couture Facile',
                'description': 'Patron imprimable taille adulte avec variantes pour tablier court ou long.',
            },
        ],
    },

    {
        'titre': 'Sac à dos urbain structuré',
        'description': (
            'Sac à dos fonctionnel et robuste avec poche frontale zippée, dos rembourré et bretelles réglables. '
            'Ce projet ambitieux convient aux couturières expérimentées et nécessite des tissus résistants '
            'comme le jean, la toile canvas ou le cuir synthétique. '
            'Le résultat est un sac durable, réparable et vraiment personnel.'
        ),
        'typeObjet': 'Sac',
        'surfaceMin': 1.0,
        'surfaceMax': 2.0,
        'estPremium': True,
        'difficulte': 3,
        'duree': '6h',
        'materiel': (
            'Ciseaux, Machine à coudre, Fil résistant, Épingles, Aiguille à jean, '
            'Fer à repasser, Marteau de couture, Pince-rivets, Décimètre'
        ),
        'matiere_requise': 'jean,toile',
        'photo_url': 'https://images.unsplash.com/photo-1553062407-98eeb64c6a62?w=800&h=600&fit=crop&q=80',
        'photo_name': 'patron_sac_a_dos.jpg',
        'cloudinary_url': 'https://res.cloudinary.com/dh1i1pzbv/image/upload/v1780491744/patrons/patron_sac_a_dos.jpg',
        'etapes': [
            {
                'numero': 1,
                'titre': 'Tracé et découpe de toutes les pièces',
                'description': (
                    'Préparez tous vos gabarits en papier avant de couper dans le tissu. '
                    'Pièces à découper : panneau avant (30 × 40 cm), panneau arrière (30 × 45 cm), '
                    'fond (30 × 10 cm), deux flancs (10 × 45 cm), poche frontale (28 × 20 cm), '
                    'et deux bretelles (8 × 65 cm). '
                    'Découpez aussi l\'interface thermocollante pour le panneau arrière et les bretelles.'
                ),
                'video_url': None,
                'conseil': (
                    'Organisez toutes vos pièces découpées sur une grande table et étiquetez-les. '
                    'Cette organisation initiale vous fera gagner du temps et évitera les erreurs d\'assemblage.'
                ),
                'materiaux_etape': 'Ciseaux, Craie de couture, Décimètre, Règle, Fer à repasser',
            },
            {
                'numero': 2,
                'titre': 'Construction de la poche frontale',
                'description': (
                    'Finissez le bord supérieur de la poche d\'un rempli de 2 cm cousu. '
                    'Posez la fermeture éclair du haut : placez-la sur l\'endroit de la poche, '
                    'cousez avec un pied zipper, puis repassez et surpiquez à 3 mm. '
                    'Assemblez l\'autre côté du zip avec la pièce de contrepoche. '
                    'Surpiquez les flancs de la poche à 2 mm du bord pour un aspect soigné.'
                ),
                'video_url': 'https://www.youtube.com/watch?v=CfbVgG4JSJA',
                'conseil': (
                    'Utilisez une fermeture éclair de qualité (métal ou nylon épais) : '
                    'c\'est le premier point de fragilité d\'un sac à dos et cela se voit à l\'usage.'
                ),
                'materiaux_etape': 'Machine à coudre, Fil résistant, Pied zipper, Épingles, Fer à repasser',
            },
            {
                'numero': 3,
                'titre': 'Préparation du panneau arrière',
                'description': (
                    'Thermocollez l\'interface sur l\'envers du panneau arrière. '
                    'Cousez une couche de mousse de 5 mm sur la zone de dos (zone de contact avec le dos). '
                    'Recouvrez avec un tissu doux (maille respirante ou coton léger) '
                    'en surpiquant les bords pour fixer la mousse et créer un dos confortable. '
                    'Marquez les emplacements des bretelles à 8 cm des flancs.'
                ),
                'video_url': None,
                'conseil': (
                    'Ajoutez un système de glissière de chargement de sac à dos si vous souhaitez '
                    'fixer votre sac à une valise : c\'est un détail pratique très apprécié.'
                ),
                'materiaux_etape': 'Fer à repasser, Machine à coudre, Fil, Épingles, Ciseaux',
            },
            {
                'numero': 4,
                'titre': 'Fabrication des bretelles réglables',
                'description': (
                    'Confectionnez les bretelles : cousez chaque bande de tissu sur trois côtés '
                    'avec interface thermocollée à l\'intérieur. Retournez et glissez une sangle plate de 2,5 cm '
                    'à l\'intérieur avant de fermer. Surpiquez les bords. '
                    'Passez l\'extrémité inférieure de chaque bretelle dans un anneau de réglage, '
                    'pliez et cousez solidement. Fixez les réglettes coulissantes pour l\'ajustement de longueur.'
                ),
                'video_url': None,
                'conseil': (
                    'Cousez les bretelles en X renforcé et passez plusieurs fois sur les points de fixation. '
                    'Un sac chargé génère une traction considérable sur ces points.'
                ),
                'materiaux_etape': 'Machine à coudre, Fil résistant, Épingles, Fer à repasser, Aiguille à jean',
            },
            {
                'numero': 5,
                'titre': 'Assemblage du corps principal',
                'description': (
                    'Positionnez la poche frontale sur le panneau avant et cousez le bas et les côtés à 2 mm. '
                    'Assemblez les pièces dans l\'ordre : flancs + fond, puis panneau avant, puis panneau arrière. '
                    'Travaillez endroit contre endroit à chaque assemblage. '
                    'Cousez avec fil résistant et point de longueur réduite (2 mm) pour plus de solidité. '
                    'Repassez les marges ouvertes au fur et à mesure.'
                ),
                'video_url': None,
                'conseil': (
                    'Pour les coutures sous tension, faites deux passes parallèles à 2 mm d\'écart '
                    'plutôt qu\'une seule couture centrale : la résistance est doublée.'
                ),
                'materiaux_etape': 'Machine à coudre, Fil résistant, Épingles, Fer à repasser',
            },
            {
                'numero': 6,
                'titre': 'Pose de la fermeture principale et des sangles',
                'description': (
                    'Posez la grande fermeture éclair d\'ouverture principale en haut du sac, '
                    'entre les deux panneaux. Travaillez méthodiquement, endroit contre endroit. '
                    'Fixez les bretelles sur le panneau arrière : piquez solidement en X renforcé, '
                    'puis renforcez avec des rivets métalliques aux quatre points de contrainte. '
                    'Fixez la sangle de poignée en haut du sac avec des rivets.'
                ),
                'video_url': None,
                'conseil': (
                    'Pour poser les rivets, utilisez un marteau et une surface dure. '
                    'Percez le trou légèrement plus petit que le rivet pour un maintien parfait.'
                ),
                'materiaux_etape': 'Pied zipper, Machine à coudre, Fil résistant, Marteau, Pince-rivets',
            },
            {
                'numero': 7,
                'titre': 'Finitions et contrôle qualité',
                'description': (
                    'Retournez le sac et inspectez toutes les coutures intérieures. '
                    'Surfilez ou surjetez les marges de couture intérieures pour éviter l\'effilochage '
                    'et prolonger la durée de vie du sac. '
                    'Renforcez les angles du fond avec des coutures triangulaires. '
                    'Testez le sac en le chargeant à 5 kg pour vérifier que tous les points d\'attache résistent. '
                    'Repassez et placez une forme gonflante à l\'intérieur pour lui donner sa structure.'
                ),
                'video_url': None,
                'conseil': (
                    'Traitez l\'extérieur du sac avec une cire d\'imperméabilisation en spray '
                    'pour protéger le tissu de la pluie sans changer son aspect.'
                ),
                'materiaux_etape': 'Machine à coudre, Ciseaux, Fer à repasser',
            },
        ],
        'tutoriels': [
            {
                'titre': 'Sac à dos DIY complet — tutoriel avancé',
                'typeTutoriel': 'video',
                'urlVideoOuArticle': 'https://www.youtube.com/watch?v=BaSmyabj9Hk',
                'source': 'YouTube',
                'description': 'Tutoriel en plusieurs parties couvrant la construction complète d\'un sac à dos structuré avec toutes les astuces de renforcement.',
            },
            {
                'titre': 'Patron sac à dos PDF avec gabarits',
                'typeTutoriel': 'pdf',
                'urlVideoOuArticle': 'https://www.sewmamasew.com/patterns/backpack.pdf',
                'source': 'Sew Mama Sew',
                'description': 'Patron professionnel avec gabarits imprimables, liste de fournitures et guide d\'assemblage illustré.',
            },
        ],
    },

    {
        'titre': 'Veste kimono bohème',
        'description': (
            'Veste légère et fluide au style kimono, avec de larges manches droites et un tombé élégant. '
            'Ce patron de niveau intermédiaire demande des tissus souples et légers : '
            'viscose, voile de coton, mousseline ou tissu de chemise fin. '
            'Idéal pour valoriser une nappe ou un rideau léger en lin ou en coton.'
        ),
        'typeObjet': 'Vêtement',
        'surfaceMin': 1.5,
        'surfaceMax': 2.5,
        'estPremium': False,
        'difficulte': 2,
        'duree': '4h',
        'materiel': (
            'Ciseaux, Machine à coudre, Fil, Épingles, Ruban à mesurer, '
            'Fer à repasser, Mètre ruban, Craie de couture'
        ),
        'matiere_requise': 'viscose,voile,mousseline,lin',
        'photo_url': 'https://images.unsplash.com/photo-1509631179647-0177331693ae?w=800&h=600&fit=crop&q=80',
        'photo_name': 'patron_veste_kimono.jpg',
        'cloudinary_url': 'https://res.cloudinary.com/dh1i1pzbv/image/upload/v1780491745/patrons/patron_veste_kimono.jpg',
        'etapes': [
            {
                'numero': 1,
                'titre': 'Prise de mesures et tracé du patron',
                'description': (
                    'Prenez les mesures suivantes : tour de poitrine + 20 cm (aisance), '
                    'longueur épaule-poignet, longueur épaule-genou (ou longueur souhaitée), '
                    'largeur d\'épaule. '
                    'Tracez le patron en T sur papier kraft : '
                    'corps central (largeur = tour poitrine/2 + 10 cm, hauteur = longueur voulue), '
                    'manches rectangulaires (45 cm de large × longueur bras). '
                    'Ajoutez 2 cm de marge partout.'
                ),
                'video_url': None,
                'conseil': (
                    'Le kimono est un vêtement très indulgent : les tolérances sont larges '
                    'et le patron peut être adapté en quelques traits de craie. '
                    'Commencez toujours par un test en tissu bon marché.'
                ),
                'materiaux_etape': 'Craie de couture, Mètre ruban, Règle, Ciseau à papier',
            },
            {
                'numero': 2,
                'titre': 'Découpe du tissu',
                'description': (
                    'Pliez le tissu en deux dans le sens de la longueur, endroit contre endroit. '
                    'Placez le patron en alignant le bord du milieu dos sur le pli du tissu. '
                    'Épinglez et découpez. Dépliez : vous obtenez le corps entier d\'un seul tenant. '
                    'Découpez les deux manches séparément. '
                    'Pour les tissus glissants, stabilisez-les avec des épingles serrées et des ciseaux bien aiguisés.'
                ),
                'video_url': 'https://www.youtube.com/watch?v=Qlbq5nOhBb0',
                'conseil': (
                    'Évitez de tirer sur les tissus fluides lors de la découpe : '
                    'posez-les à plat et utilisez des poids de couture plutôt que des épingles '
                    'pour ne pas les déformer.'
                ),
                'materiaux_etape': 'Ciseaux, Épingles, Craie de couture',
            },
            {
                'numero': 3,
                'titre': 'Assemblage des épaules et des côtés',
                'description': (
                    'Repliez le corps en deux au niveau des épaules, endroit contre endroit. '
                    'Cousez les coutures d\'épaule à 1,5 cm. Surjetez ou surfilez les marges. '
                    'Cousez les coutures de côté à 1,5 cm du bas de la manche jusqu\'en bas du vêtement '
                    'en laissant une fente de 15 cm en bas des côtés si souhaité. '
                    'Repassez toutes les marges vers le dos.'
                ),
                'video_url': None,
                'conseil': (
                    'Sur les tissus fluides, utilisez une aiguille fine (70/10) et un fil de polyester léger. '
                    'Rallongez légèrement le point de couture pour éviter les fronces.'
                ),
                'materiaux_etape': 'Machine à coudre, Fil, Épingles, Fer à repasser',
            },
            {
                'numero': 4,
                'titre': 'Pose des manches',
                'description': (
                    'Cousez les coutures de dessous de manche à 1,5 cm. Repassez ouvertes. '
                    'Glissez chaque manche dans l\'emmanchure correspondante, endroit contre endroit. '
                    'Alignez la couture sous-manche avec la couture de côté du corps. '
                    'Épinglez régulièrement et cousez à 1,5 cm. '
                    'Pour le kimono, les manches n\'ont pas de courbe d\'emmanchure — c\'est une couture droite simple.'
                ),
                'video_url': None,
                'conseil': (
                    'La force du kimono est sa construction rectangulaire : '
                    'pas de courbes difficiles à assembler, juste des droites. '
                    'C\'est pour ça que c\'est parfait pour les tissus glissants.'
                ),
                'materiaux_etape': 'Machine à coudre, Fil, Épingles, Fer à repasser',
            },
            {
                'numero': 5,
                'titre': 'Réalisation du col et des revers',
                'description': (
                    'Coupez une bande de 8 cm de large pour le col/revers sur toute la longueur du devant + 40 cm de col. '
                    'Pliez-la en deux dans le sens de la longueur, repassez. '
                    'Épinglez la face extérieure sur l\'endroit du vêtement en commençant par le bas du devant '
                    'et en continuant dans le dos du col. Cousez à 1,5 cm. '
                    'Repliez vers l\'intérieur et cousez au point glissé ou surpiquez depuis l\'endroit.'
                ),
                'video_url': None,
                'conseil': (
                    'Crantez les courbes du col au niveau du virage dos/devant tous les 5 mm '
                    'pour que le col se pose à plat sans faire de boursouflures.'
                ),
                'materiaux_etape': 'Machine à coudre, Fil, Épingles, Ciseaux, Fer à repasser, Aiguille',
            },
            {
                'numero': 6,
                'titre': 'Ourlets et finitions décoratives',
                'description': (
                    'Faites un ourlet de 1 cm roulotté (plié deux fois à 0,5 cm) sur les bas de manches. '
                    'Faites le même ourlet en bas du vêtement. '
                    'Optionnel : ajoutez des franges, du biais contrastant, '
                    'de la broderie ou des impressions au tampon pour personnaliser votre kimono. '
                    'Repassez une dernière fois à l\'envers avec un chiffon humide pour laisser le tissu respirer.'
                ),
                'video_url': None,
                'conseil': (
                    'Pour les ourlets de tissus très fins, l\'ourlet roulotté est le plus discret. '
                    'Faites-le à la machine avec un pied ourlet roulotté si vous en avez un.'
                ),
                'materiaux_etape': 'Machine à coudre, Fil, Fer à repasser',
            },
        ],
        'tutoriels': [
            {
                'titre': 'Veste kimono facile — patron gratuit',
                'typeTutoriel': 'article',
                'urlVideoOuArticle': 'https://www.burda-style.com/tutos/kimono-jacket',
                'source': 'Burda Style',
                'description': 'Guide complet avec patron gratuit en tailles 36 à 46, conseils sur les tissus fluides et variantes de longueur.',
            },
            {
                'titre': 'Kimono jacket tutorial — vidéo anglais',
                'typeTutoriel': 'video',
                'urlVideoOuArticle': 'https://www.youtube.com/watch?v=CfbVgG4JSJA',
                'source': 'YouTube',
                'description': 'Tutoriel en anglais (sous-titres disponibles) avec démonstration des coutures sur tissus glissants.',
            },
        ],
    },

    {
        'titre': 'Housse de coussin réversible',
        'description': (
            'Housse de coussin 50 × 50 cm avec système d\'ouverture enveloppe — aucune fermeture éclair nécessaire ! '
            'En cousant deux tissus complémentaires dos à dos, vous obtenez une housse réversible '
            'qui peut changer d\'aspect selon votre envie. '
            'Un projet idéal pour les tout débutants : prêt en moins d\'une heure.'
        ),
        'typeObjet': 'Coussin',
        'surfaceMin': 0.3,
        'surfaceMax': 0.6,
        'estPremium': False,
        'difficulte': 1,
        'duree': '45min',
        'materiel': 'Ciseaux, Machine à coudre, Fil, Épingles, Fer à repasser',
        'matiere_requise': '',
        'photo_url': 'https://images.unsplash.com/photo-1586023492125-27b2c045efd7?w=800&h=600&fit=crop&q=80',
        'photo_name': 'patron_housse_coussin.jpg',
        'cloudinary_url': 'https://res.cloudinary.com/dh1i1pzbv/image/upload/v1780491746/patrons/patron_housse_coussin.jpg',
        'etapes': [
            {
                'numero': 1,
                'titre': 'Découpe des panneaux',
                'description': (
                    'Pour une housse de 50 × 50 cm : découpez un panneau avant de 52 × 52 cm, '
                    'et deux panneaux arrière de 52 × 35 cm chacun. '
                    'Les deux panneaux arrière se chevauchent au centre pour créer l\'ouverture enveloppe. '
                    'Repassez tous les panneaux. '
                    'Pour une housse réversible : découpez les mêmes pièces dans un deuxième tissu.'
                ),
                'video_url': None,
                'conseil': (
                    'Ajoutez toujours 2 cm aux dimensions du coussin pour la housse : '
                    'la housse doit être légèrement ajustée pour que le coussin soit bien plein et ferme.'
                ),
                'materiaux_etape': 'Ciseaux, Craie de couture, Règle, Fer à repasser',
            },
            {
                'numero': 2,
                'titre': 'Ourlet des panneaux arrière et assemblage',
                'description': (
                    'Faites un ourlet double de 2 cm sur le bord central de chacun des deux panneaux arrière. '
                    'Posez le panneau avant endroit vers le haut. '
                    'Posez les deux panneaux arrière endroit vers le bas, les ourlets se chevauchant au centre. '
                    'Épinglez tout le tour. Cousez à 1,5 cm du bord tout autour. '
                    'Coupez les coins en biais à 2 mm de la couture.'
                ),
                'video_url': None,
                'conseil': (
                    'Le chevauchement des panneaux arrière doit faire au moins 10 cm pour que le coussin '
                    'reste en place. Si votre tissu est glissant, cousez un point d\'arrêt au centre du chevauchement.'
                ),
                'materiaux_etape': 'Machine à coudre, Fil, Épingles, Ciseaux',
            },
            {
                'numero': 3,
                'titre': 'Retournement et finitions',
                'description': (
                    'Retournez la housse à l\'endroit en passant par l\'ouverture enveloppe au dos. '
                    'Poussez bien les coins avec un stylo pour les former parfaitement. '
                    'Repassez tout le tour pour aplatir les coutures. '
                    'Glissez votre coussin de 50 × 50 cm à l\'intérieur. '
                    'La housse est prête — aucun point à faire à la main !'
                ),
                'video_url': None,
                'conseil': (
                    'Lavez la housse à froid à l\'envers pour préserver les couleurs. '
                    'Le système enveloppe permet de l\'enlever et la remettre en quelques secondes.'
                ),
                'materiaux_etape': 'Fer à repasser',
            },
        ],
        'tutoriels': [
            {
                'titre': 'Housse de coussin enveloppe — 3 étapes',
                'typeTutoriel': 'article',
                'urlVideoOuArticle': 'https://www.maison-victor.com/tutos/housse-coussin-enveloppe',
                'source': 'La Maison Victor',
                'description': 'Guide illustré avec photos pas à pas de chaque étape et variante pour housse avec liseré décoratif.',
            },
        ],
    },

    {
        'titre': 'Nécessaire de voyage à compartiments',
        'description': (
            'Trousse de toilette structurée avec soufflets, fermeture éclair principale et poche filet intérieure. '
            'Ce projet de niveau intermédiaire exploite les possibilités des tissus épais et résistants '
            'pour créer un accessoire pratique et durable. '
            'Ses soufflets latéraux lui donnent du volume tout en restant compact lorsqu\'il est vide.'
        ),
        'typeObjet': 'Trousse',
        'surfaceMin': 0.3,
        'surfaceMax': 0.6,
        'estPremium': True,
        'difficulte': 2,
        'duree': '2h30',
        'materiel': (
            'Ciseaux, Machine à coudre, Fil, Épingles, '
            'Dé à coudre, Règle, Craie de couture, Pied zipper'
        ),
        'matiere_requise': 'jean,toile,coton',
        'photo_url': 'https://images.unsplash.com/photo-1547949003-9792a18a2601?w=800&h=600&fit=crop&q=80',
        'photo_name': 'patron_necessaire_voyage.jpg',
        'cloudinary_url': 'https://res.cloudinary.com/dh1i1pzbv/image/upload/v1780491747/patrons/patron_necessaire_voyage.jpg',
        'etapes': [
            {
                'numero': 1,
                'titre': 'Découpe et préparation des pièces',
                'description': (
                    'Découpez les pièces suivantes : deux rectangles principaux de 35 × 22 cm (extérieur), '
                    'deux rectangles de 35 × 22 cm (doublure), deux bandes de soufflet de 8 × 55 cm, '
                    'et un rectangle de poche filet de 30 × 18 cm dans du tissu maille ou filet. '
                    'Thermocollez l\'interface sur l\'envers des pièces extérieures pour leur donner de la tenue. '
                    'Repassez toutes les pièces.'
                ),
                'video_url': None,
                'conseil': (
                    'Choisissez une interface semi-rigide (type Pellon 809) pour les pièces extérieures '
                    'afin que le nécessaire garde sa forme même vide.'
                ),
                'materiaux_etape': 'Ciseaux, Craie de couture, Règle, Fer à repasser',
            },
            {
                'numero': 2,
                'titre': 'Montage de la poche intérieure',
                'description': (
                    'Pliez le rectangle de poche en deux (18 × 15 cm une fois plié). '
                    'Cousez les trois côtés à 1 cm en laissant une ouverture de retournement. '
                    'Retournez et repassez. Positionnez la poche sur l\'endroit d\'un panneau de doublure, '
                    'centrez-la horizontalement à 5 cm du haut, et cousez trois côtés à 2 mm du bord '
                    '(le bord supérieur reste ouvert). '
                    'Ajoutez une cloison verticale cousue en faisant un trait du haut vers le bas.'
                ),
                'video_url': None,
                'conseil': (
                    'La poche intérieure peut être en filet pour voir les objets à l\'intérieur, '
                    'ou en tissu doublure coordonné pour un intérieur plus soigné.'
                ),
                'materiaux_etape': 'Machine à coudre, Fil, Épingles, Ciseaux, Fer à repasser',
            },
            {
                'numero': 3,
                'titre': 'Pose de la fermeture éclair principale',
                'description': (
                    'Posez la fermeture éclair entre le panneau extérieur et la doublure correspondante '
                    'en sandwich (tissu extérieur endroit vers le haut, zip face vers le bas, doublure endroit vers le bas). '
                    'Cousez à 0,7 cm avec le pied zipper. Repassez le tissu away du zip, surpiquez. '
                    'Répétez de l\'autre côté. Ouvrez le zip à mi-course avant de continuer.'
                ),
                'video_url': 'https://www.youtube.com/watch?v=_mFd8FHIZM4',
                'conseil': (
                    'Choisissez un zip de longueur = largeur du panneau + 4 cm. '
                    'Il dépassera légèrement sur les côtés — c\'est normal et se cachera dans les soufflets.'
                ),
                'materiaux_etape': 'Machine à coudre, Pied zipper, Fil, Épingles, Fer à repasser',
            },
            {
                'numero': 4,
                'titre': 'Assemblage avec soufflets',
                'description': (
                    'Cousez les deux bandes de soufflet en un seul anneau (les deux courts côtés ensemble). '
                    'Épinglez l\'anneau de soufflet sur le pourtour de l\'ensemble extérieur/doublure, '
                    'en alignant les coutures du soufflet avec les coins du sac. '
                    'Cousez tout le tour à 1 cm. '
                    'Crantez les courbes et les angles tous les 1 cm pour que le soufflet s\'aplat bien. '
                    'Retournez par l\'ouverture du zip.'
                ),
                'video_url': None,
                'conseil': (
                    'Faites des crans (petites entailles à 3 mm de la couture) dans les angles arrondis '
                    'pour permettre au soufflet de se courber sans faire de plis.'
                ),
                'materiaux_etape': 'Machine à coudre, Fil, Épingles, Ciseaux',
            },
            {
                'numero': 5,
                'titre': 'Finitions et poignée',
                'description': (
                    'Découpez une bande de 4 × 16 cm pour la poignée. '
                    'Pliez-la en quatre dans le sens de la longueur, surpiquez les deux bords. '
                    'Passez-la dans un anneau et cousez les deux extrémités ensemble. '
                    'Fixez l\'anneau avec poignée sur le haut du soufflet par une couture en X solide. '
                    'Inspectez toutes les coutures, coupez les fils, repassez à froid sur l\'extérieur.'
                ),
                'video_url': None,
                'conseil': (
                    'Ajoutez un anneau de porte-clé à l\'intérieur pour ne jamais perdre vos clés '
                    'au fond du sac de voyage !'
                ),
                'materiaux_etape': 'Machine à coudre, Fil, Épingles, Ciseaux, Fer à repasser',
            },
        ],
        'tutoriels': [
            {
                'titre': 'Trousse de toilette avec soufflets — tutoriel vidéo',
                'typeTutoriel': 'video',
                'urlVideoOuArticle': 'https://www.youtube.com/watch?v=_mFd8FHIZM4',
                'source': 'YouTube',
                'description': 'Tutoriel complet avec démonstration de la technique des soufflets et de la pose de la fermeture éclair sur tissu épais.',
            },
            {
                'titre': 'Trousse imperméable DIY — article avec patrons',
                'typeTutoriel': 'article',
                'urlVideoOuArticle': 'https://www.couturefacile.com/tutos/trousse-soufflets',
                'source': 'Couture Facile',
                'description': 'Guide illustré avec variantes imperméables et conseils pour l\'utilisation de tissu enduit ou ciré.',
            },
        ],
    },

    {
        'titre': 'Bandeau et sachet senteur upcyclé',
        'description': (
            'Duo de petites créations rapides et anti-gaspi : un bandeau cheveux élastique '
            'et un sachet senteur lavande pour les tiroirs. '
            'Ces deux mini-projets sont parfaits pour valoriser les toutes petites chutes de tissu '
            'et offrir de jolis cadeaux zéro déchet faits main. '
            'Idéal comme premier projet de couture ou pour initier les enfants.'
        ),
        'typeObjet': 'Accessoire',
        'surfaceMin': 0.05,
        'surfaceMax': 0.2,
        'estPremium': False,
        'difficulte': 1,
        'duree': '30min',
        'materiel': 'Ciseaux, Machine à coudre (ou aiguille à la main), Fil, Épingles, Épingle de sûreté',
        'matiere_requise': '',
        'photo_url': 'https://images.unsplash.com/photo-1558618666-fcd25c85cd64?w=800&h=600&fit=crop&q=80',
        'photo_name': 'patron_bandeau_sachet.jpg',
        'cloudinary_url': 'https://res.cloudinary.com/dh1i1pzbv/image/upload/v1780491748/patrons/patron_bandeau_sachet.jpg',
        'etapes': [
            {
                'numero': 1,
                'titre': 'Découpe des pièces (bandeau et sachet)',
                'description': (
                    'Pour le bandeau : découpez une bande de 18 × 48 cm et une bande élastique de 12 cm. '
                    'Pour le sachet : découpez deux rectangles de 12 × 15 cm. '
                    'Ces formats sont pour adulte — réduisez de 20 % pour un bandeau enfant. '
                    'Choisissez des tissus souples et confortables pour le bandeau '
                    '(jersey, velours côtelé, flanelle) et n\'importe quel tissu pour le sachet.'
                ),
                'video_url': None,
                'conseil': (
                    'Le sens du tissu compte pour le bandeau : la direction extensible doit être '
                    'dans le sens de la longueur du bandeau pour qu\'il s\'adapte à la tête.'
                ),
                'materiaux_etape': 'Ciseaux, Craie de couture, Règle',
            },
            {
                'numero': 2,
                'titre': 'Confection du bandeau cheveux',
                'description': (
                    'Pliez la bande en deux dans le sens de la longueur, endroit contre endroit. '
                    'Cousez le long côté à 1 cm. Retournez à l\'endroit. '
                    'Glissez l\'élastique à l\'intérieur avec une épingle de sûreté. '
                    'Épinglez les deux extrémités du tube tissu ensemble (élastique à l\'intérieur). '
                    'Cousez les extrémités à 1 cm en prenant l\'élastique dans la couture. '
                    'Tournez la jointure vers l\'intérieur du bandeau et cousez-la discrètement.'
                ),
                'video_url': None,
                'conseil': (
                    'Si vous n\'avez pas d\'élastique, utilisez un lien de tissu plus long '
                    'pour faire un bandeau à nouer — encore plus personnalisable !'
                ),
                'materiaux_etape': 'Machine à coudre, Fil, Épingle de sûreté, Ciseaux',
            },
            {
                'numero': 3,
                'titre': 'Confection du sachet senteur',
                'description': (
                    'Placez les deux rectangles endroit contre endroit et cousez trois côtés à 1 cm, '
                    'en laissant le côté court du haut ouvert. '
                    'Crantez les coins, retournez à l\'endroit. '
                    'Remplissez de fleurs de lavande séchées, de pot-pourri ou d\'écorces de cèdre. '
                    'Repliez le bord supérieur de 1 cm vers l\'intérieur et cousez à la main au point glissé, '
                    'ou nouez avec un joli ruban.'
                ),
                'video_url': None,
                'conseil': (
                    'Ajoutez quelques gouttes d\'huile essentielle de lavande sur les fleurs '
                    'avant de fermer pour une senteur plus intense et durable.'
                ),
                'materiaux_etape': 'Aiguille, Fil, Ciseaux',
            },
        ],
        'tutoriels': [
            {
                'titre': 'Bandeau cheveux couture — tutoriel rapide',
                'typeTutoriel': 'video',
                'urlVideoOuArticle': 'https://www.youtube.com/watch?v=Qlbq5nOhBb0',
                'source': 'YouTube',
                'description': 'Tutoriel de 10 minutes pour réaliser un bandeau élastique élégant, idéal pour les débutants.',
            },
        ],
    },
]


def download_image(url):
    """Télécharge une image depuis une URL et retourne les octets en mémoire."""
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as response:
            return response.read()
    except Exception:
        return None


class Command(BaseCommand):
    help = 'Supprime tous les patrons existants et peuple la BDD avec les patrons de démonstration'

    def _apply_cloudinary_urls(self):
        """Force les URLs Cloudinary sur les patrons existants, par titre."""
        updated = 0
        for data in PATRONS_DATA:
            cld_url = data.get('cloudinary_url')
            if cld_url:
                n = Patron.objects.filter(titre=data['titre']).update(photo=cld_url)
                updated += n
        self.stdout.write(self.style.SUCCESS(
            f'  {updated} photo(s) patron mise(s) a jour avec URLs Cloudinary.'
        ))

    def handle(self, *args, **options):
        existing = Patron.objects.all()
        if existing.exists():
            cloudinary_photos = [
                p for p in existing
                if p.photo and 'res.cloudinary.com' in str(p.photo.name)
            ]
            if len(cloudinary_photos) == existing.count():
                self.stdout.write(self.style.SUCCESS(
                    f'  {existing.count()} patrons avec photos Cloudinary detectes — skip.'
                ))
                return
            # Patrons présents mais photos incorrectes : correction sans suppression
            expected_titles = {d['titre'] for d in PATRONS_DATA}
            if expected_titles.issubset(set(existing.values_list('titre', flat=True))):
                self.stdout.write('  Photos patrons incorrectes — correction en cours...')
                self._apply_cloudinary_urls()
                return

        self.stdout.write('Suppression des patrons existants...')
        for patron in Patron.objects.all():
            if patron.photo:
                try:
                    patron.photo.delete(save=False)
                except Exception:
                    pass
        Patron.objects.all().delete()
        self.stdout.write(self.style.WARNING('  Tous les patrons supprimés.'))

        media_dir = os.path.join(settings.MEDIA_ROOT, 'patrons')
        os.makedirs(media_dir, exist_ok=True)
        # Nettoyage de toutes les images patrons existantes
        for fname in os.listdir(media_dir):
            try:
                os.remove(os.path.join(media_dir, fname))
            except Exception:
                pass

        with transaction.atomic():
            for i, data in enumerate(PATRONS_DATA, 1):
                self.stdout.write(f'  Création du patron {i}/{len(PATRONS_DATA)} : {data["titre"]}...')

                patron = Patron(
                    titre=data['titre'],
                    description=data['description'],
                    typeObjet=data['typeObjet'],
                    surfaceMin=data['surfaceMin'],
                    surfaceMax=data['surfaceMax'],
                    estPremium=data['estPremium'],
                    difficulte=data['difficulte'],
                    duree=data['duree'],
                    materiel=data['materiel'],
                    matiere_requise=data.get('matiere_requise', ''),
                )

                photo_url = data.get('photo_url')
                photo_name = data.get('photo_name')
                if photo_url and photo_name:
                    img_data = download_image(photo_url)
                    if img_data:
                        patron.photo.save(photo_name, ContentFile(img_data), save=False)
                        self.stdout.write(f'    Image telechargee : {photo_name}')
                    else:
                        self.stdout.write(self.style.WARNING(f'    Image non telechargee pour {data["titre"]}'))

                patron.save()

                for etape_data in data.get('etapes', []):
                    EtapePatron.objects.create(
                        patron=patron,
                        numero=etape_data['numero'],
                        titre=etape_data['titre'],
                        description=etape_data['description'],
                        video_url=etape_data.get('video_url') or None,
                        conseil=etape_data.get('conseil', ''),
                        materiaux_etape=etape_data.get('materiaux_etape', ''),
                    )

                for tuto_data in data.get('tutoriels', []):
                    Tutoriel.objects.create(
                        patron=patron,
                        titre=tuto_data['titre'],
                        typeTutoriel=tuto_data['typeTutoriel'],
                        urlVideoOuArticle=tuto_data['urlVideoOuArticle'],
                        source=tuto_data['source'],
                        description=tuto_data.get('description', ''),
                    )

                nb_etapes = len(data.get('etapes', []))
                nb_tutos = len(data.get('tutoriels', []))
                self.stdout.write(
                    self.style.SUCCESS(f'    OK {data["titre"]} -- {nb_etapes} etapes, {nb_tutos} tutoriels')
                )

        # Nettoyage final : supprime les fichiers non référencés en BDD
        referenced = set(
            os.path.basename(p.photo.name)
            for p in Patron.objects.all() if p.photo
        )
        for fname in os.listdir(media_dir):
            if fname not in referenced:
                try:
                    os.remove(os.path.join(media_dir, fname))
                except Exception:
                    pass

        self._apply_cloudinary_urls()
        self.stdout.write(self.style.SUCCESS(
            f'\n{len(PATRONS_DATA)} patrons crees avec succes !'
        ))
