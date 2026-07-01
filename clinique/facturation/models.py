import unicodedata
from django.db import models
from patients.models import Patient
from decimal import Decimal


def _norm(s):
    """Normalise une chaîne pour comparaison : minuscules, sans accents ni espaces superflus.
    Permet de matcher « Particulière » == « particuliere », « GENERALISTE » == « Généraliste »."""
    if not s:
        return ''
    s = unicodedata.normalize('NFKD', str(s))
    s = ''.join(c for c in s if not unicodedata.combining(c))
    return s.strip().lower()


class Tarif(models.Model):
    TYPE_CHOICES = [
        ('consultation',    'Consultation'),
        ('examen',          'Examen médical'),
        ('hospitalisation', 'Hospitalisation (par nuit)'),
    ]

    # Types de chambres prédéfinis pour l'hospitalisation
    TYPE_CHAMBRE_CHOICES = [
        ('Standard',       'Chambre Standard'),
        ('Particulière',   'Chambre Particulière'),
        ('VIP',            'Chambre VIP'),
        ('Double',         'Chambre Double'),
        ('USI',            'Unité de Soins Intensifs (USI)'),
        ('Pédiatrie',      'Chambre Pédiatrie'),
        ('Maternité',      'Chambre Maternité'),
    ]

    type_service = models.CharField(max_length=20, choices=TYPE_CHOICES)
    # consultation  → specialite = spécialité médecin  (ex: "Cardiologie")
    # examen        → specialite = type d'examen        (ex: "Radiologie")
    # hospitalisation → specialite = type de chambre   (ex: "Standard", "VIP")
    specialite = models.CharField(
        max_length=100, null=True, blank=True,
        help_text="Spécialité / Type d'examen / Type de chambre selon le service"
    )
    nom  = models.CharField(max_length=100)
    prix = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        label = f" — {self.specialite}" if self.specialite else ""
        return f"{self.nom}{label} — {self.prix:,.0f} FCFA"

    class Meta:
        verbose_name = "Tarif"
        verbose_name_plural = "Tarifs"
        ordering = ['type_service', 'nom']


class Assurance(models.Model):
    """Régime / compagnie d'assurance maladie (ex : AMO, CANAM, mutuelle privée).

    Le taux de prise en charge est le pourcentage de la facture couvert par
    l'assurance ; le reste (« ticket modérateur ») est à la charge du patient.
    """
    nom = models.CharField(max_length=100, unique=True)
    taux_prise_en_charge = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal('70'),
        help_text="Pourcentage de la facture pris en charge par l'assurance (ex : 70 pour 70 %)."
    )
    description = models.CharField(max_length=200, blank=True, default='')
    actif = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.nom} — {self.taux_prise_en_charge:.0f} %"

    class Meta:
        verbose_name = "Assurance"
        verbose_name_plural = "Assurances"
        ordering = ['nom']


