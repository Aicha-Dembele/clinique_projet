-- =====================================================================
--  Clinique Névroglie — requêtes SQL de soutenance
--  Base : clinique_db (MySQL 8.0, port 3307, collation utf8mb4_bin)
--
--  Toutes les requêtes de ce fichier ont été exécutées et vérifiées sur
--  la base réelle. Classées du plus simple au plus complexe : le jury
--  commence presque toujours par le haut.
--
--  Connexion :  mysql -u root -p -P 3307 -h 127.0.0.1 clinique_db
-- =====================================================================


-- ---------------------------------------------------------------------
-- A. LES BASES  —  SELECT, WHERE, ORDER BY, LIMIT
-- ---------------------------------------------------------------------

-- A1. Lister tous les patients
SELECT id, nom, prenom, sexe, telephone
FROM patients_patient
ORDER BY nom;

-- A2. Rechercher un patient par son nom (recherche partielle)
SELECT id, nom, prenom, telephone
FROM patients_patient
WHERE nom LIKE '%Diallo%' OR prenom LIKE '%Diallo%';

-- A3. Les patientes, triées par nom
SELECT nom, prenom, date_naissance
FROM patients_patient
WHERE sexe = 'Féminin'
ORDER BY nom;

-- A4. Les 5 médicaments les plus chers
SELECT nom, forme, dosage, prix_unitaire
FROM pharmacie_medicament
ORDER BY prix_unitaire DESC
LIMIT 5;


-- ---------------------------------------------------------------------
-- B. CALCULS ET FONCTIONS
-- ---------------------------------------------------------------------

-- B1. Âge de chaque patient
SELECT nom, prenom, date_naissance,
       TIMESTAMPDIFF(YEAR, date_naissance, CURDATE()) AS age
FROM patients_patient
ORDER BY age DESC;

-- B2. Valeur totale du stock de la pharmacie
SELECT COUNT(*)                              AS references_en_stock,
       SUM(quantite_stock)                   AS unites_totales,
       SUM(quantite_stock * prix_unitaire)   AS valeur_stock_fcfa
FROM pharmacie_medicament
WHERE actif = 1;


-- ---------------------------------------------------------------------
-- C. AGRÉGATION  —  COUNT, SUM, AVG, GROUP BY, HAVING
-- ---------------------------------------------------------------------

-- C1. Nombre de patients par sexe
SELECT sexe, COUNT(*) AS nombre
FROM patients_patient
GROUP BY sexe;

-- C2. Montant facturé par statut
SELECT statut,
       COUNT(*)            AS nb_factures,
       SUM(montant_total)  AS total_fcfa,
       ROUND(AVG(montant_total)) AS moyenne_fcfa
FROM facturation_facture
GROUP BY statut
ORDER BY total_fcfa DESC;

-- C3. Recettes encaissées par mois
SELECT DATE_FORMAT(date, '%Y-%m') AS mois,
       COUNT(*)                   AS nb_paiements,
       SUM(montant)               AS encaisse_fcfa
FROM facturation_paiement
GROUP BY mois
ORDER BY mois;

-- C4. Répartition des modes de paiement
SELECT mode_paiement,
       COUNT(*)     AS nb,
       SUM(montant) AS total_fcfa,
       ROUND(100 * SUM(montant) / (SELECT SUM(montant) FROM facturation_paiement), 1) AS part_pourcent
FROM facturation_paiement
GROUP BY mode_paiement
ORDER BY total_fcfa DESC;

-- C5. Médecins ayant au moins 1 rendez-vous  (GROUP BY + HAVING)
SELECT m.nom, m.prenom, m.specialite,
       COUNT(r.id) AS nb_rendez_vous
FROM personnel_medecin m
JOIN consultation_rendez_vous r ON r.medecin_id = m.id
GROUP BY m.id, m.nom, m.prenom, m.specialite
HAVING COUNT(r.id) >= 1
ORDER BY nb_rendez_vous DESC;


