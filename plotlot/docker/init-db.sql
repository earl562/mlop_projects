-- Create separate database for MLflow backend store.
-- Mounted as /docker-entrypoint-initdb.d/ in the db service.
CREATE DATABASE plotlot_mlflow;
