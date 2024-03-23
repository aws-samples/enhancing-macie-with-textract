import json
import base64
import boto3
import os
import gzip

snsTopicArn = os.environ['TOPIC_ARN']
snsc = boto3.client('sns')

def handler(event, context):

    payload = base64.b64decode(event['awslogs']['data'])
    payload = gzip.decompress(payload)
    payload = payload.decode('UTF-8')
    payload = json.loads(payload)
    
    for aL in (payload['logEvents']):
        bL = json.loads(aL['message'])
    
    sbT = bL['description']+": "+bL['jobName']
    msT = "Time: "+bL['occurredAt']+"\n"
    msT = msT + "Account Id: "+bL['adminAccountId']+"\n"
    msT = msT + "Job Id: "+bL['jobId']+"\n"
    msT = msT + "Job Name: "+bL['jobName']+"\n"
    msT = msT + "Description: "+bL['description']+"\n"
    
    # Notify the administrator
    response = snsc.publish(
        TopicArn=snsTopicArn,
        Message=msT,
        Subject=sbT
        )