-- ---------------------------------------------------------------------
-- D. JOINTURES
-- ---------------------------------------------------------------------

-- D1. Rendez-vous avec le patient et le médecin  (jointure de 3 tables)
SELECT r.id, r.date, r.statut,
       CONCAT(p.prenom, ' ', p.nom) AS patient,
       CONCAT('Dr ', m.prenom, ' ', m.nom) AS medecin
FROM consultation_rendez_vous r
JOIN patients_patient  p ON p.id = r.patient_id
JOIN personnel_medecin m ON m.id = r.medecin_id
ORDER BY r.date DESC;

-- D2. Factures avec le patient et son assurance
--     LEFT JOIN parce qu'une facture peut n'avoir aucune assurance : un INNER
--     JOIN ferait disparaître ces factures-là, ce qui fausserait le total.
SELECT f.id, f.date_creation, f.montant_total, f.statut,
       CONCAT(p.prenom, ' ', p.nom) AS patient,
       COALESCE(a.nom, 'Aucune')    AS assurance
FROM facturation_facture f
JOIN patients_patient      p ON p.id = f.patient_id
LEFT JOIN facturation_assurance a ON a.id = f.assurance_id
ORDER BY f.date_creation DESC;

-- D3. Détail d'une facture : ses lignes et le sous-total de chacune
SELECT f.id AS facture,
       l.description, l.type_service, l.quantite, l.prix_unitaire,
       (l.quantite * l.prix_unitaire) AS sous_total
FROM facturation_facture f
JOIN facturation_lignefacture l ON l.facture_id = f.id
ORDER BY f.id, l.id;

-- D4. Vérifier que le total enregistré correspond à la somme des lignes.
--     Un jury adore cette question : « comment savez-vous que c'est juste ? »
SELECT f.id,
       f.montant_total                          AS total_enregistre,
       SUM(l.quantite * l.prix_unitaire)        AS total_recalcule,
       CASE WHEN f.montant_total = SUM(l.quantite * l.prix_unitaire)
            THEN 'OK' ELSE 'ECART' END          AS verdict
FROM facturation_facture f
JOIN facturation_lignefacture l ON l.facture_id = f.id
GROUP BY f.id, f.montant_total
ORDER BY f.id;


-- D5. Les consultations d'un médecin donné.
--     Piège classique : la table consultation_consultation n'a PAS de colonne
--     medecin_id. Dans ce modèle, le médecin est rattaché au rendez-vous, et la
--     consultation se rattache au rendez-vous. Il faut donc remonter la chaîne
--     consultation -> rendez-vous -> médecin. Écrire directement
--     « WHERE medecin_id = 1 » renvoie l'erreur 1054, Unknown column.
SELECT c.id,
       c.date,
       CONCAT(p.prenom, ' ', p.nom)        AS patient,
       CONCAT('Dr ', m.prenom, ' ', m.nom) AS medecin,
       c.motif,
       c.diagnostic
FROM consultation_consultation c
JOIN consultation_rendez_vous r ON r.id = c.rendez_vous_id
JOIN patients_patient         p ON p.id = r.patient_id
JOIN personnel_medecin        m ON m.id = r.medecin_id
WHERE m.id = 1
ORDER BY c.date DESC;

-- D5 bis. La même chose en filtrant sur le nom plutôt que sur l'identifiant.
--         Rappel : la base est sensible à la casse, 'cisse' ne marcherait pas.
-- WHERE m.nom = 'Cisse'


-- ---------------------------------------------------------------------
-- E. SOUS-REQUÊTES ET ANTI-JOINTURES
-- ---------------------------------------------------------------------

-- E1. Patients qui n'ont jamais eu de rendez-vous
SELECT p.id, p.nom, p.prenom
FROM patients_patient p
WHERE NOT EXISTS (
    SELECT 1 FROM consultation_rendez_vous r WHERE r.patient_id = p.id
);

