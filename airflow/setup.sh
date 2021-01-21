#!/bin/bash

airflow initdb
wait $!
airflow connections -a --conn_id $CONN_ID --conn_type sqlite --conn_host $CONN_HOST
airflow webserver
