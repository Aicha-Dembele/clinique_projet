from datetime import timedelta
from decimal import Decimal

from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


class Specialite(models.Model):
    """Spécialité médicale servant à cibler les médicaments à la prescription."""

    code = models.CharField(max_length=40, unique=True)
    nom  = models.CharField(max_length=80)

    class Meta:
        ordering = ['nom']
        verbose_name = "Spécialité"
        verbose_name_plural = "Spécialités"

    def __str__(self):
        return self.nom


class Medicament(models.Model):
    """Médicament géré en stock par la pharmacie de la clinique."""

    # Rangées dans l'ordre où un soignant y pense : la douleur et les
    # infections d'abord, les consommables à la fin. Cet ordre est celui de
    # l'affichage par groupes, en pharmacie comme dans l'assistant
    # d'ordonnance — changer l'ordre ici change l'ordre des deux écrans.
    # Les codes ne changent JAMAIS : ils sont enregistrés en base.
    CATEGORIE_CHOICES = [
        ('antalgique',       'Antalgique / Antidouleur'),
        ('anti_inflammatoire', 'Anti-inflammatoire'),
        ('antipyretique',    'Antipyrétique (fièvre)'),
        ('antibiotique',     'Antibiotique'),
        ('antifongique',     'Antifongique (mycoses)'),
        ('antiviral',        'Antiviral'),
        ('antipaludique',    'Antipaludique'),
        ('antiallergique',   'Antiallergique / Antihistaminique'),
        ('orl',              'ORL — rhume, gorge, oreilles'),
        ('respiratoire',     'Respiratoire (asthme, toux)'),
        ('cardiovasculaire', 'Cardiovasculaire'),
        ('digestif',         'Digestif / Gastro'),
        ('endocrinien',      'Diabète / Hormones'),
        ('neuro_psy',        'Neurologie / Psychiatrie'),
        ('gynecologie',      'Gynécologie / Obstétrique'),
        ('dermatologique',   'Dermatologique (peau)'),
        ('ophtalmologique',  'Ophtalmologie (yeux)'),
        ('vitamine',         'Vitamines / Compléments'),
        ('solute',           'Soluté / Perfusion'),
        ('antiseptique',     'Antiseptique / Désinfectant'),
        ('consommable',      'Consommable / Matériel médical'),
        ('autre',            'Autre'),
    ]

    nom            = models.CharField(max_length=150)
    dci            = models.CharField(
        max_length=150, blank=True, default='',
        help_text="Dénomination commune internationale (principe actif), ex : Paracétamol.")
    forme          = models.CharField(
        max_length=100, blank=True, default='',
        help_text="Comprimé, sirop, injectable, pommade, gélule…")
    dosage         = models.CharField(
        max_length=60, blank=True, default='',
        help_text="Ex : 500 mg, 1 g, 100 mg/5 ml.")
    categorie      = models.CharField(
        max_length=30, choices=CATEGORIE_CHOICES, blank=True, default='')
    indication     = models.TextField(
        blank=True, default='',
        help_text="À quoi sert ce médicament et dans quels cas le prescrire (aide à la prescription).")
    commun         = models.BooleanField(
        default=False,
        help_text="Médicament de base, proposé à toutes les spécialités.")
    # Toutes les assurances ne remboursent pas tout : un générique essentiel
    # est pris en charge, une spécialité de marque souvent pas. Décoché, le
    # médicament est entièrement à la charge du patient, même assuré.
    rembourse      = models.BooleanField(
        "remboursé par l'assurance", default=True,
        help_text="Décochez si ce médicament reste entièrement à la charge du patient.")
    specialites    = models.ManyToManyField(
        Specialite, blank=True, related_name='medicaments',
        help_text="Spécialités pour lesquelles ce médicament est proposé en priorité.")
    unite          = models.CharField(
        max_length=30, default='boîte',
        help_text="Unité de gestion du stock : boîte, comprimé, flacon…")
    prix_unitaire  = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    quantite_stock = models.PositiveIntegerField(default=0)
    seuil_alerte   = models.PositiveIntegerField(
        default=10,
        help_text="Stock minimal : en dessous (ou égal), une alerte de réapprovisionnement s'affiche.")
    date_peremption = models.DateField(null=True, blank=True)
    actif          = models.BooleanField(default=True)
    date_creation  = models.DateTimeField(auto_now_add=True, null=True)

    class Meta:
        verbose_name = "Médicament"
        verbose_name_plural = "Médicaments"
        ordering = ['nom']

    def __str__(self):
        base = self.nom
        if self.dosage:
            base += f" {self.dosage}"
        return f"{base} — {self.quantite_stock} {self.unite}"

    # ── Libellé complet (nom + dosage + forme) ────────────────────
    def libelle(self):
        parts = [self.nom]
        if self.dosage:
            parts.append(self.dosage)
        if self.forme:
            parts.append(f"({self.forme})")
        return ' '.join(parts)

    # ── État du stock ─────────────────────────────────────────────
    def est_rupture(self):
        """Stock épuisé."""
        return self.quantite_stock <= 0

    def est_en_alerte(self):
        """Stock faible : encore disponible mais sous le seuil."""
        return 0 < self.quantite_stock <= self.seuil_alerte

    def statut_stock(self):
        """'rupture' | 'alerte' | 'ok' — pratique pour le template."""
        if self.est_rupture():
            return 'rupture'
        if self.est_en_alerte():
            return 'alerte'
        return 'ok'

    def valeur_stock(self):
        """Valeur monétaire du stock détenu (prix unitaire × quantité)."""
        return (self.prix_unitaire or Decimal('0')) * self.quantite_stock

    # ── Péremption ────────────────────────────────────────────────
    def est_perime(self):
        return bool(self.date_peremption) and self.date_peremption < timezone.localdate()

    def rafraichir_peremption(self):
        """La péremption du médicament = celle du lot qui périme le plus tôt.

        Le champ `date_peremption` reste sur le médicament — toute
        l'application s'en sert déjà (pastille « Périmé », filtre, badge du
        menu) — mais il devient une **recopie du plus proche lot en stock**
        au lieu d'une date saisie à la main. C'est ce qui corrige le défaut :
        réapprovisionner n'efface plus la date de l'ancien stock, puisque
        l'ancien lot est toujours là et reste le plus proche.

        Sans aucun lot en stock, on ne touche à rien : les médicaments
        d'avant les lots gardent la date qu'ils avaient.
        """
        plus_proche = (self.lots.filter(quantite_restante__gt=0)
                       .exclude(date_peremption__isnull=True)
                       .order_by('date_peremption')
                       .values_list('date_peremption', flat=True).first())
        if plus_proche and plus_proche != self.date_peremption:
            self.date_peremption = plus_proche
            Medicament.objects.filter(pk=self.pk).update(date_peremption=plus_proche)

    def stock_par_lots(self):
        """Somme des lots en stock. Doit valoir `quantite_stock` ; sert à
        repérer un écart (médicament d'avant les lots, ou saisie manuelle)."""
        return sum(l.quantite_restante for l in self.lots.all())

    #: Au-delà de ce délai, la péremption n'est plus « proche ». Constante
    #: partagée avec le badge d'alerte du menu (comptes/context_processors).
    JOURS_AVANT_PEREMPTION = 30

    def bientot_perime(self, jours=None):
        if not self.date_peremption or self.est_perime():
            return False
        jours = self.JOURS_AVANT_PEREMPTION if jours is None else jours
        return self.date_peremption <= timezone.localdate() + timedelta(days=jours)