-- E2. Factures dont le montant dépasse la moyenne générale
SELECT id, montant_total, statut
FROM facturation_facture
WHERE montant_total > (SELECT AVG(montant_total) FROM facturation_facture)
ORDER BY montant_total DESC;

-- E3. Le médicament le plus dispensé  (sous-requête dans le FROM)
--     Attention : la base est en utf8mb4_bin, donc les comparaisons de texte
--     sont sensibles à la casse. La valeur stockée est 'sortie' en minuscules ;
--     écrire 'SORTIE' ne renverrait aucune ligne.
SELECT m.nom, m.forme, t.total_sorti
FROM (
    SELECT medicament_id, SUM(quantite) AS total_sorti
    FROM pharmacie_mouvementstock
    WHERE type_mouvement = 'sortie'
    GROUP BY medicament_id
) t
JOIN pharmacie_medicament m ON m.id = t.medicament_id
ORDER BY t.total_sorti DESC
LIMIT 5;


-- ---------------------------------------------------------------------
-- F. REQUÊTES MÉTIER  —  celles qui montrent que l'application sert
-- ---------------------------------------------------------------------

-- F1. Médicaments sous le seuil d'alerte : rupture imminente
SELECT nom, dci, quantite_stock, seuil_alerte,
       (seuil_alerte - quantite_stock) AS manque
FROM pharmacie_medicament
WHERE actif = 1 AND quantite_stock <= seuil_alerte
ORDER BY manque DESC;

-- F2. Qualité des données : médicaments dont la péremption n'est pas saisie.
--     Les 41 références sont dans ce cas ; c'est un constat assumable devant
--     le jury, la saisie des péremptions reste à faire.
SELECT COUNT(*)                         AS total_references,
       SUM(date_peremption IS NULL)     AS sans_peremption,
       SUM(date_peremption IS NOT NULL) AS avec_peremption
FROM pharmacie_medicament
WHERE actif = 1;

-- F2 bis. La même surveillance une fois les dates saisies : ce qui périme
--         dans les 90 jours. À garder sous la main si le jury la demande.
-- SELECT nom, date_peremption, quantite_stock,
--        DATEDIFF(date_peremption, CURDATE()) AS jours_restants
-- FROM pharmacie_medicament
-- WHERE date_peremption IS NOT NULL
--   AND date_peremption <= DATE_ADD(CURDATE(), INTERVAL 90 DAY)
-- ORDER BY date_peremption;

-- F3. Part patient et part assurance sur chaque facture
SELECT f.id,
       CONCAT(p.prenom, ' ', p.nom)                        AS patient,
       COALESCE(a.nom, 'Aucune')                           AS assurance,
       f.montant_total,
       f.taux_prise_en_charge                              AS taux_pourcent,
       ROUND(f.montant_total * f.taux_prise_en_charge/100) AS part_assurance,
       ROUND(f.montant_total * (1 - f.taux_prise_en_charge/100)) AS part_patient
FROM facturation_facture f
JOIN patients_patient p ON p.id = f.patient_id
LEFT JOIN facturation_assurance a ON a.id = f.assurance_id
ORDER BY f.id;

-- F4. Reste à payer par facture : part patient moins les paiements reçus
SELECT f.id,
       CONCAT(p.prenom, ' ', p.nom) AS patient,
       ROUND(f.montant_total * (1 - f.taux_prise_en_charge/100)) AS part_patient,
       COALESCE(SUM(pa.montant), 0)                              AS deja_paye,
       ROUND(f.montant_total * (1 - f.taux_prise_en_charge/100))
           - COALESCE(SUM(pa.montant), 0)                        AS reste_a_payer,
       f.statut
FROM facturation_facture f
JOIN patients_patient p ON p.id = f.patient_id
LEFT JOIN facturation_paiement pa ON pa.facture_id = f.id
GROUP BY f.id, p.prenom, p.nom, f.montant_total, f.taux_prise_en_charge, f.statut
ORDER BY reste_a_payer DESC;

