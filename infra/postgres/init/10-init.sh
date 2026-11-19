#!/bin/sh
# Runs once on first start of an empty data volume (docker-entrypoint-initdb.d).
set -e

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-SQL
	CREATE EXTENSION IF NOT EXISTS vector;
	CREATE DATABASE gauntlet_test;
SQL

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname gauntlet_test <<-SQL
	CREATE EXTENSION IF NOT EXISTS vector;
SQL