class MouvementStock(models.Model):
    """Trace chaque entrée (réapprovisionnement) ou sortie (dispensation) de stock.

    Le stock du médicament est ajusté automatiquement à la création du mouvement
    et ré-ajusté en cas de suppression : le `Medicament.quantite_stock` reste donc
    toujours cohérent avec la somme des mouvements.
    """

    TYPE_CHOICES = [
        ('entree', 'Entrée (réapprovisionnement)'),
        ('sortie', 'Sortie (dispensation)'),
    ]

    medicament     = models.ForeignKey(
        Medicament, on_delete=models.CASCADE, related_name='mouvements')
    type_mouvement = models.CharField(max_length=10, choices=TYPE_CHOICES)
    quantite       = models.PositiveIntegerField()
    prix_unitaire  = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        help_text="Prix unitaire figé au moment du mouvement. Par défaut, celui du médicament.")
    motif          = models.CharField(max_length=200, blank=True, default='')

    # Liens optionnels : une sortie peut correspondre à une ordonnance / un patient
    ordonnance     = models.ForeignKey(
        'consultation.Ordonnance', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='dispensations')
    patient        = models.ForeignKey(
        'patients.Patient', on_delete=models.SET_NULL, null=True, blank=True)
    facture        = models.ForeignKey(
        'facturation.Facture', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='mouvements',
        help_text="Facture sur laquelle ce médicament dispensé est porté (le cas échéant).")
    utilisateur    = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True)
    date           = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Mouvement de stock"
        verbose_name_plural = "Mouvements de stock"
        ordering = ['-date']

    def __str__(self):
        signe = '+' if self.type_mouvement == 'entree' else '-'
        return f"{self.get_type_mouvement_display()} {signe}{self.quantite} — {self.medicament.nom}"

    # ── Montant du mouvement (prix figé × quantité) ───────────────
    def montant(self):
        """Valeur monétaire du mouvement : prix unitaire (snapshot) × quantité."""
        return (self.prix_unitaire or Decimal('0')) * self.quantite

    # ── Ajustement automatique du stock ───────────────────────────
    def _appliquer(self, delta):
        """Applique un delta au stock du médicament de façon atomique (F-expression)."""
        Medicament.objects.filter(pk=self.medicament_id).update(
            quantite_stock=models.F('quantite_stock') + delta
        )

    def _stock_actuel(self):
        """Quantité en stock lue en base (l'instance self.medicament peut être périmée)."""
        return (Medicament.objects.filter(pk=self.medicament_id)
                .values_list('quantite_stock', flat=True).first() or 0)

    def _notifier_si_seuil_franchi(self, avant, apres):
        """Notifie les pharmaciens (cloche) quand le stock FRANCHIT le seuil
        d'alerte ou tombe en rupture. Déclenchée uniquement au franchissement,
        pas à chaque sortie, pour ne pas noyer la cloche de doublons."""
        try:
            medicament = Medicament.objects.get(pk=self.medicament_id)
            seuil = medicament.seuil_alerte
            reste = max(apres, 0)
            if avant > 0 and apres <= 0:
                titre = f"Rupture de stock : {medicament.libelle()}"
                message = (f"Le stock est épuisé (0 {medicament.unite}). "
                           "Réapprovisionnement urgent nécessaire.")
            elif avant > seuil and apres <= seuil:
                titre = f"Stock insuffisant : {medicament.libelle()}"
                message = (f"Il ne reste que {reste} {medicament.unite} "
                           f"(seuil d'alerte : {seuil}). Pensez à réapprovisionner.")
            else:
                return

            from django.urls import reverse
            from comptes.models import Notification, Profil
            url = reverse('pharmacie:medicaments')
            pharmaciens = (Profil.objects
                           .filter(role__code='pharmacien', user__is_active=True)
                           .select_related('user'))
            for profil in pharmaciens:
                Notification.creer(profil.user, titre, message,
                                   url=url, icone='bi-capsule')
        except Exception:
            # Une alerte qui échoue ne doit jamais bloquer le mouvement de stock.
            pass

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        # Fige le prix courant du médicament si aucun prix n'a été fourni
        if is_new and not self.prix_unitaire:
            self.prix_unitaire = self.medicament.prix_unitaire or Decimal('0')
        super().save(*args, **kwargs)
        if is_new:
            # Le detail par lot AVANT le compteur : si la repartition echoue,
            # le stock global n'a pas encore bouge.
            if self.type_mouvement == 'entree':
                self._creer_le_lot()
            else:
                self._consommer_les_lots()
            self.medicament.rafraichir_peremption()

            delta = self.quantite if self.type_mouvement == 'entree' else -self.quantite
            avant = self._stock_actuel()
            self._appliquer(delta)
            if delta < 0:
                self._notifier_si_seuil_franchi(avant, avant + delta)

    # ── Le detail par lot ────────────────────────────────────────

    def _creer_le_lot(self):
        """Toute entree de stock cree un lot : c'est un arrivage.

        Les precisions du bon de livraison (numero de lot, peremption, prix
        d'achat, fournisseur) sont posees par l'appelant sur l'instance avant
        le save, sous forme d'attributs `lot_*`. Quand elles manquent, on
        retombe sur ce qu'on sait du medicament : l'entree reste tracee.
        """
        Lot.objects.create(
            medicament=self.medicament,
            numero=getattr(self, 'lot_numero', '') or '',
            date_peremption=(getattr(self, 'lot_peremption', None)
                             or self.medicament.date_peremption),
            quantite_initiale=self.quantite,
            quantite_restante=self.quantite,
            prix_achat=(getattr(self, 'lot_prix_achat', None)
                        or self.prix_unitaire or Decimal('0')),
            fournisseur=getattr(self, 'lot_fournisseur', None),
        )

    def _consommer_les_lots(self):
        """Sert d'abord le lot qui perime le plus tot (regle PEPS / FEFO).

        Une sortie peut vider la fin d'un lot et entamer le suivant : chaque
        part est enregistree dans SortieLot, pour savoir quel lot est parti
        chez quel patient.

        Si les lots ne couvrent pas la quantite — stock d'avant les lots, ou
        ecart de saisie — on sert ce qu'on peut sans bloquer : le compteur
        du medicament reste la reference, les lots sont le detail.
        """
        a_servir = self.quantite
        disponibles = (Lot.objects.select_for_update()
                       .filter(medicament=self.medicament, quantite_restante__gt=0))
        for lot in disponibles:
            if a_servir <= 0:
                break
            pris = min(lot.quantite_restante, a_servir)
            lot.quantite_restante -= pris
            lot.save(update_fields=['quantite_restante'])
            SortieLot.objects.create(mouvement=self, lot=lot, quantite=pris)
            a_servir -= pris

    def delete(self, *args, **kwargs):
        # Annule l'effet du mouvement avant suppression
        delta = -self.quantite if self.type_mouvement == 'entree' else self.quantite
        avant = self._stock_actuel()
        self._appliquer(delta)
        # La suppression d'une ENTRÉE fait baisser le stock : on vérifie le seuil aussi.
        if delta < 0:
            self._notifier_si_seuil_franchi(avant, avant + delta)
        facture = self.facture
        super().delete(*args, **kwargs)
        # Recalcule la facture pour retirer la ligne du médicament dispensé
        if facture is not None:
            facture.save()


