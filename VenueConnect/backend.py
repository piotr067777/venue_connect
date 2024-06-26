from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.db.models import Q


class NameAuthenticationBackend(ModelBackend):
    def authenticate(self, request, first_name=None, last_name=None, password=None, **kwargs):
        user_model = get_user_model()
        try:
            user = user_model.objects.get(Q(first_name=first_name), Q(last_name=last_name))
            return user if user.check_password(password) else None
        except user_model.DoesNotExist:
            return None
