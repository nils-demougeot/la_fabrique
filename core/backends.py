from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend


class EmailOrUsernameBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        UserModel = get_user_model()

        # username peut arriver à None (certains flux d'auth). On évite le TypeError.
        if username is None:
            username = kwargs.get(UserModel.USERNAME_FIELD)
        if username is None or password is None:
            return None

        try:
            if '@' in username:
                user = UserModel.objects.get(email__iexact=username)
            else:
                user = UserModel.objects.get(username=username)
        except UserModel.DoesNotExist:
            # On exécute quand même le hachage du mot de passe pour ne pas révéler
            # par le temps de réponse si l'utilisateur existe (anti-énumération).
            UserModel().set_password(password)
            return None
        except UserModel.MultipleObjectsReturned:
            return None

        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
