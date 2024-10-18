import boto3
import json
import os
from datetime import datetime

DDB_TABLE_NAME = os.environ['TEXTRACTJOBSTATUSTABLE_TABLE_NAME']
MACIE_CUSTOM_IDENTIFIER_ID_COMMA_SEPARATED_STRING = os.environ['MACIE_CUSTOM_IDENTIFIER_ID_COMMA_SEPARATED_STRING'] 
MACIE_CUSTOM_IDENTIFIER_ID_LIST = [item.strip() for item in MACIE_CUSTOM_IDENTIFIER_ID_COMMA_SEPARATED_STRING.split(',')]

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
    
    # Postprocessing on textract output file
    # Rename the textract output object to follow image object key    
    if job_status == 'SUCCEEDED':
        original_object_key = f'textract-output/{job_id}/1'

        if object_key.endswith(('.png', '.jpg')):
            new_object_key = f'textract-output/{job_id}/{object_key[:-4]}' + '.json'
        if object_key.endswith(('.jpeg')):
            new_object_key = f'textract-output/{job_id}/{object_key[:-5]}' + '.json'

        s3.copy_object(
            CopySource= {'Bucket': bucket_name, 'Key': original_object_key},
            Bucket=bucket_name, 
            Key=new_object_key
            )
        s3.delete_object(Bucket=bucket_name, Key=original_object_key)
    
    # Create a new txt file containing only the the extracted text 
        # Retrieve JSON data from S3
        response = s3.get_object(Bucket=bucket_name, Key=new_object_key)
        json_data = response['Body'].read().decode('utf-8')
        
        # Parse the JSON data
        parsed_data = json.loads(json_data)
        
        # Extract the "Text" key from each dictionary in the list
        texts = [block["Text"] for block in parsed_data['Blocks']]
               
        # Create TXT file with extracted text
        texts = [text for text in texts if text is not None]
        output_txt_data = '\n'.join(texts)
        output_txt_file_key = f'{new_object_key[:-5]}-postprocessed'+'.txt'
    
        # Upload the TXT file to S3
        s3.put_object(Bucket=bucket_name, Key=output_txt_file_key, Body=output_txt_data.encode('utf-8'))
        
        print("Extracted text has been stored in S3 as", output_txt_file_key)
        
    
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
    
    
    macie_scan(context, job_id, bucket_name, new_object_key)
    

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
        print ("Other async textract jobs are still in progress")
        return None
    # If no, trigger macie scan
    else:
        # Get jobs which have finished Textract scan but not Macie scan
        print ("All async textract jobs done but macie scan not done")
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
            if job['ObjectKey']['S'].endswith(('.png', '.jpg')):
                job_object_key = f'textract-output/{job['JobId']['S']}/{job['ObjectKey']['S'][:-4]}' + '.json'
            if job['ObjectKey']['S'].endswith(('.jpeg')):
                job_object_key = f'textract-output/{job['JobId']['S']}/{job['ObjectKey']['S'][:-5]}' + '.json'

            object_keys.append(job_object_key)
            postprocessed_object_key = f'{job_object_key[:-5]}-postprocessed' +'.txt'
            object_keys.append(postprocessed_object_key)
            job_ids.append(job['JobId']['S'])

        # start Macie scan for new jobs
        try:
            print ("Starting Macie scan")
            response = macie.create_classification_job(
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