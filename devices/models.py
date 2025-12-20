from django.db import models
from django.utils import timezone


class Terminal(models.Model):
    """Terminal biométrique TM20-WIFI"""
    
    sn = models.CharField(
        max_length=50,
        unique=True,
        db_index=True,
        verbose_name="Numéro de série"
    )
    cpusn = models.CharField(
        max_length=50,
        blank=True,
        verbose_name="Numéro de série CPU"
    )
    model = models.CharField(
        max_length=50,
        blank=True,
        verbose_name="Modèle"
    )
    firmware = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="Firmware"
    )
    mac_address = models.CharField(
        max_length=17,
        blank=True,
        verbose_name="Adresse MAC"
    )
    
    user_capacity = models.IntegerField(default=3000, verbose_name="Capacité utilisateurs")
    fp_capacity = models.IntegerField(default=3000, verbose_name="Capacité empreintes")
    card_capacity = models.IntegerField(default=3000, verbose_name="Capacité cartes")
    log_capacity = models.IntegerField(default=100000, verbose_name="Capacité logs")
    
    used_users = models.IntegerField(default=0, verbose_name="Utilisateurs utilisés")
    used_fp = models.IntegerField(default=0, verbose_name="Empreintes utilisées")
    used_cards = models.IntegerField(default=0, verbose_name="Cartes utilisées")
    used_logs = models.IntegerField(default=0, verbose_name="Logs utilisés")
    
    fp_algo = models.CharField(
        max_length=50,
        blank=True,
        verbose_name="Algorithme empreinte"
    )
    
    last_seen = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Dernière connexion"
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="Actif"
    )
    is_whitelisted = models.BooleanField(
        default=True,
        verbose_name="En liste blanche"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'tm20_terminals'
        verbose_name = "Terminal"
        verbose_name_plural = "Terminaux"
        ordering = ['-last_seen']
    
    def __str__(self):
        return f"{self.model or 'TM20'} - {self.sn}"
    
    def update_last_seen(self):
        self.last_seen = timezone.now()
        self.save(update_fields=['last_seen'])


class BiometricUser(models.Model):
    """Utilisateur biométrique enregistré sur un terminal"""
    
    ADMIN_CHOICES = [
        (0, 'Utilisateur normal'),
        (1, 'Administrateur'),
        (2, 'Super utilisateur'),
    ]
    
    terminal = models.ForeignKey(
        Terminal,
        on_delete=models.CASCADE,
        related_name='users',
        verbose_name="Terminal"
    )
    enrollid = models.IntegerField(
        db_index=True,
        verbose_name="ID d'enrôlement"
    )
    name = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="Nom"
    )
    admin = models.IntegerField(
        choices=ADMIN_CHOICES,
        default=0,
        verbose_name="Niveau admin"
    )
    is_enabled = models.BooleanField(
        default=True,
        verbose_name="Activé"
    )
    
    weekzone = models.IntegerField(default=1, verbose_name="Zone semaine 1")
    weekzone2 = models.IntegerField(default=1, verbose_name="Zone semaine 2")
    weekzone3 = models.IntegerField(default=1, verbose_name="Zone semaine 3")
    weekzone4 = models.IntegerField(default=1, verbose_name="Zone semaine 4")
    group = models.IntegerField(default=0, verbose_name="Groupe")
    
    starttime = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Date de début validité"
    )
    endtime = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Date de fin validité"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'tm20_biometric_users'
        verbose_name = "Utilisateur biométrique"
        verbose_name_plural = "Utilisateurs biométriques"
        unique_together = ['terminal', 'enrollid']
        ordering = ['enrollid']
    
    def __str__(self):
        return f"{self.name or f'User#{self.enrollid}'} ({self.terminal.sn})"


