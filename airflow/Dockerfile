FROM apache/airflow:1.10.12

USER root
COPY ./airflow/setup.sh /opt/airflow/setup.sh

RUN chmod 777 /opt/airflow/setup.sh

USER airflow

ENTRYPOINT [ "./setup.sh" ] 
