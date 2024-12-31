import json
import base64
import boto3
import os
import gzip

SNS_TOPIC_ARN = os.environ['TOPIC_ARN']
sns_client = boto3.client('sns')

def handler(event, context):
    # Decode and decompress the CloudWatch Logs payload
    payload = base64.b64decode(event['awslogs']['data'])
    payload = gzip.decompress(payload)
    payload = json.loads(payload.decode('UTF-8'))
    
    # Process the last log event
    log_event = json.loads(payload['logEvents'][-1]['message'])
    
    subject = f"{log_event['description']}: {log_event['jobName']}"
    message = (f"Time: {log_event['occurredAt']}\n"
                f"Account Id: {log_event['adminAccountId']}\n"
                f"Job Id: {log_event['jobId']}\n"
                f"Job Name: {log_event['jobName']}\n"
                f"Description: {log_event['description']}")
    
    # Notify the administrator
    response = sns_client.publish(
        TopicArn=SNS_TOPIC_ARN,
        Message=message,
        Subject=subject
        )
    
    print(f"SNS notification sent. Message ID: {response['MessageId']}")