-- Création d'un compte SQL Server en lecture seule, dédié à la synchronisation
-- de stock de l'application de commande FRPS (stock_sync.SageSQLServerConnector).
--
-- À exécuter par l'administrateur SQL Server du FRPS, avec un compte ayant les
-- droits d'administration (sysadmin ou équivalent), dans SQL Server Management
-- Studio (SSMS) ou sqlcmd.
--
-- Remplacer :
--   - NOM_BASE_SAGE   : le nom réel de la base de données Sage Gescom
--   - MotDePasseSolide : un mot de passe fort (à reporter ensuite dans le .env
--                        de l'application, variable SQLSERVER_PASSWORD)

-- 1. Créer le login au niveau du serveur
USE master;
GO
CREATE LOGIN frps_commande_readonly WITH PASSWORD = 'MotDePasseSolide123!';
GO

-- 2. Créer l'utilisateur dans la base Sage Gescom et l'associer au login
USE NOM_BASE_SAGE;
GO
CREATE USER frps_commande_readonly FOR LOGIN frps_commande_readonly;
GO

-- 3. Donner UNIQUEMENT des droits de lecture
--
-- Option A (rapide) : lecture sur TOUTES les tables de la base.
-- Pratique pour démarrer, mais donne accès à des tables potentiellement sans
-- rapport avec le stock (comptabilité, etc.) si la base Sage est partagée
-- entre plusieurs modules.
ALTER ROLE db_datareader ADD MEMBER frps_commande_readonly;
GO

-- Option B (recommandée à terme, plus restrictive) : lecture sur UNE SEULE
-- table/vue précise (celle contenant réellement le stock/les articles).
-- Décommenter et adapter le nom de table une fois confirmé avec l'équipe Sage,
-- et retirer l'ajout au rôle db_datareader ci-dessus (option A) si utilisé.
--
-- GRANT SELECT ON dbo.NOM_TABLE_ARTICLES TO frps_commande_readonly;
-- GO

-- 4. Vérification : ce compte ne doit avoir AUCUN droit d'écriture.
-- Pour confirmer, essayer (avec ce compte) une requête d'écriture, qui doit échouer :
--   INSERT INTO dbo.NOM_TABLE_ARTICLES (...) VALUES (...);  -- doit renvoyer une erreur de permission
