-- =============================================================================
-- Foreign key constraints for apc_db, based on the ER diagram.
--
-- IMPORTANT: check each column name below against your actual tables
-- (phpMyAdmin -> table -> Structure) before running these. Column names
-- must match EXACTLY (case included). Adjust any that differ.
--
-- ON UPDATE CASCADE  -> if a parent's key changes (e.g. a physician's PID),
--                       every table that references it updates automatically.
-- ON DELETE RESTRICT -> stops you from deleting a row that other tables still
--                       depend on (e.g. a physician who has consultations),
--                       so you don't accidentally orphan data.
-- ON DELETE CASCADE   -> used only for pure "detail" rows that have no
--                       meaning without their parent (a hospital's location,
--                       a diagnosis tied to one consultation, a physician's
--                       speciality link) — deleting the parent removes these
--                       automatically instead of leaving orphaned rows.
--
-- Run each block once. If you need to re-run after fixing a mistake, drop
-- the constraint first:
--   ALTER TABLE table_name DROP FOREIGN KEY constraint_name;
-- =============================================================================

-- Make sure every table below uses the InnoDB engine — foreign keys do not
-- work on MyISAM. Uncomment and run these first if unsure:
-- ALTER TABLE patient ENGINE=InnoDB;
-- ALTER TABLE physician ENGINE=InnoDB;
-- ALTER TABLE consultation ENGINE=InnoDB;
-- ALTER TABLE hospital ENGINE=InnoDB;
-- ALTER TABLE hospital_location ENGINE=InnoDB;
-- ALTER TABLE diagnosis ENGINE=InnoDB;
-- ALTER TABLE coveragepolicy ENGINE=InnoDB;
-- ALTER TABLE speciality ENGINE=InnoDB;
-- ALTER TABLE physician_speciality ENGINE=InnoDB;

-- Physician belongs to a Hospital (physician.HID -> hospital.HID)
ALTER TABLE physician
  ADD CONSTRAINT fk_physician_hospital
  FOREIGN KEY (HID) REFERENCES hospital (HID)
  ON UPDATE CASCADE
  ON DELETE RESTRICT;

-- Patient has a Coverage Policy (patient.PoId -> coveragepolicy.POId)
ALTER TABLE patient
  ADD CONSTRAINT fk_patient_coveragepolicy
  FOREIGN KEY (PoId) REFERENCES coveragepolicy (POId)
  ON UPDATE CASCADE
  ON DELETE RESTRICT;

-- Hospital Location belongs to a Hospital (hospital_location.HID -> hospital.HID)
-- A location has no meaning without its hospital, so deleting the hospital
-- removes its location record too.
ALTER TABLE hospital_location
  ADD CONSTRAINT fk_hospitallocation_hospital
  FOREIGN KEY (HID) REFERENCES hospital (HID)
  ON UPDATE CASCADE
  ON DELETE CASCADE;

-- Physician <-> Speciality bridge table (physician_speciality)
ALTER TABLE physician_speciality
  ADD CONSTRAINT fk_physicianspeciality_physician
  FOREIGN KEY (PID) REFERENCES physician (PID)
  ON UPDATE CASCADE
  ON DELETE CASCADE;

ALTER TABLE physician_speciality
  ADD CONSTRAINT fk_physicianspeciality_speciality
  FOREIGN KEY (SName) REFERENCES speciality (SName)
  ON UPDATE CASCADE
  ON DELETE CASCADE;

-- Consultation links one Physician and one Patient
ALTER TABLE consultation
  ADD CONSTRAINT fk_consultation_physician
  FOREIGN KEY (PID) REFERENCES physician (PID)
  ON UPDATE CASCADE
  ON DELETE RESTRICT;

ALTER TABLE consultation
  ADD CONSTRAINT fk_consultation_patient
  FOREIGN KEY (PSSN) REFERENCES patient (PSSN)
  ON UPDATE CASCADE
  ON DELETE RESTRICT;

-- Diagnosis belongs to one specific Consultation (composite key: CTime, PID, PSSN).
-- This requires `consultation` to already have a PRIMARY KEY or UNIQUE
-- constraint on exactly (CTime, PID, PSSN) — if it doesn't yet, run:
--   ALTER TABLE consultation ADD PRIMARY KEY (CTime, PID, PSSN);
-- before running the constraint below.
ALTER TABLE diagnosis
  ADD CONSTRAINT fk_diagnosis_consultation
  FOREIGN KEY (CTime, PID, PSSN) REFERENCES consultation (CTime, PID, PSSN)
  ON UPDATE CASCADE
  ON DELETE CASCADE;