class Facture(models.Model):
    STATUT_CHOICES = [
        ('non payé', 'Non payé'),
        ('partiel',  'Partiellement payé'),
        ('payé',     'Payé'),
    ]

    patient         = models.ForeignKey(Patient, on_delete=models.CASCADE)
    consultation    = models.ForeignKey("consultation.Consultation",  on_delete=models.SET_NULL, null=True, blank=True)
    hospitalisation = models.ForeignKey("consultation.Hospitalisation", on_delete=models.SET_NULL, null=True, blank=True)
    montant_total   = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    statut          = models.CharField(max_length=20, choices=STATUT_CHOICES, default='non payé')
    date_creation   = models.DateTimeField(auto_now_add=True, null=True)
    notes           = models.TextField(blank=True, default='')

    # ── Assurance : prise en charge d'une partie de la facture ────
    # `taux_prise_en_charge` est un instantané (snapshot) copié depuis l'assurance
    # à la création, mais modifiable par facture : ainsi l'historique reste juste
    # même si le taux de l'assurance change plus tard.
    assurance            = models.ForeignKey(Assurance, on_delete=models.SET_NULL, null=True, blank=True)
    taux_prise_en_charge = models.DecimalField(
        max_digits=5, decimal_places=2, default=0,
        help_text="Taux de prise en charge appliqué à cette facture (%)."
    )

    # ── Calcul principal ──────────────────────────────────────────
    def calculer_total(self):
        """Recalcule le total depuis les LigneFacture existantes."""
        return sum(l.sous_total() for l in self.lignes.all()) or Decimal('0')

    @staticmethod
    def _index_tarifs():
        """Précharge TOUS les tarifs en une seule requête et construit un index
        en mémoire → matching O(1) sans requête par ligne (zéro N+1).

        Retourne (index, defaults) :
          index[type_service][specialite_normalisee] = Tarif
          defaults[type_service] = tarif de repli (1er selon l'ordre du modèle)
        """
        index, defaults = {}, {}
        for t in Tarif.objects.all():                 # ordering Meta : type_service, nom
            index.setdefault(t.type_service, {})[_norm(t.specialite)] = t
            defaults.setdefault(t.type_service, t)    # 1er rencontré = repli (== .first())
        return index, defaults

    def generer_lignes(self):
        """
        Supprime les anciennes lignes et recrée tout depuis les objets liés.
        Appelée lors du save(). Tous les tarifs sont préchargés une seule fois :
        le calcul reste correct quel que soit le nombre d'examens, sans N+1.
        """
        self.lignes.all().delete()
        index, defaults = self._index_tarifs()

        def resolve(type_service, specialite):
            """Tarif correspondant au type/spécialité (accents & casse ignorés), sinon repli."""
            return index.get(type_service, {}).get(_norm(specialite)) or defaults.get(type_service)

        lignes = []

        # ── 1. CONSULTATION ──────────────────────────────────────
        if self.consultation:
            specialite = ''
            try:
                specialite = self.consultation.rendez_vous.medecin.specialite
            except Exception:
                pass

            tarif = resolve('consultation', specialite)
            prix = tarif.prix if tarif else Decimal('0')
            nom  = tarif.nom  if tarif else f"Consultation {specialite}"
            lignes.append(LigneFacture(
                facture=self,
                description=nom,
                type_service='consultation',
                prix_unitaire=prix,
                quantite=1,
            ))

            # ── 1b. EXAMENS liés à cette consultation ────────────
            for examen in self.consultation.examenmedical_set.all():
                tarif_e = resolve('examen', examen.type_examen)
                prix_e = tarif_e.prix if tarif_e else Decimal('0')
                nom_e  = tarif_e.nom  if tarif_e else f"Examen — {examen.type_examen}"
                lignes.append(LigneFacture(
                    facture=self,
                    description=f"{nom_e} ({examen.type_examen})",
                    type_service='examen',
                    prix_unitaire=prix_e,
                    quantite=1,
                ))

        # ── 2. HOSPITALISATION ───────────────────────────────────
        if self.hospitalisation:
            h = self.hospitalisation
            type_ch = (h.type_chambre or 'standard').strip()
            jours   = max(int(h.nombre_jours or 1), 1)

            tarif_h = resolve('hospitalisation', type_ch)
            prix_h = tarif_h.prix if tarif_h else Decimal('0')
            nom_h  = tarif_h.nom  if tarif_h else f"Chambre {type_ch}"
            lignes.append(LigneFacture(
                facture=self,
                description=f"{nom_h} — chambre {h.numero_chambre} ({type_ch})",
                type_service='hospitalisation',
                prix_unitaire=prix_h,
                quantite=jours,
            ))

        # ── 3. MÉDICAMENTS dispensés (sorties de stock portées sur cette facture) ──
        # Régénérées depuis les MouvementStock liés : le total reste juste à chaque
        # recalcul, comme pour les consultations/examens (une requête, sans N+1).
        if self.pk:
            # Filet de sécurité : rattache à cette facture les médicaments déjà
            # dispensés contre une ordonnance de SA consultation mais pas encore
            # portés sur une facture (sorties « orphelines »). Ainsi les médicaments
            # de l'ordonnance apparaissent toujours sur la facture de la consultation.
            if self.consultation_id:
                from pharmacie.models import MouvementStock
                MouvementStock.objects.filter(
                    type_mouvement='sortie',
                    facture__isnull=True,
                    ordonnance__consultation_id=self.consultation_id,
                ).update(facture=self)
            for mv in (self.mouvements
                       .filter(type_mouvement='sortie')
                       .select_related('medicament')):
                lignes.append(LigneFacture(
                    facture=self,
                    description=f"Médicament — {mv.medicament.libelle()}",
                    type_service='medicament',
                    prix_unitaire=mv.prix_unitaire,
                    quantite=mv.quantite,
                ))

        LigneFacture.objects.bulk_create(lignes)

    def save(self, *args, **kwargs):
        # Cohérence assurance ↔ taux de prise en charge :
        #  - assurance choisie sans taux explicite → on reprend le taux de l'assurance
        #  - aucune assurance → pas de prise en charge
        if self.assurance_id:
            if not self.taux_prise_en_charge:
                self.taux_prise_en_charge = self.assurance.taux_prise_en_charge
        else:
            self.taux_prise_en_charge = Decimal('0')

        # Premier save pour avoir un PK (persiste aussi assurance + taux)
        is_new = self.pk is None
        super().save(*args, **kwargs)
        # Génère les lignes
        self.generer_lignes()
        # Recalcule le total depuis les lignes
        self.montant_total = self.calculer_total()
        # Save final sans boucle infinie
        Facture.objects.filter(pk=self.pk).update(montant_total=self.montant_total)
        # Recalcule le statut selon la part réellement due par le patient
        self.update_statut()

    def montant_paye(self):
        return sum(p.montant for p in self.paiements.all()) or Decimal('0')

    # ── Répartition assurance / patient ───────────────────────────
    def part_assurance(self):
        """Montant pris en charge par l'assurance (arrondi au franc)."""
        taux = self.taux_prise_en_charge or Decimal('0')
        if taux <= 0:
            return Decimal('0')
        return (self.montant_total * taux / Decimal('100')).quantize(Decimal('1'))

    def part_patient(self):
        """Reste à charge du patient (ticket modérateur) = ce qu'il doit régler."""
        return max(self.montant_total - self.part_assurance(), Decimal('0'))

    def montant_restant(self):
        """Ce qu'il reste à encaisser auprès du patient (hors part assurance)."""
        return max(self.part_patient() - self.montant_paye(), Decimal('0'))

    def update_statut(self):
        paye    = self.montant_paye()
        a_payer = self.part_patient()
        if a_payer <= 0:
            self.statut = 'payé'            # prise en charge à 100 %
        elif paye <= 0:
            self.statut = 'non payé'
        elif paye >= a_payer:
            self.statut = 'payé'
        else:
            self.statut = 'partiel'
        Facture.objects.filter(pk=self.pk).update(statut=self.statut)

    def __str__(self):
        return f"FAC-{str(self.pk).zfill(4)} — {self.patient} — {self.montant_total:,.0f} FCFA — {self.statut}"