class Fournisseur(models.Model):
    """Grossiste ou laboratoire chez qui la clinique achète ses médicaments.

    Sans lui, une entrée de stock ne dit pas d'où vient la marchandise : on
    ne peut ni calculer sa marge, ni rappeler un lot défectueux auprès de
    celui qui l'a livré.
    """
    nom       = models.CharField(max_length=150, unique=True)
    telephone = models.CharField(max_length=40, blank=True, default='')
    email     = models.EmailField(blank=True, default='')
    adresse   = models.CharField(max_length=250, blank=True, default='')
    contact   = models.CharField(
        max_length=120, blank=True, default='',
        help_text="Personne à joindre chez ce fournisseur.")
    actif     = models.BooleanField(default=True)
    date_creation = models.DateTimeField(auto_now_add=True, null=True)

    class Meta:
        verbose_name = "Fournisseur"
        verbose_name_plural = "Fournisseurs"
        ordering = ['nom']

    def __str__(self):
        return self.nom


class Lot(models.Model):
    """Un arrivage précis d'un médicament : une quantité, une péremption, un prix.

    C'est ce qui manquait au stock. Sans lot, un médicament n'a qu'UNE date
    de péremption : réapprovisionner écrase la date de l'ancien stock, qui
    devient invisible et qu'on découvre périmé.

    Avec les lots, chaque arrivage garde sa date. Et la dispensation sert
    toujours **le lot qui périme le plus tôt** (règle PEPS / FEFO), comme
    dans une vraie pharmacie : voir `MouvementStock._consommer_les_lots()`.
    """
    medicament  = models.ForeignKey(Medicament, related_name='lots',
                                    on_delete=models.CASCADE)
    numero      = models.CharField(
        "numéro de lot", max_length=60, blank=True, default='',
        help_text="Numéro imprimé sur la boîte par le fabricant.")
    date_peremption   = models.DateField(null=True, blank=True)
    quantite_initiale = models.PositiveIntegerField()
    quantite_restante = models.PositiveIntegerField()
    prix_achat  = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        help_text="Prix d'achat unitaire chez le fournisseur (pour la marge).")
    fournisseur = models.ForeignKey(Fournisseur, null=True, blank=True,
                                    related_name='lots', on_delete=models.SET_NULL)
    date_entree = models.DateTimeField(auto_now_add=True, null=True)

    class Meta:
        verbose_name = "Lot"
        verbose_name_plural = "Lots"
        # Les lots sans date de péremption passent en dernier : on sert
        # d'abord ce dont on connaît l'échéance.
        ordering = [models.F('date_peremption').asc(nulls_last=True), 'pk']

    def __str__(self):
        etiquette = self.numero or f"lot {self.pk}"
        if self.date_peremption:
            return f"{etiquette} — périme le {self.date_peremption:%d/%m/%Y}"
        return etiquette

    def est_epuise(self):
        return self.quantite_restante <= 0

    def est_perime(self):
        return bool(self.date_peremption) and self.date_peremption < timezone.localdate()

    def bientot_perime(self):
        if not self.date_peremption or self.est_perime():
            return False
        limite = timezone.localdate() + timedelta(
            days=Medicament.JOURS_AVANT_PEREMPTION)
        return self.date_peremption <= limite


