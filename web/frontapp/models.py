from django.contrib.auth.models import AbstractUser ,Group, Permission
from django.db import models
from django.db.models import JSONField


class CustomUser(AbstractUser):
    display_name = models.CharField(max_length=255, null=True, blank=True)
    avatar = models.URLField(max_length=200, null=True, blank=True)
    stats = JSONField(default=dict, null=True, blank=True )
    match_history = JSONField(default=list,  null=True, blank=True)
    two_factor_auth_enabled = models.BooleanField(default=False)
    last_active = models.DateTimeField(null=True, blank=True)

    groups = models.ManyToManyField(
        'auth.Group',
        related_name='customuser_set',
        blank=True,
        help_text='The groups this user belongs to.',
        verbose_name='groups'
    )
    user_permissions = models.ManyToManyField(
        'auth.Permission',
        related_name='customuser_set',
        blank=True,
        help_text='Specific permissions for this user.',
        verbose_name='user permissions'
    )

    def get_friends(self):
        accepted_friendships = self.friendships_sent.filter(accepted=True) | self.friendships_received.filter(accepted=True)

        friends = [friendship.to_user for friendship in accepted_friendships if friendship.to_user != self] + \
                [friendship.from_user for friendship in accepted_friendships if friendship.from_user != self]

        return friends

    def get_pending_friend_requests(self):

        pending_friendships = self.friendships_received.filter(accepted=False)

        pending_friends = [friendship.from_user for friendship in pending_friendships]

        return pending_friends

    def add_friend_request(self, new_friend):
        if new_friend != self:
            if new_friend not in self.get_friends():
                friendship = Friendship(from_user=self, to_user=new_friend, accepted=False)
                friendship.save()
                return True
        return False

    def accept_friend_request(self, friend):
        friendship = self.friendships_received.filter(from_user=friend).first()

        if friendship:
            friendship.accepted = True
            friendship.save()
            return True
        return False

    def remove_friend(self, friend):
        friendship = self.friendships_sent.filter(to_user=friend).first() or self.friendships_received.filter(from_user=friend).first()

        if friendship:
            friendship.delete()
            return True
        return False


    def __str__(self):
        return self.username

    class Meta:
        db_table = 'auth_user'


class CustomUserGroup(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    group = models.ForeignKey(Group, on_delete=models.CASCADE)

class CustomUserPermission(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    permission = models.ForeignKey(Permission, on_delete=models.CASCADE)

class Friendship(models.Model):
    from_user = models.ForeignKey(CustomUser, related_name='friendships_sent', on_delete=models.CASCADE)
    to_user = models.ForeignKey(CustomUser, related_name='friendships_received', on_delete=models.CASCADE)
    accepted = models.BooleanField(default=False)
    popup_shown = models.BooleanField(default=False)
    class Meta:
        unique_together = ('from_user', 'to_user')


class Game(models.Model):
    game_id = models.AutoField(primary_key=True)
    player1 = models.ForeignKey(CustomUser, on_delete=models.PROTECT, related_name='player1')
    player2 = models.ForeignKey(CustomUser, on_delete=models.PROTECT, related_name='player2')
    p1_wins = models.IntegerField(default=0)
    p2_wins = models.IntegerField(default=0)
    winner = models.ForeignKey(CustomUser, on_delete=models.PROTECT, related_name='winner')

    date = models.DateTimeField(auto_now_add=True)

    def to_dict(self):
        return {
            'game_id': self.game_id,
            'player1': self.player1.username,
            'player2': self.player2.username,
            'p1_wins': self.p1_wins,
            'p2_wins': self.p2_wins,
            'winner': self.winner.username,
            'date': self.date.strftime('%Y-%m-%d %H:%M:%S'),
        }

    def __str__(self):
      return self.player1.username + " vs " + self.player2.username + " (" + self.winner.username + ")"


class Tournament(models.Model):
    id = models.AutoField(primary_key=True)
    creator = models.ForeignKey(CustomUser, on_delete=models.PROTECT, related_name='creator')
    name = models.CharField(max_length=40)
    number_of_players = models.IntegerField(default=0)
    start_time = models.DateTimeField(auto_now_add=True)
    winner = models.ForeignKey(CustomUser, on_delete=models.PROTECT, related_name='tournament_winner', null=True)
    players = models.ManyToManyField(CustomUser, related_name='players')
    status = models.CharField(max_length=40, default='waiting')
    class Status(models.TextChoices):
        WAITING = 'waiting', 'Waiting'
        ONGOING = 'ongoing', 'Ongoing'
        COMPLETED = 'completed', 'Completed'
        FAILED = 'failed', 'Failed'

    status = models.CharField(
        max_length=40,
        choices=Status.choices,
        default=Status.WAITING,
    )

    def to_dict(self):
        return {
            'name': self.name,
            'id': self.id,
            'creator': self.creator.username,
            'number_of_players': self.number_of_players,
            'free_slots': self.number_of_players - self.players.count(),
            'start_time': self.start_time.strftime('%Y-%m-%d %H:%M:%S'),
            'winner': self.winner.username if self.winner else None,
            'players': [player.username for player in self.players.all()],
            'status': self.status,
        }

    def __str__(self):
      return self.name

