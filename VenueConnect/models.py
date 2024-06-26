from django.conf import settings
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.core.mail import EmailMessage
from django.db import models
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from django.utils.translation import gettext_lazy as _

from .utils import Calendar, email_verification_token, TimeRange


class UserManager(BaseUserManager):
    def create_user(self,
                    username,
                    email,
                    password,
                    first_name,
                    last_name,
                    phone_number,
                    **extra_fields):
        if not email:
            raise ValueError(_('The Email must be set'))
        email = self.normalize_email(email)
        user = self.model(
            username=username,
            email=email,
            first_name=first_name,
            last_name=last_name,
            phone_number=phone_number,
            **extra_fields)
        user.set_password(password)
        user.email_is_verified = False
        user.save()
        return user

    def create_superuser(self, username, email, password, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)
        if extra_fields.get('is_staff') is not True:
            raise ValueError(_('Superuser must have is_staff=True.'))
        if extra_fields.get('is_superuser') is not True:
            raise ValueError(_('Superuser must have is_superuser=True.'))
        return self.create_user(username, email, password, **extra_fields)


class User(AbstractUser):
    # By default, django includes:
    # first_name instead of name
    # last_name
    # email

    # we have to extend the model by the phone number:
    phone_number = models.IntegerField(null=True)

    email = models.EmailField(unique=True)
    email_verified = models.BooleanField(default=False)

    @staticmethod
    def register(username,
                 email,
                 password,
                 first_name='',
                 last_name='',
                 phone_number=None):
        return User.objects.create_user(username=username,
                                        password=password,
                                        first_name=first_name,
                                        last_name=last_name,
                                        email=email,
                                        phone_number=phone_number)

    def send_verification_email(self, request_scheme, domain):
        subject = "Verify Email"
        message = render_to_string('verify_email_msg.html', {
            'request_scheme': request_scheme,
            'user': self,
            'domain': domain,
            'uid': urlsafe_base64_encode(force_bytes(self.pk)),
            'token': email_verification_token.make_token(self),
        })
        email = EmailMessage(
            subject, message, to=[self.email]
        )
        email.content_subtype = 'html'
        email.send()

    def make_booking(self, venue: 'Venue', time: TimeRange):
        if venue.check_availability(time.start_time,time.end_time):
            booking_order = BookingOrder(
                user=self,
                start_time=time.start_time,
                end_time=time.end_time,
                venue=venue,
                price=venue.reserve_venue(time.start_time, time.end_time)
            )
            booking_order.save()
            return True
        else:
            return False

    def cancel_booking(self):
        self.booking_order.delete()

    def browse_venues(self, requested_capacity: int, requested_address: str):
        return Venue.objects.filter(capacity=requested_capacity, address=requested_address)

    def rate_venue(self, chosen_venue: 'Venue', description: str, feedback: int):
        if feedback not in range(1, 11):
            return False
        review = Review()
        review.venue = chosen_venue
        review.author = self
        review.review = description
        review.feedback = feedback
        review.save()
        return True

    def message_user(self, subject: str, receiver_email: str, message: str):
        if len(message) not in range(200, 5001) or len(subject) not in range(1, 51):
            return False
        email = EmailMessage(subject, message, from_email=self.email, to=receiver_email)
        email.content_subtype = 'html'
        email.send()
        return True


class VenueType(models.TextChoices):
    CONCERT_HALL = 'CH', 'Concert Hall'
    SPORTS_ARENA = 'SA', 'Sports Arena'
    THEATER = 'TH', 'Theater'
    CONFERENCE_ROOM = 'CR', 'Conference Room'
    OPEN_AIR = 'OA', 'Open Air'


class Venue(models.Model):
    venue_name = models.CharField(max_length=100)
    address = models.CharField(max_length=100)
    price_per_day = models.IntegerField(default=0)
    venue_type = models.CharField(
        max_length=2,
        choices=VenueType.choices,
        default=VenueType.CONCERT_HALL,
    )
    capacity = models.IntegerField()

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='owned_venues'
    )
    availabilityCalendar = Calendar()

    def check_availability(self, time):
        return self.availabilityCalendar.check_availability(time)

    def check_availability(self, start_time, end_time):
        return self.availabilityCalendar.check_availability(start_time, end_time)

    def reserve_venue(self, start_time, end_time):
        days = self.availabilityCalendar.reserve(start_time, end_time)
        self.save()
        return days * self.price_per_day

    def remove_venue(self):
        self.delete()

    def update_venue_details(self, *,
                             venue_name=None,
                             address=None,
                             venue_type=None,
                             capacity=None,
                             owner=None):
        if venue_name is not None:
            self.venue_name = venue_name
        if address is not None:
            self.address = address
        if venue_type is not None:
            self.venue_type = venue_type
        if capacity is not None:
            self.capacity = int(capacity)
        if owner is not None:
            self.owner = owner
        self.save()


class Review(models.Model):
    venue = models.ForeignKey(Venue, on_delete=models.CASCADE, related_name='review')
    feedback = models.IntegerField(default=0)
    review = models.TextField(max_length=500)
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name='review', default=0)


class BookingOrder(models.Model):
    start_time = models.DateTimeField(default=timezone.now)
    end_time = models.DateTimeField(default=timezone.now)
    price = models.IntegerField(default=0)
    venue = models.ForeignKey(Venue, on_delete=models.CASCADE, related_name='booking_order', )
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='booking_order', default=0)

    # the spec talks about the 'paymentID' attribute, but since the payment processing
    # has been scrapped, it was skipped


class Advertisement(models.Model):
    title = models.CharField(max_length=100)
    description = models.TextField()
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='advertisement')
    is_active = models.BooleanField()
    venue = models.ForeignKey(Venue, on_delete=models.CASCADE, related_name='advertisement')

    @staticmethod
    def filter(
            venue_type=None,
            min_price=None,
            max_price=None,
            min_capacity=None,
            max_capacity=None,
            available_from=None,
            available_to=None
    ):
        ads = Advertisement.objects.filter(is_active=True)
        return_ads = []
        for ad in ads:
            v = ad.venue
            if venue_type and v.venue_type != venue_type:
                continue
            if min_price and v.price_per_day < min_price:
                continue
            if max_price and v.price_per_day > max_price:
                continue
            if min_capacity and v.capacity < min_capacity:
                continue
            if max_capacity and v.capacity > max_capacity:
                continue
            if available_from and available_to and not v.check_available(available_from, available_from, available_to):
                continue
            if available_to and not v.check_available(available_from):
                continue
            if available_to and not v.check_available(available_to):
                continue
            return_ads.append(ad)

        return return_ads