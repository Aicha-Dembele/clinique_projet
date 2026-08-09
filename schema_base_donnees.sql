-- ══════════════════════════════════════════════════════════════════
--  SCHÉMA DE LA BASE DE DONNÉES — CLINIQUE NEVROGLIE
--  27 tables principales (sur 43) — dialecte MySQL / MariaDB
--  Convention Django : nom_de_table = nomdelapp_nomdumodele
-- ══════════════════════════════════════════════════════════════════

-- ────────────────────────────────────────────────────
--  1. COMPTES & ACCÈS
-- ────────────────────────────────────────────────────

-- Comptes de connexion (table native de Django)
CREATE TABLE auth_user (
    id           INT AUTO_INCREMENT PRIMARY KEY,
    username     VARCHAR(150) NOT NULL UNIQUE,
    password     VARCHAR(128) NOT NULL,           -- haché (PBKDF2), jamais en clair
    first_name   VARCHAR(150) NOT NULL,
    last_name    VARCHAR(150) NOT NULL,
    email        VARCHAR(254) NOT NULL,
    is_active    BOOLEAN NOT NULL DEFAULT TRUE,   -- compte activé / désactivé
    is_staff     BOOLEAN NOT NULL DEFAULT FALSE,
    is_superuser BOOLEAN NOT NULL DEFAULT FALSE,
    last_login   DATETIME NULL,
    date_joined  DATETIME NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

-- Rôles applicatifs (admin, medecin, laborantin, infirmier, receptionniste, pharmacien)
CREATE TABLE comptes_role (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    code        VARCHAR(30)  NOT NULL UNIQUE,
    libelle     VARCHAR(100) NOT NULL,
    description TEXT NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

-- Permissions fines (ex : patient.view, facture.add)
CREATE TABLE comptes_permission (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    code        VARCHAR(100) NOT NULL UNIQUE,
    libelle     VARCHAR(200) NOT NULL,
    description TEXT NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

-- Table de liaison N-N : un rôle possède plusieurs permissions
CREATE TABLE comptes_role_permissions (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    role_id       INT NOT NULL,
    permission_id INT NOT NULL,
    UNIQUE (role_id, permission_id),
    FOREIGN KEY (role_id)       REFERENCES comptes_role(id)       ON DELETE CASCADE,
    FOREIGN KEY (permission_id) REFERENCES comptes_permission(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

-- ────────────────────────────────────────────────────
--  2. PERSONNEL DE LA CLINIQUE
-- ────────────────────────────────────────────────────

CREATE TABLE personnel_medecin (
    id         INT AUTO_INCREMENT PRIMARY KEY,
    nom        VARCHAR(100) NOT NULL,
    prenom     VARCHAR(100) NOT NULL,
    telephone  VARCHAR(20)  NOT NULL,
    adresse    TEXT NOT NULL,
    service    VARCHAR(100) NOT NULL,
    specialite VARCHAR(100) NOT NULL,      -- ex : Cardiologie, Neurologie
    photo      VARCHAR(100) NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

CREATE TABLE personnel_infirmier (
    id        INT AUTO_INCREMENT PRIMARY KEY,
    nom       VARCHAR(100) NOT NULL,
    prenom    VARCHAR(100) NOT NULL,
    telephone VARCHAR(20)  NOT NULL,
    adresse   TEXT NOT NULL,
    service   VARCHAR(100) NOT NULL,
    photo     VARCHAR(100) NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

CREATE TABLE personnel_laborantin (
    id         INT AUTO_INCREMENT PRIMARY KEY,
    nom        VARCHAR(100) NOT NULL,
    prenom     VARCHAR(100) NOT NULL,
    telephone  VARCHAR(20)  NOT NULL,
    adresse    TEXT NOT NULL,
    service    VARCHAR(100) NOT NULL,
    specialite VARCHAR(100) NOT NULL,      -- ex : Biologie, Radiologie
    photo      VARCHAR(100) NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

CREATE TABLE personnel_receptionniste (
    id        INT AUTO_INCREMENT PRIMARY KEY,
    nom       VARCHAR(100) NOT NULL,
    prenom    VARCHAR(100) NOT NULL,
    telephone VARCHAR(20)  NOT NULL,
    adresse   TEXT NOT NULL,
    service   VARCHAR(100) NOT NULL,
    photo     VARCHAR(100) NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

CREATE TABLE personnel_pharmacien (
    id        INT AUTO_INCREMENT PRIMARY KEY,
    nom       VARCHAR(100) NOT NULL,
    prenom    VARCHAR(100) NOT NULL,
    telephone VARCHAR(20)  NOT NULL,
    adresse   TEXT NOT NULL,
    service   VARCHAR(100) NOT NULL,
    photo     VARCHAR(100) NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

-- Profil : le pont entre le compte de connexion (auth_user), le rôle
-- applicatif et la fiche métier du personnel (liens 1-1 optionnels)
CREATE TABLE comptes_profil (
    id                INT AUTO_INCREMENT PRIMARY KEY,
    user_id           INT NOT NULL UNIQUE,
    role_id           INT NOT NULL,
    telephone         VARCHAR(20) NOT NULL,
    adresse           TEXT NOT NULL,
    medecin_id        INT NULL UNIQUE,
    infirmier_id      INT NULL UNIQUE,
    laborantin_id     INT NULL UNIQUE,
    receptionniste_id INT NULL UNIQUE,
    pharmacien_id     INT NULL UNIQUE,
    date_creation     DATETIME NOT NULL,
    FOREIGN KEY (user_id)           REFERENCES auth_user(id)                ON DELETE CASCADE,
    FOREIGN KEY (role_id)           REFERENCES comptes_role(id)             ON DELETE RESTRICT,
    FOREIGN KEY (medecin_id)        REFERENCES personnel_medecin(id)        ON DELETE SET NULL,
    FOREIGN KEY (infirmier_id)      REFERENCES personnel_infirmier(id)      ON DELETE SET NULL,
    FOREIGN KEY (laborantin_id)     REFERENCES personnel_laborantin(id)     ON DELETE SET NULL,
    FOREIGN KEY (receptionniste_id) REFERENCES personnel_receptionniste(id) ON DELETE SET NULL,
    FOREIGN KEY (pharmacien_id)     REFERENCES personnel_pharmacien(id)     ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

-- Notifications (cloche) : résultats transmis, alertes de stock…
CREATE TABLE comptes_notification (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    user_id       INT NOT NULL,
    titre         VARCHAR(200) NOT NULL,
    message       TEXT NOT NULL,
    url           VARCHAR(300) NOT NULL,
    icone         VARCHAR(50)  NOT NULL DEFAULT 'bi-bell-fill',
    lu            BOOLEAN NOT NULL DEFAULT FALSE,
    date_creation DATETIME NOT NULL,
    FOREIGN KEY (user_id) REFERENCES auth_user(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

-- ────────────────────────────────────────────────────
--  3. PATIENTS & ASSURANCE
-- ────────────────────────────────────────────────────

-- Régimes d'assurance maladie (AMO, CANAM, mutuelles…)
CREATE TABLE facturation_assurance (
    id                   INT AUTO_INCREMENT PRIMARY KEY,
    nom                  VARCHAR(100) NOT NULL UNIQUE,
    taux_prise_en_charge DECIMAL(5,2) NOT NULL DEFAULT 70.00,  -- % couvert
    description          VARCHAR(200) NOT NULL,
    actif                BOOLEAN NOT NULL DEFAULT TRUE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

CREATE TABLE patients_patient (
    id             INT AUTO_INCREMENT PRIMARY KEY,
    nom            VARCHAR(100) NOT NULL,
    prenom         VARCHAR(100) NOT NULL,
    sexe           VARCHAR(50)  NOT NULL,          -- Masculin / Féminin
    date_naissance DATE NOT NULL,
    adresse        VARCHAR(255) NOT NULL,
    telephone      VARCHAR(20)  NOT NULL,
    email          VARCHAR(254) NOT NULL,
    numero_urgence VARCHAR(20)  NOT NULL,
    photo          VARCHAR(100) NULL,
    date_creation  DATETIME NOT NULL,
    assurance_id   INT NULL,
    numero_assure  VARCHAR(50) NOT NULL DEFAULT '',
    FOREIGN KEY (assurance_id) REFERENCES facturation_assurance(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

-- ────────────────────────────────────────────────────
--  4. PARCOURS DE SOINS
-- ────────────────────────────────────────────────────

CREATE TABLE consultation_rendez_vous (
    id         INT AUTO_INCREMENT PRIMARY KEY,
    patient_id INT NOT NULL,
    medecin_id INT NOT NULL,
    date       DATETIME NOT NULL,
    statut     VARCHAR(20) NOT NULL DEFAULT 'programme',  -- programme|termine|annule
    UNIQUE (medecin_id, date),                 -- pas 2 RDV au même créneau
    FOREIGN KEY (patient_id) REFERENCES patients_patient(id)  ON DELETE CASCADE,
    FOREIGN KEY (medecin_id) REFERENCES personnel_medecin(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

-- Dossier médical : UN par patient (créé au premier soin), avec un
-- médecin propriétaire (cloisonnement des données entre confrères)
CREATE TABLE consultation_dossiermedical (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    patient_id    INT NOT NULL UNIQUE,
    medecin_id    INT NULL,
    date_creation DATETIME NOT NULL,
    FOREIGN KEY (patient_id) REFERENCES patients_patient(id)  ON DELETE CASCADE,
    FOREIGN KEY (medecin_id) REFERENCES personnel_medecin(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

CREATE TABLE consultation_consultation (
    id             INT AUTO_INCREMENT PRIMARY KEY,
    rendez_vous_id INT NOT NULL UNIQUE,      -- 1 RDV → au plus 1 consultation
    dossier_id     INT NULL,
    motif          TEXT NOT NULL,
    diagnostic     TEXT NOT NULL,
    observation    TEXT NOT NULL,
    date           DATETIME NOT NULL,
    FOREIGN KEY (rendez_vous_id) REFERENCES consultation_rendez_vous(id)    ON DELETE CASCADE,
    FOREIGN KEY (dossier_id)     REFERENCES consultation_dossiermedical(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

CREATE TABLE consultation_examenmedical (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    patient_id      INT NOT NULL,
    dossier_id      INT NULL,
    consultation_id INT NOT NULL,
    laborantin_id   INT NULL,
    medecin_id      INT NULL,
    type_examen     VARCHAR(100) NOT NULL,
    motif           VARCHAR(255) NOT NULL DEFAULT '',
    date            DATE NULL,
    statut          VARCHAR(20) NOT NULL DEFAULT 'en_cours',  -- en_attente|en_cours|termine
    FOREIGN KEY (patient_id)      REFERENCES patients_patient(id)           ON DELETE CASCADE,
    FOREIGN KEY (dossier_id)      REFERENCES consultation_dossiermedical(id) ON DELETE CASCADE,
    FOREIGN KEY (consultation_id) REFERENCES consultation_consultation(id)  ON DELETE CASCADE,
    FOREIGN KEY (laborantin_id)   REFERENCES personnel_laborantin(id)       ON DELETE CASCADE,
    FOREIGN KEY (medecin_id)      REFERENCES personnel_medecin(id)          ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

CREATE TABLE consultation_resultatexamen (
    id                INT AUTO_INCREMENT PRIMARY KEY,
    patient_id        INT NOT NULL,
    dossier_id        INT NULL,
    examen_id         INT NOT NULL,
    medecin_id        INT NULL,
    laborantin_id     INT NULL,
    resultat          TEXT NOT NULL,
    observations      TEXT NOT NULL,
    image             VARCHAR(100) NULL,      -- scanner, radio, échographie…
    transmis          BOOLEAN NOT NULL DEFAULT FALSE,
    date_transmission DATETIME NULL,
    lu_par_medecin    BOOLEAN NOT NULL DEFAULT FALSE,
    date_lecture      DATETIME NULL,
    date_examen       DATETIME NOT NULL,
    FOREIGN KEY (patient_id)    REFERENCES patients_patient(id)            ON DELETE CASCADE,
    FOREIGN KEY (dossier_id)    REFERENCES consultation_dossiermedical(id) ON DELETE CASCADE,
    FOREIGN KEY (examen_id)     REFERENCES consultation_examenmedical(id)  ON DELETE CASCADE,
    FOREIGN KEY (medecin_id)    REFERENCES personnel_medecin(id)           ON DELETE SET NULL,
    FOREIGN KEY (laborantin_id) REFERENCES personnel_laborantin(id)        ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

CREATE TABLE consultation_ordonnance (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    consultation_id INT NOT NULL,
    dossier_id      INT NULL,
    date            DATE NOT NULL,
    medicaments     TEXT NOT NULL,
    FOREIGN KEY (consultation_id) REFERENCES consultation_consultation(id)   ON DELETE CASCADE,
    FOREIGN KEY (dossier_id)      REFERENCES consultation_dossiermedical(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

CREATE TABLE consultation_traitement (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    patient_id      INT NOT NULL,
    consultation_id INT NULL,
    dossier_id      INT NULL,
    infirmier_id    INT NULL,
    description     TEXT NOT NULL,
    duree           INT NOT NULL,             -- durée en jours
    statut          VARCHAR(20) NOT NULL DEFAULT 'prescrit',  -- prescrit|en_cours|termine
    date_creation   DATETIME NOT NULL,
    FOREIGN KEY (patient_id)      REFERENCES patients_patient(id)            ON DELETE CASCADE,
    FOREIGN KEY (consultation_id) REFERENCES consultation_consultation(id)   ON DELETE CASCADE,
    FOREIGN KEY (dossier_id)      REFERENCES consultation_dossiermedical(id) ON DELETE CASCADE,
    FOREIGN KEY (infirmier_id)    REFERENCES personnel_infirmier(id)         ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

CREATE TABLE consultation_hospitalisation (
    id             INT AUTO_INCREMENT PRIMARY KEY,
    patient_id     INT NOT NULL,
    medecin_id     INT NOT NULL,
    dossier_id     INT NULL,
    type_chambre   VARCHAR(100) NOT NULL DEFAULT 'standard',  -- vip|double|simple
    nombre_jours   INT NOT NULL DEFAULT 1,
    numero_chambre VARCHAR(10) NOT NULL,      -- plan fixe : 40 chambres
    date_entree    DATE NOT NULL,
    date_sortie    DATE NULL,                 -- NULL = patient encore hospitalisé
    etat_clinique  VARCHAR(20) NOT NULL DEFAULT 'stable',     -- stable|critique
    FOREIGN KEY (patient_id) REFERENCES patients_patient(id)            ON DELETE CASCADE,
    FOREIGN KEY (medecin_id) REFERENCES personnel_medecin(id)           ON DELETE CASCADE,
    FOREIGN KEY (dossier_id) REFERENCES consultation_dossiermedical(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

-- ────────────────────────────────────────────────────
--  5. FACTURATION
-- ────────────────────────────────────────────────────

-- Grille tarifaire : retrouvée dynamiquement par (type_service, specialite)
CREATE TABLE facturation_tarif (
    id           INT AUTO_INCREMENT PRIMARY KEY,
    type_service VARCHAR(20)  NOT NULL,       -- consultation|examen|hospitalisation
    specialite   VARCHAR(100) NULL,           -- spécialité / type d'examen / type de chambre
    nom          VARCHAR(100) NOT NULL,
    prix         DECIMAL(10,2) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

CREATE TABLE facturation_facture (
    id                   INT AUTO_INCREMENT PRIMARY KEY,
    patient_id           INT NOT NULL,
    consultation_id      INT NULL,
    hospitalisation_id   INT NULL,
    montant_total        DECIMAL(10,2) NOT NULL DEFAULT 0,
    statut               VARCHAR(20) NOT NULL DEFAULT 'non payé',  -- non payé|partiel|payé
    date_creation        DATETIME NULL,
    notes                TEXT NOT NULL,
    assurance_id         INT NULL,
    taux_prise_en_charge DECIMAL(5,2) NOT NULL DEFAULT 0,  -- copié (snapshot) de l'assurance
    FOREIGN KEY (patient_id)         REFERENCES patients_patient(id)             ON DELETE CASCADE,
    FOREIGN KEY (consultation_id)    REFERENCES consultation_consultation(id)    ON DELETE SET NULL,
    FOREIGN KEY (hospitalisation_id) REFERENCES consultation_hospitalisation(id) ON DELETE SET NULL,
    FOREIGN KEY (assurance_id)       REFERENCES facturation_assurance(id)        ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

CREATE TABLE facturation_lignefacture (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    facture_id    INT NOT NULL,
    description   VARCHAR(200) NOT NULL DEFAULT '',
    type_service  VARCHAR(50)  NOT NULL,
    prix_unitaire DECIMAL(10,2) NOT NULL,
    quantite      INT UNSIGNED NOT NULL DEFAULT 1,
    FOREIGN KEY (facture_id) REFERENCES facturation_facture(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

CREATE TABLE facturation_paiement (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    facture_id    INT NOT NULL,
    montant       DECIMAL(10,2) NOT NULL,
    mode_paiement VARCHAR(20) NOT NULL,       -- cash|orange_money|moov_money|carte
    date          DATETIME NOT NULL,
    note          VARCHAR(200) NOT NULL DEFAULT '',
    FOREIGN KEY (facture_id) REFERENCES facturation_facture(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

-- ────────────────────────────────────────────────────
--  6. PHARMACIE
-- ────────────────────────────────────────────────────

CREATE TABLE pharmacie_medicament (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    nom             VARCHAR(150) NOT NULL,
    dci             VARCHAR(150) NOT NULL DEFAULT '',   -- principe actif
    forme           VARCHAR(100) NOT NULL DEFAULT '',   -- comprimé, sirop…
    dosage          VARCHAR(60)  NOT NULL DEFAULT '',
    categorie       VARCHAR(30)  NOT NULL DEFAULT '',
    indication      TEXT NOT NULL,
    commun          BOOLEAN NOT NULL DEFAULT FALSE,
    unite           VARCHAR(30)  NOT NULL DEFAULT 'boîte',
    prix_unitaire   DECIMAL(10,2) NOT NULL DEFAULT 0,
    quantite_stock  INT UNSIGNED NOT NULL DEFAULT 0,
    seuil_alerte    INT UNSIGNED NOT NULL DEFAULT 10,   -- alerte de réapprovisionnement
    date_peremption DATE NULL,
    actif           BOOLEAN NOT NULL DEFAULT TRUE,
    date_creation   DATETIME NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

-- Chaque entrée/sortie de stock est tracée ; le stock du médicament
-- n'est modifié QUE par ces mouvements (jamais directement)
CREATE TABLE pharmacie_mouvementstock (
    id             INT AUTO_INCREMENT PRIMARY KEY,
    medicament_id  INT NOT NULL,
    type_mouvement VARCHAR(10) NOT NULL,      -- entree|sortie
    quantite       INT UNSIGNED NOT NULL,
    prix_unitaire  DECIMAL(10,2) NOT NULL DEFAULT 0,  -- prix figé au moment du mouvement
    motif          VARCHAR(200) NOT NULL DEFAULT '',
    ordonnance_id  INT NULL,                  -- dispensation liée à une ordonnance
    patient_id     INT NULL,
    facture_id     INT NULL,                  -- médicament porté sur la facture
    utilisateur_id INT NULL,
    date           DATETIME NOT NULL,
    FOREIGN KEY (medicament_id)  REFERENCES pharmacie_medicament(id)    ON DELETE CASCADE,
    FOREIGN KEY (ordonnance_id)  REFERENCES consultation_ordonnance(id) ON DELETE SET NULL,
    FOREIGN KEY (patient_id)     REFERENCES patients_patient(id)        ON DELETE SET NULL,
    FOREIGN KEY (facture_id)     REFERENCES facturation_facture(id)     ON DELETE SET NULL,
    FOREIGN KEY (utilisateur_id) REFERENCES auth_user(id)               ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;