class SortieLot(models.Model):
    """Quelle quantité une sortie a prise dans quel lot.

    Une dispensation peut vider la fin d'un lot et entamer le suivant : ce
    détail est enregistré ici, pour qu'on sache toujours quel lot est parti
    chez quel patient — c'est ce qui permet de rappeler un lot défectueux.
    """
    mouvement = models.ForeignKey('MouvementStock', related_name='lots_servis',
                                  on_delete=models.CASCADE)
    lot       = models.ForeignKey(Lot, related_name='sorties',
                                  on_delete=models.CASCADE)
    quantite  = models.PositiveIntegerField()

    class Meta:
        verbose_name = "Sortie de lot"
        verbose_name_plural = "Sorties de lot"
        ordering = ['pk']

    def __str__(self):
        return f"{self.quantite} × {self.lot}"


class Commande(models.Model):
    """Commande passée à un fournisseur, puis réceptionnée.

    C'est le chaînon qui manquait en amont du stock : aujourd'hui une entrée
    sort de nulle part. Avec la commande, on sait ce qu'on a demandé, à qui,
    à quel prix, et ce qui est réellement arrivé.

    La réception ne se contente pas de changer un statut : elle crée les
    entrées de stock, donc les lots, avec leur péremption (voir
    `LigneCommande.receptionner`).
    """
    class Statut(models.TextChoices):
        BROUILLON = 'brouillon', 'Brouillon'
        ENVOYEE   = 'envoyee',   'Envoyée au fournisseur'
        RECUE     = 'recue',     'Reçue'
        ANNULEE   = 'annulee',   'Annulée'

    fournisseur    = models.ForeignKey(Fournisseur, related_name='commandes',
                                       on_delete=models.PROTECT)
    reference      = models.CharField(
        max_length=60, blank=True, default='',
        help_text="Votre référence ou celle du bon de commande du fournisseur.")
    statut         = models.CharField(max_length=12, choices=Statut.choices,
                                      default=Statut.BROUILLON)
    date_commande  = models.DateField(default=timezone.localdate)
    date_reception = models.DateField(null=True, blank=True)
    notes          = models.TextField(blank=True, default='')
    utilisateur    = models.ForeignKey('auth.User', null=True, blank=True,
                                       on_delete=models.SET_NULL)

    class Meta:
        verbose_name = "Commande fournisseur"
        verbose_name_plural = "Commandes fournisseurs"
        ordering = ['-date_commande', '-pk']

    def __str__(self):
        return f"CMD-{self.pk:04d} — {self.fournisseur}"

    def montant_total(self):
        return sum(l.sous_total() for l in self.lignes.all()) or Decimal('0')

    def est_receptionnee(self):
        return self.statut == self.Statut.RECUE

    def reste_a_recevoir(self):
        """Lignes pas encore servies en totalité."""
        return [l for l in self.lignes.all() if l.quantite_restante() > 0]


