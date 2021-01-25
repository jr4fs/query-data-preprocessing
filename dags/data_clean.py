"""
### Data Cleaning Pipeline
A pipeline that cleans search log data.
(Based off of the Airflow 
[tutorial DAG](https://airflow.apache.org/docs/stable/tutorial.html)).
"""
from datetime import timedelta
from urllib.parse import urlparse
from airflow import DAG
from airflow.operators.bash_operator import BashOperator
from airflow.operators.sqlite_operator import SqliteOperator

from airflow.operators.python_operator import PythonOperator
from airflow.utils.dates import days_ago
from airflow.models import Connection
from airflow import settings
import pandas as pd
import sqlite3
import os
import logging

# [START default_args]
default_args = {
    'owner': 'airflow',
    'depends_on_past': False,
    'start_date': days_ago(2),
    'email': ['airflow@example.com'],
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
    # 'queue': 'bash_queue',
    # 'pool': 'backfill',
    # 'priority_weight': 10,
    # 'end_date': datetime(2016, 1, 1),
    # 'wait_for_downstream': False,
    # 'dag': dag,
    # 'sla': timedelta(hours=2),
    # 'execution_timeout': timedelta(seconds=300),
    # 'on_failure_callback': some_function,
    # 'on_success_callback': some_other_function,
    # 'on_retry_callback': another_function,
    # 'sla_miss_callback': yet_another_function,
    # 'trigger_rule': 'all_success'
}
# [END default_args]

# [START instantiate_dag]
dag = DAG(
    'clean_data',
    default_args=default_args,
    description='A simple tutorial DAG',
    schedule_interval=None,
)
# [END instantiate_dag]

tables = ['search_request', 'search_result_interaction']
db_con_str = os.getenv('AIRFLOW__CORE__SQL_ALCHEMY_CONN')
db_filepath = urlparse(db_con_str).path[1:]

def load_data():
    """Load the csv data into tables `search_request` and 
    `search_result_interaction` in the default db.
    """    
    # reuse the same sqlite db as airflow
    con = sqlite3.connect(db_filepath)
    
    data_dir = os.getenv('DATA_DIR')
    for table in tables:
        filename = os.path.join(data_dir, table + '.csv')
        if os.path.isfile(filename):
            df = pd.read_csv(filename)
            df.to_sql(table, con, if_exists='replace', index=False)
        else:
            logging.error("Filename does not exist")
            raise Exception(f'{filename} does not exist')

load_data = PythonOperator(
    task_id='load_data',
    python_callable=load_data,
    dag=dag
)

"""SQL operator toy example
Demonstrates how to access the tables populated in `load_data`.
The task itself does nothing. You're most likely to use this operator
to modify the table (it doesn't return a result).
"""
for table in tables:
    summary_sql = f"""
        select count(*)
        from {table}
    """
    read_data = SqliteOperator(
        task_id=f'read_data_{table}',
        sqlite_conn_id=os.getenv('CONN_ID'),
        sql=summary_sql,
        dag=dag,
    )
    load_data >> read_data

"""Pandas DF toy example
Demonstrates how to access the tables populated in `load_data` with pandas.
If you used pandas to load/modify data, you can work off of this example.
Hmm doesn't seem super efficient. 
"""
def clean_data_df(tablename: str):
    db_con_str = os.getenv('AIRFLOW__CORE__SQL_ALCHEMY_CONN')
    con = sqlite3.connect(db_filepath)
    df = pd.read_sql(f"select * from {tablename}", con)
    
    # Drop "Unnamed" columns
    junk_columns = df.columns[df.columns.str.startswith('Unnamed')]
    df = df.drop(junk_columns, axis=1)
    cols_before = list(df.columns)

    # Check if there are duplicate search ids, these are the
        # entries that need to be dropped to remove duplicates
    duplicate_search_id = df['search_id'].duplicated().any()
    if (duplicate_search_id):
        df = df.drop_duplicates(subset=['search_id'])
    
    # Convert time stamp to standardized format
    df['ts'] = pd.to_datetime(df['ts'])

    # Ensure all click data has a corresponding search request
    if ((tablename) == 'search_result_interaction'):
        search_request_df = pd.read_sql(f"select * from {'search_request'}", con)
        
        # Drop search_result_interaction entries that don't have corresponding search_id
        df = pd.merge(search_request_df, df, on='search_id')
        df = df.drop(junk_columns, axis=1)
        df = df.rename(columns={"ts_x": "ts_request", "ts_y": "ts"})

        # Check if all click data has corresponding search id
        search_request_ids = search_request_df['search_id'].tolist()
        df_ids = df['search_id'].tolist()
        ids_intersect = [id for id in search_request_ids if id in df_ids]
        if (len(ids_intersect) != len(df_ids)):
            logging.error("All click data does not have a search request")
        else:
            logging.info("All click data has a corresponding search request")
        if(len(search_request_ids) > len(ids_intersect)):
            logging.info("There were more search requests than clicked on data")

    # Display columns in each dataframe
    cols_cleaned = list(df.columns)
    cols_str = ' ,'.join(str(column) for column in cols_cleaned)
    #logging.info("Columns: ", str(cols_str))
    
    # Check if there are any duplicate entries
    if (df.duplicated().any()):
        logging.error("There are duplicate entries")
    else:
        logging.info("There are no duplicate entries")
    # Check if original columns are in tact
    cols_intersect = [value for value in cols_before if value in cols_cleaned]
    if (len(cols_intersect) != len(cols_before)):
        logging.error("Original columns are not in tact")
    else:
        logging.info("All original columns are in tact")
    
    # Replace the table with a cleaned version
    df.to_sql(f'clean_{tablename}', con, if_exists='replace', index=False)
        
for table in tables:
    clean_data = PythonOperator(
        task_id=f'clean_data_{table}',
        python_callable=clean_data_df,
        op_kwargs={
            'tablename': table
        },
        dag=dag,
    )
    load_data >> clean_data

# [START documentation]
dag.doc_md = __doc__

load_data.doc_md = """\
#### Load Data 
This task loads data from the csv files in the data directory (set as 
an environment variable DATA_DIR) into the database Airflow creates.
"""

read_data.doc_md = """\
#### Read Data 
This task does nothing. It demonstrates how to use the SQLite operator.
"""

clean_data.doc_md = """\
#### Clean Data 
This task removes a column with pandas. It demonstrates how to alter data 
and write it back into the same table.
"""
# [END documentation]
