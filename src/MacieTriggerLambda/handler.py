import boto3
import json
import os
from datetime import datetime

DDB_TABLE_NAME = os.environ['TEXTRACTJOBSTATUSTABLE_TABLE_NAME']
MACIE_CUSTOM_IDENTIFIER_ID_COMMA_SEPARATED_STRING = os.environ['MACIE_CUSTOM_IDENTIFIER_ID_COMMA_SEPARATED_STRING'] 
MACIE_CUSTOM_IDENTIFIER_ID_LIST = [item.strip() for item in MACIE_CUSTOM_IDENTIFIER_ID_COMMA_SEPARATED_STRING.split(',')]

ddb_client = boto3.client('dynamodb')
s3_client = boto3.client('s3')
macie_client = boto3.client('macie2')


def handler(event, context):

    # Retrieve SNS message and convert to json object
    message = json.loads(event['Records'][0]['Sns']['Message'])
    # retrieve details from SNS message
    job_id = message['JobId']
    bucket_name = message['DocumentLocation']['S3Bucket']
    object_key = message['DocumentLocation']['S3ObjectName']
    job_status = message['Status']
    
    # Perform a GetItem to fetch the existing item
    existing_item_response = ddb_client.get_item(
        TableName=DDB_TABLE_NAME,
        Key={
            'Status': {'S': 'IN_PROGRESS'},
            'JobId': {'S': job_id}
        }
    )
    existing_item = existing_item_response.get('Item')
    start_timestamp = existing_item.get('StartTimestamp')
    complete_timestamp = datetime.now().isoformat(timespec='seconds')
    
    # Postprocessing on textract output file
    # Rename the textract output object to follow image object key    
    if job_status == 'SUCCEEDED':
        postprocessing_textract_output(job_id, bucket_name, object_key)
    
    # Combine delete and put operations into a single transaction to update job status in DynamoDB
    try:
        ddb_client.transact_write_items(
            TransactItems=[
                {
                    'Delete': {
                        'TableName': DDB_TABLE_NAME,
                        'Key': {
                            'Status': {'S': 'IN_PROGRESS'},
                            'JobId': {'S': job_id}
                        }
                    }
                },
                {
                    'Put': {
                        'TableName': DDB_TABLE_NAME,
                        'Item': {
                            'Status': {'S': job_status},
                            'JobId': {'S': job_id},
                            'Bucket': {'S': bucket_name},
                            'ObjectKey': {'S': object_key},
                            'StartTimestamp': start_timestamp,
                            'CompleteTimestamp': {'S': complete_timestamp},
                            'MacieScanned': {"BOOL": False}
                        },
                    }
                }
            ]
        )
    except Exception as e:
        print(f"Error in DynamoDB transaction: {e}")
        return

    # Query DynamoDB to check for any jobs that are still in progress before calling macie_scan
    if not check_in_progress_jobs():
        print ("All async Textract jobs complete. Starting Macie scan")
        macie_scan(context, bucket_name)
    else:
        print("Other async Textract jobs are still in progress. Skipping Macie scan.")


def postprocessing_textract_output(job_id, bucket_name, object_key):
    try:
        new_object_key = get_new_object_key(job_id, object_key)
        original_object_key = f'textract-output/{job_id}/1'

        s3_client.copy_object(
            CopySource={'Bucket': bucket_name, 'Key': original_object_key},
            Bucket=bucket_name, 
            Key=new_object_key
            )
        s3_client.delete_object(Bucket=bucket_name, Key=original_object_key)

        # Create a new txt file containing only the the extracted text 
        # Retrieve JSON data from S3
        response = s3_client.get_object(Bucket=bucket_name, Key=new_object_key)
        json_data = response['Body'].read().decode('utf-8')

        # Parse the JSON data
        parsed_data = json.loads(json_data)
        
        # Extract the "Text" key from each dictionary in the list
        texts = [block["Text"] for block in parsed_data['Blocks']]
               
        # Create TXT file with extracted text
        texts = [text for text in texts if text is not None]
        output_txt_data = '\n'.join(texts)
        output_txt_file_key = f'{new_object_key[:-5]}-postprocessed.txt'
    
        # Upload the TXT file to S3
        s3_client.put_object(Bucket=bucket_name, Key=output_txt_file_key, Body=output_txt_data.encode('utf-8'))
        
        print(f"Extracted text has been stored in S3 as {output_txt_file_key}")

    except Exception as e:
        print(f"Error in S3 operations: {e}")
        raise

def get_new_object_key(job_id, object_key):
    if object_key.endswith(('.png', '.jpg')):
        return f'textract-output/{job_id}/{object_key[:-4]}.json'
    elif object_key.endswith('.jpeg'):
        return f'textract-output/{job_id}/{object_key[:-5]}.json'
    else:
        raise ValueError(f"Unsupported file type: {object_key}")

def check_in_progress_jobs():
    try:
        in_progress_jobs = ddb_client.query(
            TableName=DDB_TABLE_NAME,
            KeyConditionExpression='#s = :status',
            ExpressionAttributeNames={'#s': 'Status'},
            ExpressionAttributeValues={':status': {'S': 'IN_PROGRESS'}},
            Limit=1
        )
        return 'Items' in in_progress_jobs and in_progress_jobs['Items']
    except Exception as e:
        print(f"Error checking in-progress jobs: {str(e)}")
        raise
        
def macie_scan(context, bucket_name):  
    # Query DynamoDB to get all jobs that have succeeded but haven't been scanned by Macie yet
    completed_jobs = ddb_client.query(
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

    # Iterate through each completed job
    for job in completed_jobs['Items']:
        job_id = job['JobId']['S']
        object_key = job['ObjectKey']['S']
        
        job_object_key = get_new_object_key(job_id, object_key)

        object_keys.append(job_object_key)
        postprocessed_object_key = f'{job_object_key[:-5]}-postprocessed.txt'
        object_keys.append(postprocessed_object_key)
        job_ids.append(job_id)

    # Start Macie scan for new jobs
    try:
        print ("Starting Macie scan")
        macie_response = macie_client.create_classification_job(
            jobType='ONE_TIME',
            name=f'Scan for {len(object_keys)} objects {datetime.now()}',
            customDataIdentifierIds= MACIE_CUSTOM_IDENTIFIER_ID_LIST,
            managedDataIdentifierSelector='RECOMMENDED',
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
        print(f"Macie job created: {macie_response['jobId']}")
    except Exception as e:
        print(f"Error in Macie scan: {e}")
        
    # Update value in Update DynamoDB MacieScanned=True
    for jobID in job_ids:
        try:
            update_response = ddb_client.update_item(
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
            print(f"Error updating DynamoDB for job {jobID}: {e}")
    return True