class LigneCommande(models.Model):
    """Un médicament commandé : ce qu'on a demandé, ce qu'on a reçu."""
    commande       = models.ForeignKey(Commande, related_name='lignes',
                                       on_delete=models.CASCADE)
    medicament     = models.ForeignKey(Medicament, related_name='lignes_commande',
                                       on_delete=models.PROTECT)
    quantite       = models.PositiveIntegerField("quantité commandée")
    quantite_recue = models.PositiveIntegerField("quantité reçue", default=0)
    prix_achat     = models.DecimalField("prix d'achat unitaire",
                                         max_digits=10, decimal_places=2, default=0)

    class Meta:
        verbose_name = "Ligne de commande"
        verbose_name_plural = "Lignes de commande"
        ordering = ['pk']

    def __str__(self):
        return f"{self.quantite} × {self.medicament.libelle()}"

    def sous_total(self):
        return self.prix_achat * self.quantite

    def quantite_restante(self):
        return max(self.quantite - self.quantite_recue, 0)

    def receptionner(self, quantite, numero_lot='', date_peremption=None,
                     utilisateur=None):
        """Fait entrer en stock ce qui vient d'être livré sur cette ligne.

        Une entrée de stock est créée, donc un lot : la marchandise arrive
        avec sa propre péremption et son prix d'achat, rattachée au
        fournisseur de la commande. Livrer en deux fois crée deux lots,
        ce qui est fidèle à la réalité.
        """
        quantite = int(quantite or 0)
        if quantite <= 0:
            return None
        if quantite > self.quantite_restante():
            raise ValueError(
                f"{self.medicament.nom} : {quantite} reçus pour "
                f"{self.quantite_restante()} encore attendus.")

        mouvement = MouvementStock(
            medicament=self.medicament,
            type_mouvement='entree',
            quantite=quantite,
            prix_unitaire=self.medicament.prix_unitaire or Decimal('0'),
            motif=f"Réception {self.commande}",
            utilisateur=utilisateur,
        )
        mouvement.lot_numero = numero_lot or ''
        mouvement.lot_peremption = date_peremption
        mouvement.lot_prix_achat = self.prix_achat or None
        mouvement.lot_fournisseur = self.commande.fournisseur
        mouvement.save()

        self.quantite_recue += quantite
        self.save(update_fields=['quantite_recue'])
        return mouvement