-- F5. Séjours d'hospitalisation, avec la durée réelle calculée.
--     Le filtre « en cours » (date_sortie IS NULL) ne renvoie rien aujourd'hui :
--     tous les patients enregistrés sont déjà sortis.
SELECT h.numero_chambre, h.type_chambre,
       CONCAT(p.prenom, ' ', p.nom)                      AS patient,
       h.date_entree, h.date_sortie,
       DATEDIFF(h.date_sortie, h.date_entree)            AS duree_calculee,
       h.nombre_jours                                    AS duree_facturee,
       CASE WHEN h.date_sortie IS NULL THEN 'En cours' ELSE 'Termine' END AS etat
FROM consultation_hospitalisation h
JOIN patients_patient p ON p.id = h.patient_id
ORDER BY h.date_entree DESC;

-- F6. Activité de chaque médecin : rendez-vous, hospitalisations, examens
SELECT CONCAT('Dr ', m.prenom, ' ', m.nom) AS medecin, m.specialite,
       (SELECT COUNT(*) FROM consultation_rendez_vous     r WHERE r.medecin_id = m.id) AS rendez_vous,
       (SELECT COUNT(*) FROM consultation_hospitalisation h WHERE h.medecin_id = m.id) AS hospitalisations,
       (SELECT COUNT(*) FROM consultation_examenmedical   e WHERE e.medecin_id = m.id) AS examens
FROM personnel_medecin m
ORDER BY rendez_vous DESC;

-- F7. Examens de laboratoire par statut
SELECT statut, COUNT(*) AS nombre
FROM consultation_examenmedical
GROUP BY statut;


-- ---------------------------------------------------------------------
-- G. COMPTES, RÔLES ET PERMISSIONS  —  le volet sécurité
-- ---------------------------------------------------------------------

-- G1. Quel utilisateur possède quel rôle
SELECT u.username, u.is_active, r.code AS role, r.libelle
FROM auth_user u
LEFT JOIN comptes_profil pr ON pr.user_id = u.id
LEFT JOIN comptes_role   r  ON r.id = pr.role_id
ORDER BY r.code, u.username;

-- G2. Nombre de permissions accordées à chaque rôle
SELECT r.libelle, COUNT(rp.permission_id) AS nb_permissions
FROM comptes_role r
LEFT JOIN comptes_role_permissions rp ON rp.role_id = r.id
GROUP BY r.id, r.libelle
ORDER BY nb_permissions DESC;

-- G3. Permissions détaillées d'un rôle donné.
--     Même piège qu'en E3 : les codes de rôle sont en minuscules et la base est
--     sensible à la casse. 'MEDECIN' ne renverrait rien, 'medecin' fonctionne.
SELECT r.libelle AS role, pe.code, pe.libelle AS permission
FROM comptes_role r
JOIN comptes_role_permissions rp ON rp.role_id = r.id
JOIN comptes_permission       pe ON pe.id = rp.permission_id
WHERE r.code = 'medecin'
ORDER BY pe.code;


-- ---------------------------------------------------------------------
-- H. STRUCTURE DE LA BASE  —  si le jury demande à voir le schéma
-- ---------------------------------------------------------------------

-- H1. Toutes les tables et leur nombre de lignes
SELECT table_name, table_rows
FROM information_schema.tables
WHERE table_schema = 'clinique_db'
ORDER BY table_name;

-- H2. Structure de la table des patients
DESCRIBE patients_patient;

-- H3. Le SQL de création d'une table : types, index, contraintes
SHOW CREATE TABLE facturation_facture;

-- H4. Toutes les clés étrangères de la base
SELECT table_name AS depuis, column_name AS colonne,
       referenced_table_name AS vers, referenced_column_name AS colonne_cible
FROM information_schema.key_column_usage
WHERE table_schema = 'clinique_db' AND referenced_table_name IS NOT NULL
ORDER BY table_name, column_name;

-- H5. Jeu de caractères et collation de la base
SELECT default_character_set_name AS jeu, default_collation_name AS collation
FROM information_schema.schemata
WHERE schema_name = 'clinique_db';
