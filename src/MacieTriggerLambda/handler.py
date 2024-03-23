import boto3
import json
import os
from datetime import datetime

DDB_TABLE_NAME = os.environ['TEXTRACTJOBSTATUSTABLE_TABLE_NAME']
MACIE_CUSTOM_IDENTIFIER_ID = os.environ['MACIECUSTOMIDENTIFIER']

ddb = boto3.client('dynamodb')
s3 = boto3.client('s3')
textract = boto3.client('textract')
sns = boto3.client('sns')
macie = boto3.client('macie2')


def handler(event, context):

    # retrieve SNS message and convert to json object
    message = event['Records'][0]['Sns']['Message']
    textract_json = json.loads(message)
    # retrieve details from SNS message
    job_id = textract_json['JobId']
    bucket_name = textract_json['DocumentLocation']['S3Bucket']
    object_key = textract_json['DocumentLocation']['S3ObjectName']
    job_status = textract_json['Status']

    
    # Perform a GetItem to fetch the existing item
    existing_item_response = ddb.get_item(
        TableName=DDB_TABLE_NAME,
        Key={
            'Status': {'S': 'IN_PROGRESS'},
            'JobId': {'S': job_id}
        }
    )
    existing_item = existing_item_response.get('Item')
    start_timestamp = existing_item.get('StartTimestamp')
    complete_timestamp = datetime.now().isoformat(timespec='seconds')
    
    #update job status in DynamoDB, since its the partition key, have to delete and recreate the item with the new keys in a transaction
    put_transaction_item = [
        {
            'Put': {
                'TableName': DDB_TABLE_NAME,
                'Item': {
                    'Status': {'S': job_status},
                    'JobId': {'S': job_id},
                    'Bucket': {'S': bucket_name},
                    'ObjectKey': {'S': object_key},
                    'StartTimestamp': start_timestamp, #already in the proper format
                    'CompleteTimestamp': {'S': complete_timestamp},
                    'MacieScanned': {"BOOL": False}
                },
            }
        }
    ]
    delete_transaction_item = [
        {
            'Delete': {
                'TableName': DDB_TABLE_NAME,
                'Key': {
                    'Status': {'S': 'IN_PROGRESS'},
                    'JobId': {'S': job_id}
                }
            }
        }
    ]
    # Delete item
    try:
        delete_response = ddb.transact_write_items(
            TransactItems=delete_transaction_item
        )
        # print("Delete transaction successful:", delete_response)
    except Exception as e:
        print("Error in transaction:", e)
    
    # Put item with new status
    try:
        put_response = ddb.transact_write_items(
            TransactItems=put_transaction_item
        )
        # print("Put transaction successful:", put_response)
    except Exception as e:
        print("Error in transaction:", e)
    
    # Rename the textract output object to follow image object key    
    if job_status == 'SUCCEEDED':
        original_object_key = f'textract-output/{job_id}/1'
        new_object_key = f'textract-output/{job_id}/' + object_key[:-4] + '.json'
        
        s3.copy_object(
            CopySource= {'Bucket': bucket_name, 'Key': original_object_key}, 
            Bucket=bucket_name, 
            Key=new_object_key
            )
        s3.delete_object(Bucket=bucket_name, Key=original_object_key)
    macie_scan(context, job_id, bucket_name, new_object_key)
    
## YT starts here
def macie_scan(context, job_id, bucket_name, object_key):  
    # Query DynamoDB to check for any jobs that are still in progress
    in_progress_jobs = ddb.query(
        TableName=DDB_TABLE_NAME,
        ExpressionAttributeValues={
            ':status': {
                'S': 'IN_PROGRESS'
            }
        },
        KeyConditionExpression='#s = :status',
        ExpressionAttributeNames={
            '#s': 'Status'
        }
    )

    # If yes, end
    if 'Items' in in_progress_jobs and in_progress_jobs['Items']:
        return None
    # If no, trigger macie scan
    else:
        # Get jobs which have finished Textract scan but not Macie scan
        completed_jobs = ddb.query(
            TableName=DDB_TABLE_NAME,
            ExpressionAttributeValues={
                ':status': {
                    'S': 'SUCCEEDED'
                },
                ':scanboolean': {
                    'BOOL': False
                }
            },
            KeyConditionExpression='#s = :status',
            ExpressionAttributeNames={
                '#s': 'Status'
            },
            FilterExpression='MacieScanned = :scanboolean'
        )

        object_keys = []
        job_ids = []
        for job in completed_jobs['Items']:
            job_object_key = f'textract-output/' + job['JobId']['S'] + '/' + job['ObjectKey']['S'][:-4] + '.json'
            object_keys.append(job_object_key)
            job_ids.append(job['JobId']['S'])

        # start Macie scane for new jobs
        try:
            response = macie.create_classification_job(
                jobType='ONE_TIME',
                name=f'Scan for {len(object_keys)} objects {datetime.now()}',
                customDataIdentifierIds=[
                    MACIE_CUSTOM_IDENTIFIER_ID
                ],
                s3JobDefinition={
                    'bucketDefinitions': [
                        {
                            'accountId': context.invoked_function_arn.split(":")[4],
                            'buckets': [bucket_name],
                        },
                    ],
                    'scoping': {
                        'includes': {
                            'and': [
                                {
                                    'simpleScopeTerm':{ 
                                        'comparator': 'STARTS_WITH',
                                        'key':'OBJECT_KEY',
                                        'values': object_keys
                                    }
                                }  
                            ]
                        }
                    }
                }
            )
        except Exception as e:
            print("Error in transaction:", e)
            
        # Update value in ddb MacieScanned=True
        for jobID in job_ids:
            try:
                update_response = ddb.update_item(
                    TableName=DDB_TABLE_NAME,
                    Key={
                        'Status': {'S': 'SUCCEEDED'},
                        'JobId': {'S': jobID}
                    },
                    UpdateExpression='set MacieScanned=:ms',
                    ExpressionAttributeValues={':ms':{'BOOL': True}},
                    ReturnValues='ALL_NEW'
                )
            except Exception as e:
                print("Error in transaction:", e)
        return True
            
            
    
    


