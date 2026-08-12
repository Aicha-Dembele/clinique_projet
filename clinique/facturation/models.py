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

    # ── Un service = une facture ──────────────────────────────────
    # Chaque prestation est facturée SÉPARÉMENT : la consultation, chaque examen,
    # l'hospitalisation et les médicaments d'une ordonnance ont chacun leur propre
    # facture, avec leur propre prise en charge par l'assurance. Un et un seul de
    # ces quatre liens est renseigné par facture (voir `service()`).
    patient         = models.ForeignKey(Patient, on_delete=models.CASCADE)
    consultation    = models.ForeignKey("consultation.Consultation",  on_delete=models.SET_NULL, null=True, blank=True)
    examen          = models.ForeignKey("consultation.ExamenMedical", on_delete=models.SET_NULL, null=True, blank=True)
    hospitalisation = models.ForeignKey("consultation.Hospitalisation", on_delete=models.SET_NULL, null=True, blank=True)
    ordonnance      = models.ForeignKey("consultation.Ordonnance", on_delete=models.SET_NULL, null=True, blank=True,
                                        help_text="Facture des médicaments dispensés pour cette ordonnance.")
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

    # ── Recouvrement auprès de l'assureur ─────────────────────────
    # La part prise en charge n'est pas encaissée auprès du patient : c'est une
    # créance sur l'assurance. Ces trois champs suivent son recouvrement, de la
    # demande de remboursement jusqu'au paiement effectif par l'assureur.
    # `statut` (au-dessus) concerne le PATIENT, celui-ci concerne l'ASSUREUR :
    # une facture peut être « payé » côté patient et encore « à réclamer » ici.
    STATUT_ASSURANCE_CHOICES = [
        ('a_reclamer', 'À réclamer'),
        ('reclame',    'Réclamé'),
        ('rembourse',  'Remboursé'),
    ]
    statut_assurance   = models.CharField(
        max_length=20, choices=STATUT_ASSURANCE_CHOICES, default='a_reclamer',
        help_text="Où en est le remboursement par l'assurance.")
    date_reclamation   = models.DateField(
        null=True, blank=True,
        help_text="Date d'envoi de la demande de remboursement à l'assureur.")
    date_remboursement = models.DateField(
        null=True, blank=True,
        help_text="Date à laquelle l'assureur a effectivement remboursé.")

    def marquer_assurance(self, nouveau_statut, quand=None):
        """Fait avancer (ou revenir) le recouvrement, en tenant les dates à jour.

        Revenir en arrière efface les dates devenues fausses : un dossier
        repassé « à réclamer » ne doit pas garder une date de remboursement.
        """
        from django.utils import timezone
        if nouveau_statut not in dict(self.STATUT_ASSURANCE_CHOICES):
            raise ValueError("Statut de recouvrement inconnu.")
        quand = quand or timezone.localdate()

        self.statut_assurance = nouveau_statut
        if nouveau_statut == 'a_reclamer':
            self.date_reclamation = None
            self.date_remboursement = None
        elif nouveau_statut == 'reclame':
            self.date_reclamation = self.date_reclamation or quand
            self.date_remboursement = None
        else:  # rembourse
            self.date_reclamation = self.date_reclamation or quand
            self.date_remboursement = quand

        # update() cible les seuls champs de recouvrement : pas de save() complet,
        # qui régénérerait les lignes et recalculerait le total sans raison.
        Facture.objects.filter(pk=self.pk).update(
            statut_assurance=self.statut_assurance,
            date_reclamation=self.date_reclamation,
            date_remboursement=self.date_remboursement,
        )

    # ── Identification du service facturé ─────────────────────────
    SERVICES = [
        ('consultation',    'Consultation'),
        ('examen',          'Examen médical'),
        ('hospitalisation', 'Hospitalisation'),
        ('ordonnance',      'Pharmacie (ordonnance)'),
    ]

    def service(self):
        """Code du service facturé, ou None si la facture n'est rattachée à rien.

        Une facture ne porte qu'un seul service : on renvoie le premier lien
        renseigné, dans l'ordre du parcours de soin.
        """
        if self.consultation_id:
            return 'consultation'
        if self.examen_id:
            return 'examen'
        if self.hospitalisation_id:
            return 'hospitalisation'
        if self.ordonnance_id:
            return 'ordonnance'
        return None

    def service_libelle(self):
        """Nom lisible du service facturé, pour l'affichage et les PDF."""
        code = self.service()
        return dict(self.SERVICES).get(code, 'Prestation')

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
        Supprime les anciennes lignes et recrée celles du SEUL service facturé.

        Chaque prestation est facturée à part : une facture de consultation ne
        contient que la consultation, une facture d'examen que cet examen, etc.
        L'assurance s'applique ensuite indépendamment sur chacune (part_assurance
        travaille sur le montant de cette facture uniquement).

        Appelée lors du save(). Les tarifs sont préchargés en une seule requête.
        """
        self.lignes.all().delete()
        index, defaults = self._index_tarifs()

        def resolve(type_service, specialite):
            """Tarif correspondant au type/spécialité (accents & casse ignorés), sinon repli."""
            return index.get(type_service, {}).get(_norm(specialite)) or defaults.get(type_service)

        lignes = []

        # ── CONSULTATION ─────────────────────────────────────────
        # Uniquement l'acte de consultation : les examens prescrits pendant
        # celle-ci sont factures separement, sur leur propre facture.
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

        # ── EXAMEN MÉDICAL ───────────────────────────────────────
        elif self.examen:
            e = self.examen
            tarif_e = resolve('examen', e.type_examen)
            prix_e = tarif_e.prix if tarif_e else Decimal('0')
            nom_e  = tarif_e.nom  if tarif_e else f"Examen — {e.type_examen}"
            lignes.append(LigneFacture(
                facture=self,
                description=f"{nom_e} ({e.type_examen})",
                type_service='examen',
                prix_unitaire=prix_e,
                quantite=1,
            ))

        # ── HOSPITALISATION ──────────────────────────────────────
        elif self.hospitalisation:
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

        # ── PHARMACIE : médicaments dispensés pour une ordonnance ─
        # Une facture par ordonnance : on repart des sorties de stock rattachées
        # à cette ordonnance, quel que soit le nombre de passages en pharmacie.
        # Les sorties font foi, le total reste donc juste à chaque recalcul.
        elif self.ordonnance_id and self.pk:
            from pharmacie.models import MouvementStock
            sorties = (MouvementStock.objects
                       .filter(type_mouvement='sortie', ordonnance_id=self.ordonnance_id)
                       .select_related('medicament'))
            # Traçabilité : ces sorties portent bien cette facture-là.
            sorties.exclude(facture_id=self.pk).update(facture=self)
            for mv in sorties:
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

    # Ordre d'affichage des prestations sur la facture (détail + PDF)
    GROUPES_LIGNES = [
        ('consultation',    'Consultation'),
        ('examen',          'Examens'),
        ('hospitalisation', 'Hospitalisation'),
        ('medicament',      'Médicaments (ordonnance)'),
    ]

    def lignes_groupees(self):
        """Lignes regroupées par type de prestation, dans un ordre fixe, avec
        sous-total par groupe. Travaille sur les lignes déjà préchargées
        (prefetch_related) : aucune requête supplémentaire."""
        lignes = list(self.lignes.all())
        groupes = []
        for code, label in self.GROUPES_LIGNES:
            items = [l for l in lignes if l.type_service == code]
            if items:
                groupes.append({
                    'code': code, 'label': label, 'lignes': items,
                    'sous_total': sum(l.sous_total() for l in items),
                })
        # Types inattendus : jamais perdus, regroupés en fin de facture
        connus = {code for code, _ in self.GROUPES_LIGNES}
        autres = [l for l in lignes if l.type_service not in connus]
        if autres:
            groupes.append({
                'code': 'autre', 'label': 'Autres prestations', 'lignes': autres,
                'sous_total': sum(l.sous_total() for l in autres),
            })
        return groupes

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
        return (f"FAC-{str(self.pk).zfill(4)} — {self.patient} — {self.service_libelle()} — "
                f"{self.montant_total:,.0f} FCFA — {self.statut}")


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