class LigneFacture(models.Model):
    facture       = models.ForeignKey(Facture, related_name='lignes', on_delete=models.CASCADE)
    description   = models.CharField(max_length=200, default='')
    type_service  = models.CharField(max_length=50)
    prix_unitaire = models.DecimalField(max_digits=10, decimal_places=2)
    quantite      = models.PositiveIntegerField(default=1)

    def sous_total(self):
        return self.prix_unitaire * self.quantite

    def __str__(self):
        return f"{self.description} × {self.quantite} = {self.sous_total():,.0f} FCFA"


class Paiement(models.Model):
    MODE_CHOICES = [
        ('cash',         'Espèces'),
        ('orange_money', 'Orange Money'),
        ('moov_money',   'Moov Money'),
        ('carte',        'Carte bancaire'),
    ]

    facture        = models.ForeignKey(Facture, related_name='paiements', on_delete=models.CASCADE)
    montant        = models.DecimalField(max_digits=10, decimal_places=2)
    mode_paiement  = models.CharField(max_length=20, choices=MODE_CHOICES)
    date           = models.DateTimeField(auto_now_add=True)
    note           = models.CharField(max_length=200, blank=True, default='')

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.facture.update_statut()

    def __str__(self):
        return f"{self.montant:,.0f} FCFA — {self.get_mode_paiement_display()}"