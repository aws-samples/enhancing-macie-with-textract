import boto3
import botocore
import os
from datetime import datetime

DDB_TABLE_NAME = os.environ['TEXTRACTJOBSTATUSTABLE_TABLE_NAME']
TEXTRACT_SNS_TOPIC_ARN = os.environ['TEXTRACT_SNS_TOPIC_ARN']
TEXTRACT_SERVICE_ROLE_ARN = os.environ['TEXTRACT_SERVICE_ROLE_ARN']
S3_BUCKET_NAME = os.environ['S3WITHSENSITIVEDATA_BUCKET_NAME']

textract = boto3.client('textract')
ddb = boto3.client('dynamodb')

s3 = boto3.resource('s3')
bucket = s3.Bucket(S3_BUCKET_NAME)

def handler(event, context):
    #get all file information from S3 bucket
    files = bucket.objects.all()

    # create empty list for final information
    image_files_to_scan = []

    # only looking at images extensions
    extensions = ['png', 'jpg']

    # Iterate through files and only process the images
    for file in files:
        if file.key[-3:] in extensions:
            image_files_to_scan.append({'object_key' : file.key, 'extension' : file.key[-3:]})
    
            print(f'Processing {S3_BUCKET_NAME}/{file.key}')
            document_location = {
                    'S3Object': {
                        'Bucket': S3_BUCKET_NAME, 
                        'Name': file.key
                        }
                    }
            output_config = {
                'S3Bucket': S3_BUCKET_NAME,
                'S3Prefix': 'textract-output'
                }
            notification_channel = {
                'SNSTopicArn': TEXTRACT_SNS_TOPIC_ARN,
                'RoleArn': TEXTRACT_SERVICE_ROLE_ARN
                }

            job_id, status = start_textract_job(document_location, output_config, notification_channel)
            print(f'Started Textract job {job_id}')
            
            time_stamp = datetime.now().isoformat(timespec='seconds')

            ddb.put_item(
                TableName=DDB_TABLE_NAME, 
                Item={
                    'JobId': {'S': job_id}, 
                    'Bucket' : {'S': S3_BUCKET_NAME}, 
                    'ObjectKey': {'S': file.key}, 
                    'Status': {'S': status},
                    'StartTimestamp': {'S': time_stamp},
                    'MacieScanned': {"BOOL": False}
                })
            print(f'Textract job {job_id} details have been added to DynamoDB')

def start_textract_job(documentation_location, output_config, notification_channel):
    response = textract.start_document_text_detection(
        DocumentLocation=documentation_location,
        OutputConfig=output_config,
        NotificationChannel=notification_channel
    )
    # response_update = textract.get_document_text_detection(JobId=response['JobId'])
    job_id = response["JobId"]
    # status = response_update["JobStatus"]
    status = "IN_PROGRESS"
    return job_id, status