class BiometricCredential(models.Model):
    """Credentials biométriques (empreintes, cartes, mots de passe, visages)"""
    
    BACKUP_TYPES = [
        (0, 'Empreinte 1'),
        (1, 'Empreinte 2'),
        (2, 'Empreinte 3'),
        (3, 'Empreinte 4'),
        (4, 'Empreinte 5'),
        (5, 'Empreinte 6'),
        (6, 'Empreinte 7'),
        (7, 'Empreinte 8'),
        (8, 'Empreinte 9'),
        (9, 'Empreinte 10'),
        (10, 'Mot de passe'),
        (11, 'Carte RFID'),
        (20, 'Visage statique 1'),
        (21, 'Visage statique 2'),
        (22, 'Visage statique 3'),
        (23, 'Visage statique 4'),
        (24, 'Visage statique 5'),
        (25, 'Visage statique 6'),
        (26, 'Visage statique 7'),
        (27, 'Visage statique 8'),
        (30, 'Paume 1'),
        (31, 'Paume 2'),
        (32, 'Paume 3'),
        (33, 'Paume 4'),
        (34, 'Paume 5'),
        (35, 'Paume 6'),
        (36, 'Paume 7'),
        (37, 'Paume 8'),
        (50, 'Photo'),
    ]
    
    user = models.ForeignKey(
        BiometricUser,
        on_delete=models.CASCADE,
        related_name='credentials',
        verbose_name="Utilisateur"
    )
    backupnum = models.IntegerField(
        choices=BACKUP_TYPES,
        verbose_name="Type de credential"
    )
    record = models.TextField(
        verbose_name="Données (base64 ou valeur)"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'tm20_biometric_credentials'
        verbose_name = "Credential biométrique"
        verbose_name_plural = "Credentials biométriques"
        unique_together = ['user', 'backupnum']
    
    def __str__(self):
        return f"{self.get_backupnum_display()} - {self.user}"
    
    @property
    def is_fingerprint(self):
        return 0 <= self.backupnum <= 9
    
    @property
    def is_password(self):
        return self.backupnum == 10
    
    @property
    def is_card(self):
        return self.backupnum == 11
    
    @property
    def is_face(self):
        return 20 <= self.backupnum <= 27
    
    @property
    def is_palm(self):
        return 30 <= self.backupnum <= 37


class AttendanceLog(models.Model):
    """Journal de pointage"""
    
    MODE_CHOICES = [
        (0, 'Empreinte'),
        (1, 'Carte'),
        (2, 'Mot de passe'),
        (3, 'Carte'),
        (8, 'Visage'),
        (13, 'QR Code'),
    ]
    
    INOUT_CHOICES = [
        (0, 'Entrée'),
        (1, 'Sortie'),
    ]
    
    EVENT_CHOICES = [
        (0, 'Normal'),
        (1, 'F1'),
        (2, 'F2'),
        (3, 'F3'),
        (4, 'F4'),
    ]
    
    terminal = models.ForeignKey(
        Terminal,
        on_delete=models.CASCADE,
        related_name='logs',
        verbose_name="Terminal"
    )
    user = models.ForeignKey(
        BiometricUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='logs',
        verbose_name="Utilisateur"
    )
    enrollid = models.IntegerField(
        db_index=True,
        verbose_name="ID d'enrôlement"
    )
    
    time = models.DateTimeField(
        db_index=True,
        verbose_name="Date/heure pointage"
    )
    mode = models.IntegerField(
        choices=MODE_CHOICES,
        default=0,
        verbose_name="Mode de vérification"
    )
    inout = models.IntegerField(
        choices=INOUT_CHOICES,
        default=0,
        verbose_name="Entrée/Sortie"
    )
    event = models.IntegerField(
        choices=EVENT_CHOICES,
        default=0,
        verbose_name="Événement"
    )
    
    temperature = models.DecimalField(
        max_digits=4,
        decimal_places=1,
        null=True,
        blank=True,
        verbose_name="Température"
    )
    verifymode = models.IntegerField(
        null=True,
        blank=True,
        verbose_name="Mode vérification détaillé"
    )
    image = models.TextField(
        blank=True,
        verbose_name="Image (base64)"
    )
    
    log_index = models.IntegerField(
        null=True,
        blank=True,
        verbose_name="Index du log"
    )
    
    raw_payload = models.JSONField(
        default=dict,
        verbose_name="Payload brut"
    )
    
    access_granted = models.BooleanField(
        default=True,
        verbose_name="Accès accordé"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'tm20_attendance_logs'
        verbose_name = "Log de pointage"
        verbose_name_plural = "Logs de pointage"
        ordering = ['-time']
        indexes = [
            models.Index(fields=['terminal', 'time']),
            models.Index(fields=['enrollid', 'time']),
        ]
    
    def __str__(self):
        return f"{self.enrollid} - {self.time} ({self.terminal.sn})"


class CommandQueue(models.Model):
    """File d'attente des commandes à envoyer aux terminaux"""
    
    STATUS_CHOICES = [
        ('pending', 'En attente'),
        ('sent', 'Envoyée'),
        ('success', 'Succès'),
        ('failed', 'Échec'),
        ('timeout', 'Timeout'),
    ]
    
    terminal = models.ForeignKey(
        Terminal,
        on_delete=models.CASCADE,
        related_name='commands',
        verbose_name="Terminal"
    )
    command = models.CharField(
        max_length=50,
        verbose_name="Commande"
    )
    payload = models.JSONField(
        default=dict,
        verbose_name="Payload"
    )
    
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending',
        verbose_name="Statut"
    )
    response = models.JSONField(
        null=True,
        blank=True,
        verbose_name="Réponse"
    )
    error_message = models.TextField(
        blank=True,
        verbose_name="Message d'erreur"
    )
    
    retry_count = models.IntegerField(default=0)
    max_retries = models.IntegerField(default=3)
    
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        db_table = 'tm20_command_queue'
        verbose_name = "Commande en attente"
        verbose_name_plural = "Commandes en attente"
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.command} -> {self.terminal.sn} ({self.status})"
