from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('facturation', '0002_rename_type_sevice_tarif_type_service'),
    ]

    operations = [
        migrations.AddField(
            model_name='lignefacture',
            name='description',
            field=models.CharField(max_length=200, default=''),
        ),
        migrations.AddField(
            model_name='facture',
            name='notes',
            field=models.TextField(blank=True, default=''),
        ),
        migrations.AddField(
            model_name='facture',
            name='date_creation',
            field=models.DateTimeField(auto_now_add=True, null=True),
        ),
        migrations.AddField(
            model_name='paiement',
            name='note',
            field=models.CharField(max_length=200, blank=True, default=''),
        ),
        migrations.AlterField(
            model_name='facture',
            name='statut',
            field=models.CharField(
                max_length=20,
                choices=[('non payé','Non payé'),('partiel','Partiellement payé'),('payé','Payé')],
                default='non payé'
            ),
        ),
        # Supprime l'ancienne FK examen qui n'est plus utilisée
        migrations.RemoveField(
            model_name='facture',
            name='examen',
        ),
    ]